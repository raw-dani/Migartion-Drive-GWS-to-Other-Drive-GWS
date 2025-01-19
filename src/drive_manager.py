from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from tenacity import retry, stop_after_attempt, wait_exponential
import os
import io
import zipfile
import logging
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

    def download_drive(self, user_email):
        logging.info(f"Starting download for {user_email}")
        zip_path = os.path.join(CONFIG['TEMP_DIR'], f"{user_email}_drive.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            self._download_folder('root', '', zip_file)
            
        logging.info(f"Download completed for {user_email}")
        return zip_path

    def _download_folder(self, folder_id, folder_path, zip_file):
        try:
            results = self.source_service.files().list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name, mimeType)",
                pageSize=1000
            ).execute()

            for item in results.get('files', []):
                try:
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        new_path = os.path.join(folder_path, self._clean_filename(item['name']))
                        self._download_folder(item['id'], new_path, zip_file)
                    else:
                        if item['mimeType'].startswith('application/vnd.google-apps'):
                            export_formats = {
                                'application/vnd.google-apps.document': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
                                'application/vnd.google-apps.spreadsheet': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
                                'application/vnd.google-apps.presentation': ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
                                'application/vnd.google-apps.drawing': ('application/pdf', '.pdf'),
                                'application/vnd.google-apps.script': ('application/json', '.json'),
                                'application/vnd.google-apps.form': ('application/pdf', '.pdf')
                            }

                            if item['mimeType'] in export_formats:
                                export_mime, extension = export_formats[item['mimeType']]
                                request = self.source_service.files().export_media(
                                    fileId=item['id'],
                                    mimeType=export_mime
                                )
                                file_name = f"{self._clean_filename(item['name'])}{extension}"
                            else:
                                logging.warning(f"Skipping unsupported Google file type: {item['name']}")
                                continue
                        else:
                            request = self.source_service.files().get_media(
                                fileId=item['id']
                            )
                            file_name = self._clean_filename(item['name'])

                        fh = io.BytesIO()
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            if status:
                                logging.info(f"Downloading {file_name}")

                        file_path = os.path.join(folder_path, file_name)
                        zip_file.writestr(file_path, fh.getvalue())
                        logging.info(f"Downloaded: {file_name}")

                except Exception as e:
                    logging.error(f"Error downloading {item['name']}: {str(e)}")
                    continue

        except Exception as e:
            logging.error(f"Error downloading folder {folder_id}: {str(e)}")
            raise

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

                with open(resume_file, 'a') as f:
                    f.write(f"{item_path}\n")
                uploaded_files.add(item_path)
                logging.info(f"Uploaded: {item}")

            except Exception as e:
                logging.error(f"Error uploading {item}: {str(e)}")
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _retry_upload(self, request):
        return request.execute(num_retries=3)

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
