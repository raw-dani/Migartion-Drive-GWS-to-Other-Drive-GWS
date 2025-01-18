from drive_manager import DriveManager
from ui import main as ui_main
import logging
import shutil
import os
from config import CONFIG

def cleanup():
    """Clean up temporary files"""
    shutil.rmtree(CONFIG['TEMP_DIR'])
    os.makedirs(CONFIG['TEMP_DIR'])

def main():
    # List of user emails to migrate
    users = [
        'rohmat@domain.com'
        # Add more users as needed
    ]

    # Source and destination account mappings
    migrations = [
        {
            'source_email': 'rohmat@domain.com',
            'destination_email': 'dm01@domain.com'
        }
        # ,
        # {
        #     'source_email': 'source2@firstworkspace.com',
        #     'destination_email': 'dest2@secondworkspace.com'
        # }
    ]
    
    drive_manager = DriveManager()
    
    for migration in migrations:
        try:
            logging.info(f"=== Starting migration from {migration['source_email']} to {migration['destination_email']} ===")
            
            # Step 1: Download from source
            zip_path = drive_manager.download_drive(migration['source_email'])
            
            # Step 2: Extract
            extract_path = drive_manager.extract_drive(zip_path)
            
            # Step 3: Upload to destination
            drive_manager.upload_drive(extract_path, migration['destination_email'])
            
            logging.info(f"=== Migration completed for {migration['source_email']} to {migration['destination_email']} ===")
            
        except Exception as e:
            logging.error(f"Migration failed: {str(e)}")
            
        finally:
            cleanup()
    # for user_email in users:
    #     try:
    #         logging.info(f"=== Starting migration for {user_email} ===")
            
    #         # Step 1: Download
    #         zip_path = drive_manager.download_drive(user_email)
            
    #         # Step 2: Extract
    #         extract_path = drive_manager.extract_drive(zip_path)
            
    #         # Step 3: Upload
    #         drive_manager.upload_drive(extract_path)
            
    #         logging.info(f"=== Migration completed for {user_email} ===")
            
    #     except Exception as e:
    #         logging.error(f"Migration failed for {user_email}: {str(e)}")
            
    #     finally:
    #         cleanup()

if __name__ == "__main__":
    ui_main()
