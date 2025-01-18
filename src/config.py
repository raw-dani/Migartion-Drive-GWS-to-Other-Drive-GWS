import os

# Configuration settings
CONFIG = {
    'SCOPES': ['https://www.googleapis.com/auth/drive'],
    'SOURCE_CREDENTIALS_FILE': 'credentials/source_credentials.json',
    'DEST_CREDENTIALS_FILE': 'credentials/dest_credentials.json',
    'TOKEN_DIR': 'tokens',
    'TEMP_DIR': 'temp',
    'LOG_DIR': 'logs'
}

# Create required directories
for directory in [CONFIG['TOKEN_DIR'], CONFIG['TEMP_DIR'], CONFIG['LOG_DIR'], 'credentials']:
    os.makedirs(directory, exist_ok=True)
