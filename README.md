# Migartion-Drive-GWS-to-Other-Drive-GWS
##First, you'll need to set up authentication:
Get Google Cloud credentials file (client_secrets.json)
Place it in the appropriate directory
The app will handle token generation using the auth_manager.py flow

##Run the main application with these commands:

python -m pip install -r requirements.txt

python src/main.py

##The application will:
List and download shared drives from source account
Handle workspace files (Docs, Sheets, Slides) with proper conversions
Preserve folder structures and sharing permissions
Upload files to destination with mapped permissions
Track progress and provide logging

##The code is designed to:
Handle large migrations reliably
Convert Google Workspace formats properly
Maintain sharing permissions between domains
Resume interrupted transfers
Provide detailed logging
