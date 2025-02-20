# Migartion-Drive-GWS-to-Other-Drive-GWS
## First, you'll need to set up authentication:
Get Google Cloud credentials file (client_secrets.json)
Place it in the appropriate directory
The app will handle token generation using the auth_manager.py flow

### First Project (Source)
1. Visit https://console.cloud.google.com
2. Click "New Project"
3. Name it "Drive-Migration-Source"
4. Click "Create"
5. Select the project
6. Go to "APIs & Services" > "Library"
7. Search for "Google Drive API"
8. Click "Enable"
9. Go to "OAuth consent screen"
10. Select "External"
11. Fill required fields:
    - App name: Drive Migration Source
    - User support email: your email
    - Developer contact email: your email
12. Click "Save and Continue"
13. Add scopes: "../auth/drive"
14. Add test users: your email
15. Go to "Credentials"
16. Click "Create Credentials" > "OAuth client ID"
17. Select "Desktop application"
18. Name it "Drive Migration Client"
19. Download JSON
20. Rename to "source_credentials.json"

### Second Project (Destination)
1. Click "New Project"
2. Name it "Drive-Migration-Destination"
3. Repeat steps 4-19 from above
4. Rename downloaded JSON to "dest_credentials.json"

## Run the main application with these commands:

python -m pip install -r requirements.txt

python src/main.py

## The application will:
List and download shared drives from source account
Handle workspace files (Docs, Sheets, Slides) with proper conversions
Preserve folder structures and sharing permissions
Upload files to destination with mapped permissions
Track progress and provide logging

## The code is designed to:
Handle large migrations reliably
Convert Google Workspace formats properly
Maintain sharing permissions between domains
Resume interrupted transfers
Provide detailed logging
