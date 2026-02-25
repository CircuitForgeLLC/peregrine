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
        # TODO: use google-api-python-client to list the folder
        creds = os.path.expanduser(self._config.get("credentials_json", ""))
        return os.path.exists(creds)
