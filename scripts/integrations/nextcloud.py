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
        except Exception:  # noqa: BLE001 -- test() is a user-initiated
            # "Test Connection" check against a third-party API (Nextcloud
            # WebDAV); failure modes span requests exceptions (connection
            # error, timeout, TLS -- often a self-hosted instance), and
            # malformed self._config access. Returning False is the intended
            # UI contract (verified: identical pattern across all 10
            # scripts/integrations/*.py test() methods). Not logging here is
            # deliberate -- this runs on every "Test" button click during
            # setup, including expected failed attempts while a user is
            # still entering credentials, so a warning log would be noisy
            # rather than informative.
            return False
