import os

# Configuration settings
CONFIG = {
    'SOURCE_CREDENTIALS_FILE': 'credentials/source_credentials.json',
    'DEST_CREDENTIALS_FILE': 'credentials/dest_credentials.json',
    'TOKEN_DIR': 'tokens',
    'TEMP_DIR': 'temp',
    'LOG_DIR': 'logs',
    'SCOPES': [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive.metadata'
    ],
    'SUPPORTED_MIME_TYPES': {
        # Documents
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.pdf': 'application/pdf',
        # Spreadsheets
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        # Presentations
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        # Images
        '.jpg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        # Audio
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        # Video
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        # shortcut
        'application/vnd.google-apps.shortcut': 'application/vnd.google-apps.shortcut',
        # Archives
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed'
    }
}


# Create required directories
for directory in [CONFIG['TOKEN_DIR'], CONFIG['TEMP_DIR'], CONFIG['LOG_DIR'], 'credentials']:
    os.makedirs(directory, exist_ok=True)
