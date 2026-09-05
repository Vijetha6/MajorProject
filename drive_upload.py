import logging
import os
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.pickle")


def _resolve_project_path(filepath):
    if not filepath:
        raise ValueError("A PDF file path is required for Google Drive upload.")
    if os.path.isabs(filepath):
        return filepath
    return os.path.abspath(os.path.join(BASE_DIR, filepath))


def get_drive_service():
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError("Google Drive credentials.json not found.")

    creds = None

    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, "rb") as token_file:
                creds = pickle.load(token_file)
            logger.info("✓ Loaded existing Google Drive token.pickle")
        except Exception as exc:
            logger.warning("Token file is invalid or unreadable; recreating it. Error: %s", exc)
            creds = None

    if creds and creds.valid:
        logger.info("✓ Google Drive authentication successful")
        return build("drive", "v3", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("✓ Google Drive token refreshed successfully")
            with open(TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
            logger.info("✓ Google Drive authentication successful")
            return build("drive", "v3", credentials=creds)
        except Exception as exc:
            logger.warning("Token refresh failed; starting OAuth flow. Error: %s", exc)
            creds = None

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_PATH, "wb") as token_file:
        pickle.dump(creds, token_file)

    logger.info("✓ Google Drive authentication successful")
    return build("drive", "v3", credentials=creds)


def upload_pdf_to_drive(filepath):
    resolved_path = _resolve_project_path(filepath)

    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"PDF file not found for upload: {resolved_path}")

    if os.path.getsize(resolved_path) <= 0:
        raise ValueError(f"PDF file is empty and cannot be uploaded: {resolved_path}")

    logger.info("✓ PDF upload started")
    logger.info("Uploading file: %s", resolved_path)

    service = get_drive_service()

    file_metadata = {
        "name": os.path.basename(resolved_path)
    }

    media = MediaFileUpload(
        resolved_path,
        mimetype="application/pdf",
        resumable=True
    )

    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name"
    ).execute()

    file_id = uploaded_file.get("id")
    if not file_id:
        raise RuntimeError("Google Drive upload did not return a file ID.")

    service.permissions().create(
        fileId=file_id,
        body={
            "type": "anyone",
            "role": "reader"
        }
    ).execute()

    drive_url = f"https://drive.google.com/file/d/{file_id}/view"
    logger.info("✓ PDF uploaded successfully")
    logger.info("✓ Google Drive File ID: %s", file_id)
    logger.info("✓ Google Drive URL: %s", drive_url)
    return drive_url