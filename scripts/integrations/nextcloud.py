from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class NextcloudIntegration(IntegrationBase):
    name = "nextcloud"
    label = "Nextcloud"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "host", "label": "Nextcloud URL", "type": "url",
             "placeholder": "https://nextcloud.example.com", "required": True,
             "help": "Your Nextcloud server URL"},
            {"key": "username", "label": "Username", "type": "text",
             "placeholder": "your-username", "required": True,
             "help": ""},
            {"key": "password", "label": "Password / App password", "type": "password",
             "placeholder": "your-password", "required": True,
             "help": "Recommend using a Nextcloud app password for security"},
            {"key": "folder_path", "label": "Folder path", "type": "text",
             "placeholder": "/Peregrine", "required": True,
             "help": "Nextcloud WebDAV folder for resumes and cover letters"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("host") and config.get("username") and config.get("password"))

    def test(self) -> bool:
        try:
            import requests
            host = self._config["host"].rstrip("/")
            username = self._config["username"]
            folder = self._config.get("folder_path", "")
            dav_url = f"{host}/remote.php/dav/files/{username}{folder}"
            r = requests.request(
                "PROPFIND", dav_url,
                auth=(username, self._config["password"]),
                headers={"Depth": "0"},
                timeout=8,
            )
            return r.status_code in (207, 200)
        except Exception:
            return False
