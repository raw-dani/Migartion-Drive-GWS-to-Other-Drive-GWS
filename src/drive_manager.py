from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from socket import timeout as SocketTimeout
import ssl
import os
import io
import zipfile
import json
import logging
import socket
import googleapiclient.errors
from datetime import datetime
from auth_manager import AuthManager
from config import CONFIG

class DriveManager:
    def __init__(self):
        self.source_service = AuthManager.get_drive_service(
            CONFIG['SOURCE_CREDENTIALS_FILE'],
            os.path.join(CONFIG['TOKEN_DIR'], 'source_token.pickle')
        )
        self.dest_service = AuthManager.get_drive_service(
            CONFIG['DEST_CREDENTIALS_FILE'],
            os.path.join(CONFIG['TOKEN_DIR'], 'dest_token.pickle')
        )
        self.setup_logging()
        self.retry_count = 0
        self.max_retries = 5
        self.current_file_count = 0
        self.total_files = 0
        self.metadata = {}
        self.metadata_path = os.path.join(CONFIG['TEMP_DIR'], 'file_metadata.json')
        self._init_metadata()
        self.timeout = 300  # 5 minutes timeout
        ssl._create_default_https_context = ssl._create_unverified_context

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True
    )
    def _make_request(self, request):
        try:
            return request.execute(num_retries=5)
        except Exception as e:
            logging.warning(f"Request failed, retrying... {str(e)}")
            raise


    def _init_metadata(self):
        """Initialize metadata storage"""
        os.makedirs(CONFIG['TEMP_DIR'], exist_ok=True)
        
        try:
            with open(self.metadata_path, 'r') as f:
                self.metadata = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.metadata = {}
            with open(self.metadata_path, 'w') as f:
                json.dump(self.metadata, f)

    def _save_metadata(self):
        """Save current metadata to file"""
        with open(self.metadata_path, 'w') as f:
            json.dump(self.metadata, f)

    def setup_logging(self):
        log_file = os.path.join(
            CONFIG['LOG_DIR'], 
            f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def set_ui(self, ui):
        self.ui = ui

    def count_total_files(self, folder_id='root'):
        try:
            count = 0
            results = self.source_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, mimeType)"
            ).execute()
            
            for item in results.get('files', []):
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    count += self.count_total_files(item['id'])
                else:
                    count += 1
            
            return count
        except Exception as e:
            logging.error(f"Error counting files: {str(e)}")
            return 0

    def download_drive(self, user_email):
        logging.info(f"Starting download for {user_email}")
        self.total_files = self.count_total_files()
        self.current_file_count = 0
        
        zip_path = os.path.join(CONFIG['TEMP_DIR'], f"{user_email}_drive.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            self._download_folder('root', '', zip_file)
            
        logging.info(f"Download completed for {user_email}")
        return zip_path

    def download_shared_drive(self, user_email):
        """Download Shared Drive contents"""
        logging.info(f"Starting Shared Drive download for {user_email}")
        
        # Get list of shared drives
        shared_drives = self.source_service.drives().list(fields="drives(id, name)").execute()
        
        for drive in shared_drives.get('drives', []):
            try:
                zip_path = os.path.join(CONFIG['TEMP_DIR'], f"shared_drive_{drive['name']}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    self._download_folder(drive['id'], '', zip_file, is_shared_drive=True)
                logging.info(f"Downloaded shared drive: {drive['name']}")
                return zip_path
            except Exception as e:
                logging.error(f"Error downloading shared drive {drive['name']}: {str(e)}")
                raise
    
    def download_shared_with_me(self, user_email):
        """Download files shared with the user that are owned by source"""
        logging.info(f"Starting Shared with me download for {user_email}")
        zip_path = os.path.join(CONFIG['TEMP_DIR'], f"{user_email}_shared.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            results = self._make_request(
                self.source_service.files().list(
                    q="sharedWithMe=true and trashed=false",
                    fields="files(id, name, mimeType, parents, owners)",
                    pageSize=1000
                )
            )
            
            for item in results.get('files', []):
                # Check if the file is owned by source user
                if item['owners'][0]['emailAddress'] == user_email:
                    self._handle_shared_item(item, zip_file)
                
        logging.info(f"Completed downloading shared files for {user_email}")
        return zip_path

    def _handle_shared_item(self, item, zip_file):
        """Process individual shared items"""
        try:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                self._download_folder(item['id'], item['name'], zip_file)
            else:
                self._download_file(item, '', zip_file)
        except Exception as e:
            logging.error(f"Error handling shared item {item['name']}: {str(e)}")

    def _handle_shortcut(self, item, folder_path, zip_file):
        """Handle Google Drive shortcuts and owned files within shortcut folders"""
        try:
            target_id = item['shortcutDetails']['targetId']
            
            # Get target folder contents if it's a folder
            results = self.source_service.files().list(
                q=f"'{target_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, owners)",
                pageSize=1000
            ).execute()
            
            # Store shortcut mapping for recreation
            shortcut_info = {
                'sourceId': item['id'],
                'targetId': target_id,
                'path': folder_path,
                'name': item['name']
            }
            if not hasattr(self, 'shortcuts'):
                self.shortcuts = []
            self.shortcuts.append(shortcut_info)
            
            # Process files in shortcut folder
            for file in results.get('files', []):
                if file['owners'][0]['emailAddress'] == self.source_email:
                    if file['mimeType'] == 'application/vnd.google-apps.folder':
                        new_path = os.path.join(folder_path, self._clean_filename(file['name']))
                        self._download_folder(file['id'], new_path, zip_file)
                    else:
                        self._download_file(file, folder_path, zip_file)
                        
        except Exception as e:
            logging.error(f"Error processing shortcut folder contents: {str(e)}")

    def _recreate_shortcuts(self, dest_email):
        """Recreate shortcuts in destination drive"""
        for shortcut in self.shortcuts:
            try:
                shortcut_metadata = {
                    'name': shortcut['name'],
                    'mimeType': 'application/vnd.google-apps.shortcut',
                    'shortcutDetails': {
                        'targetId': shortcut['targetId']
                    },
                    'parents': [self._get_or_create_folder(shortcut['path'], dest_email)]
                }
                
                self.dest_service.files().create(
                    body=shortcut_metadata,
                    fields='id'
                ).execute()
                
                logging.info(f"Recreated shortcut: {shortcut['name']}")
                
            except Exception as e:
                logging.error(f"Error recreating shortcut {shortcut['name']}: {str(e)}")

    def _download_folder(self, folder_id, folder_path, zip_file):
        try:
            results = self.source_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)",
                pageSize=1000
            ).execute()

            for item in results.get('files', []):
                try:
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        new_path = os.path.join(folder_path, self._clean_filename(item['name']))
                        self._download_folder(item['id'], new_path, zip_file)
                    else:
                        self._download_file(item, folder_path, zip_file)
                        self.current_file_count += 1
                        if hasattr(self, 'ui'):
                            self.ui.update_transfer_info(
                                item['name'],
                                "Downloading",
                                self.current_file_count,
                                self.total_files
                            )
                except Exception as e:
                    logging.error(f"Error downloading {item['name']}: {str(e)}")
                    continue

        except Exception as e:
            logging.error(f"Error downloading folder {folder_id}: {str(e)}")
            raise

    def _download_file(self, item, folder_path, zip_file):
        try:
            # Add shortcut handling at the start
            if item['mimeType'] == 'application/vnd.google-apps.shortcut':
                self._handle_shortcut(item, folder_path, zip_file)
                return
            # Existing workspace file handling    
            elif item['mimeType'].startswith('application/vnd.google-apps'):
                self._handle_workspace_file(item, folder_path, zip_file)
            else:
                request = self.source_service.files().get_media(fileId=item['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                file_path = os.path.join(folder_path, self._clean_filename(item['name']))
                self.metadata[file_path] = item['id']
                self._save_metadata()

                zip_file.writestr(file_path, fh.getvalue())
                logging.info(f"Downloaded: {item['name']}")
        except Exception as e:
            logging.error(f"Error downloading file {item['name']}: {str(e)}")
            raise

    def _handle_workspace_file(self, item, folder_path, zip_file):
        workspace_formats = {
            'application/vnd.google-apps.document': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
            'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
            'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
            'application/vnd.google-apps.drawing': ('application/pdf', '.pdf'),
            'application/vnd.google-apps.script': ('application/json', '.json'),
            'application/vnd.google-apps.form': ('application/pdf', '.pdf')
        }

        if item['mimeType'] in workspace_formats:
            export_mime, extension = workspace_formats[item['mimeType']]
            request = self.source_service.files().export_media(
                fileId=item['id'],
                mimeType=export_mime
            )
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            file_path = os.path.join(folder_path, f"{self._clean_filename(item['name'])}{extension}")
            zip_file.writestr(file_path, fh.getvalue())
            logging.info(f"Exported: {item['name']}")

    def extract_drive(self, zip_path):
        logging.info(f"Starting extraction of {zip_path}")
        extract_path = os.path.join(CONFIG['TEMP_DIR'], 'extracted')
        os.makedirs(extract_path, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
        logging.info("Extraction completed")
        return extract_path

    def upload_drive(self, extract_path, destination_email, source_domain, target_domain):
        logging.info(f"Starting upload process to {destination_email}")
        try:
            resume_file = os.path.join(CONFIG['TEMP_DIR'], f'resume_{destination_email}.txt')
            uploaded_files = set()
            if os.path.exists(resume_file):
                with open(resume_file, 'r') as f:
                    uploaded_files = set(f.read().splitlines())

            # Count total files for upload
            self.total_files = sum([len(files) for _, _, files in os.walk(extract_path)])
            self.current_file_count = len(uploaded_files)

            result = self._upload_folder(extract_path, 'root', uploaded_files, resume_file, source_domain, target_domain)
            return result
        except Exception as e:
            logging.error(f"Upload failed: {str(e)}")
            raise
        
    def list_shared_drives(self, user_email):
        """Get list of shared drives"""
        try:
            results = self.source_service.drives().list(fields="drives(id, name)").execute()
            drives = results.get('drives', [])
            if drives:
                logging.info(f"Found {len(drives)} shared drives")
            return drives
        except Exception as e:
            logging.error(f"Error listing shared drives: {str(e)}")
            return []

    def upload_shared_drive(self, extract_path, destination_email):
        """Upload shared drive content to destination"""
        logging.info(f"Starting shared drive upload to {destination_email}")
        try:
            # Create new shared drive in destination
            drive_metadata = {
                'name': f"Migrated Shared Drive - {datetime.now().strftime('%Y%m%d')}"
            }
            new_drive = self.dest_service.drives().create(body=drive_metadata).execute()
            
            # Upload content to new shared drive
            self._upload_folder(extract_path, new_drive['id'], set(), 
                os.path.join(CONFIG['TEMP_DIR'], f'resume_shared_{destination_email}.txt'))
                
            logging.info("Shared drive upload completed")
            return new_drive['id']
        except Exception as e:
            logging.error(f"Shared drive upload failed: {str(e)}")
            raise

    def upload_shared_with_me(self, extract_path, destination_email):
        """Upload shared files to destination"""
        logging.info(f"Starting shared files upload to {destination_email}")
        try:
            # Create shared folder in destination
            folder_metadata = {
                'name': f"Migrated Shared Files - {datetime.now().strftime('%Y%m%d')}",
                'mimeType': 'application/vnd.google-apps.folder'
            }
            shared_folder = self.dest_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            # Upload shared content
            self._upload_folder(extract_path, shared_folder['id'], set(),
                os.path.join(CONFIG['TEMP_DIR'], f'resume_shared_files_{destination_email}.txt'))
                
            logging.info("Shared files upload completed")
            return shared_folder['id']
        except Exception as e:
            logging.error(f"Shared files upload failed: {str(e)}")
            raise

    def _get_file_permissions(self, file_id):
        """Get sharing permissions of a file/folder"""
        try:
            permissions = self.source_service.permissions().list(
                fileId=file_id,
                fields='permissions(emailAddress,role,type,domain)'
            ).execute()
            return permissions.get('permissions', [])
        except Exception as e:
            logging.error(f"Error getting permissions for file {file_id}: {str(e)}")
            return []

    def _map_email_domain(self, source_email, source_domain, target_domain):
        """Map email from source domain to target domain"""
        username = source_email.split('@')[0]
        return f"{username}@{target_domain}"

    def _migrate_sharing_permissions(self, source_file_id, dest_file_id, source_domain, target_domain):
        """Migrate sharing permissions from source to destination"""
        permissions = self._get_file_permissions(source_file_id)
        
        for permission in permissions:
            try:
                if permission.get('emailAddress'):
                    if source_domain in permission['emailAddress']:
                        new_email = self._map_email_domain(
                            permission['emailAddress'],
                            source_domain,
                            target_domain
                        )
                        
                        new_permission = {
                            'type': 'user',
                            'role': permission['role'],
                            'emailAddress': new_email
                        }
                        
                        self.dest_service.permissions().create(
                            fileId=dest_file_id,
                            body=new_permission,
                            sendNotificationEmail=False
                        ).execute()
                        logging.info(f"Shared {dest_file_id} with {new_email}")
                        
                elif permission.get('domain') == source_domain:
                    new_permission = {
                        'type': 'domain',
                        'role': permission['role'],
                        'domain': target_domain
                    }
                    
                    self.dest_service.permissions().create(
                        fileId=dest_file_id,
                        body=new_permission,
                        sendNotificationEmail=False
                    ).execute()
                    logging.info(f"Shared {dest_file_id} with domain {target_domain}")
                    
            except Exception as e:
                logging.error(f"Error migrating permission: {str(e)}")

    def _store_file_mapping(self, source_id, dest_id):
        """Store mapping of source and destination file IDs"""
        if not hasattr(self, 'file_mapping'):
            self.file_mapping = {}
        self.file_mapping[source_id] = dest_id

    def _get_source_file_id(self, file_path):
        """Get source file ID from stored metadata"""
        metadata_path = os.path.join(CONFIG['TEMP_DIR'], 'file_metadata.json')
        try:
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    return metadata.get(file_path)
        except Exception as e:
            logging.error(f"Error getting source file ID: {str(e)}")
        return None


    def _upload_folder(self, local_path, parent_id, uploaded_files, resume_file, source_domain=None, target_domain=None):
        for item in os.listdir(local_path):
            item_path = os.path.join(local_path, item)
            
            if item_path in uploaded_files:
                logging.info(f"Skipping already uploaded: {item}")
                continue

            try:
                if hasattr(self, 'ui'):
                    self.ui.update_transfer_info(
                        item,
                        "Uploading",
                        self.current_file_count,
                        self.total_files
                    )

                if os.path.isdir(item_path):
                    folder_metadata = {
                        'name': item,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [parent_id]
                    }
                    folder = self._retry_upload(self.dest_service.files().create(
                        body=folder_metadata,
                        fields='id'
                    ))
                    # Migrate folder permissions
                    source_id = self._get_source_file_id(item_path)
                    if source_id:
                        self._migrate_sharing_permissions(source_id, folder['id'], source_domain, target_domain)
                
                    self._upload_folder(item_path, folder['id'], uploaded_files, resume_file)
                else:
                    file_metadata = {
                        'name': item,
                        'parents': [parent_id]
                    }
                    media = MediaFileUpload(item_path, resumable=True)
                    self._retry_upload(self.dest_service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id'
                    ))
                    # Migrate file permissions
                    source_id = self._get_source_file_id(item_path)
                    if source_id:
                        self._migrate_sharing_permissions(source_id, uploaded_file['id'], source_domain, target_domain)
                
                    self.current_file_count += 1

                with open(resume_file, 'a') as f:
                    f.write(f"{item_path}\n")
                uploaded_files.add(item_path)
                logging.info(f"Uploaded: {item}")

            except Exception as e:
                logging.error(f"Error uploading {item}: {str(e)}")
                raise

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True
    )
    def _retry_upload(self, request):
        try:
            return request.execute(num_retries=5)
        except (socket.error, googleapiclient.errors.HttpError) as e:
            self.retry_count += 1
            logging.warning(f"Retry attempt {self.retry_count}/{self.max_retries}: {str(e)}")
            if self.retry_count >= self.max_retries:
                logging.error("Max retries reached. Upload failed.")
                raise RetryError("Upload failed after maximum retries")
            raise
        finally:
            if self.retry_count >= self.max_retries:
                self.retry_count = 0

    def _clean_filename(self, filename):
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename

    def _get_or_create_folder(self, folder_path, destination_email):
        if folder_path == '.':
            return 'root'
            
        folder_names = folder_path.split(os.sep)
        parent_id = 'root'
        
        for folder_name in folder_names:
            if not folder_name:
                continue
                
            query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.dest_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            if results.get('files'):
                parent_id = results.get('files')[0]['id']
            else:
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]
                }
                folder = self.dest_service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                parent_id = folder['id']
        
        return parent_id
