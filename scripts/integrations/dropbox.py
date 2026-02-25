from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class DropboxIntegration(IntegrationBase):
    name = "dropbox"
    label = "Dropbox"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "access_token", "label": "Access Token", "type": "password",
             "placeholder": "sl.…", "required": True,
             "help": "dropbox.com/developers/apps → App Console → Generate access token"},
            {"key": "folder_path", "label": "Folder path", "type": "text",
             "placeholder": "/Peregrine", "required": True,
             "help": "Dropbox folder path where resumes/cover letters will be stored"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("access_token"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {self._config['access_token']}"},
                timeout=8,
            )
            return r.status_code == 200
        except Exception:
            return False
