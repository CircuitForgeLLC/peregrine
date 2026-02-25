from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class MegaIntegration(IntegrationBase):
    name = "mega"
    label = "MEGA"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "email", "label": "MEGA email", "type": "text",
             "placeholder": "you@example.com", "required": True,
             "help": "Your MEGA account email address"},
            {"key": "password", "label": "MEGA password", "type": "password",
             "placeholder": "your-mega-password", "required": True,
             "help": "Your MEGA account password"},
            {"key": "folder_path", "label": "Folder path", "type": "text",
             "placeholder": "/Peregrine", "required": True,
             "help": "MEGA folder path for resumes and cover letters"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("email") and config.get("password"))

    def test(self) -> bool:
        # TODO: use mega.py SDK to login and verify folder access
        return bool(self._config.get("email") and self._config.get("password"))
