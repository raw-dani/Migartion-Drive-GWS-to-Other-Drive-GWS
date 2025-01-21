from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import os
import io
import zipfile
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
        """Download files shared with the user"""
        logging.info(f"Starting Shared with me download for {user_email}")
        zip_path = os.path.join(CONFIG['TEMP_DIR'], f"{user_email}_shared.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            results = self.source_service.files().list(
                q="sharedWithMe=true and trashed=false",
                fields="files(id, name, mimeType, parents)",
                pageSize=1000
            ).execute()
            
            for item in results.get('files', []):
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
            if item['mimeType'].startswith('application/vnd.google-apps'):
                self._handle_workspace_file(item, folder_path, zip_file)
            else:
                request = self.source_service.files().get_media(fileId=item['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                file_path = os.path.join(folder_path, self._clean_filename(item['name']))
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

    def upload_drive(self, extract_path, destination_email):
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

            result = self._upload_folder(extract_path, 'root', uploaded_files, resume_file)
            return result
        except Exception as e:
            logging.error(f"Upload failed: {str(e)}")
            raise

    def _upload_folder(self, local_path, parent_id, uploaded_files, resume_file):
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
