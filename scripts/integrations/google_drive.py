from __future__ import annotations

import os

from scripts.integrations.base import IntegrationBase


class GoogleDriveIntegration(IntegrationBase):
    name = "google_drive"
    label = "Google Drive"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "folder_id", "label": "Folder ID", "type": "text",
             "placeholder": "Paste the folder ID from the Drive URL", "required": True,
             "help": "Open the folder in Drive → copy the ID from the URL after /folders/"},
            {"key": "credentials_json", "label": "Service Account JSON path", "type": "text",
             "placeholder": "~/credentials/google-drive-sa.json", "required": True,
             "help": "Download from Google Cloud Console → Service Accounts → Keys"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("folder_id") and config.get("credentials_json"))

    def test(self) -> bool:
        try:
            service = self._build_service()
            service.files().get(
                fileId=self._config["folder_id"], fields="id,name,mimeType"
            ).execute()
            return True
        except Exception:  # noqa: BLE001 -- test() is a user-initiated
            # "Test Connection" check against a third-party API (Google
            # Drive); failure modes span googleapiclient.errors.HttpError,
            # google.auth exceptions (bad/missing service-account JSON), and
            # malformed self._config access. Returning False is the intended
            # UI contract (verified: identical pattern across all 10
            # scripts/integrations/*.py test() methods). Not logging here is
            # deliberate -- this runs on every "Test" button click during
            # setup, including expected failed attempts while a user is
            # still entering credentials, so a warning log would be noisy
            # rather than informative.
            return False

    def _build_service(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_path = os.path.expanduser(self._config["credentials_json"])
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        return build("drive", "v3", credentials=creds)
