from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import pickle
from config import CONFIG

class AuthManager:
    @staticmethod
    def get_drive_service(credentials_file, token_pickle):
        creds = None
        if os.path.exists(token_pickle):
            with open(token_pickle, 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, 
                    CONFIG['SCOPES'],
                    redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                )
                creds = flow.run_local_server(port=0)
                
            with open(token_pickle, 'wb') as token:
                pickle.dump(creds, token)
                
        return build('drive', 'v3', credentials=creds, cache_discovery=False)
