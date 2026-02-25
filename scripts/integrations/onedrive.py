from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class OneDriveIntegration(IntegrationBase):
    name = "onedrive"
    label = "OneDrive"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "client_id", "label": "Application (client) ID", "type": "text",
             "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "required": True,
             "help": "Azure portal → App registrations → your app → Application (client) ID"},
            {"key": "client_secret", "label": "Client secret", "type": "password",
             "placeholder": "your-client-secret", "required": True,
             "help": "Azure portal → your app → Certificates & secrets → New client secret"},
            {"key": "folder_path", "label": "Folder path", "type": "text",
             "placeholder": "/Peregrine", "required": True,
             "help": "OneDrive folder path for resumes and cover letters"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("client_id") and config.get("client_secret"))

    def test(self) -> bool:
        # TODO: OAuth2 token exchange via MSAL, then GET /me/drive
        # For v1, return True if required fields are present
        return bool(self._config.get("client_id") and self._config.get("client_secret"))
