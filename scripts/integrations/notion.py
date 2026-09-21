from __future__ import annotations

from scripts.integrations.base import IntegrationBase


class NotionIntegration(IntegrationBase):
    name = "notion"
    label = "Notion"
    tier = "paid"

    def __init__(self):
        self._token = ""
        self._database_id = ""

    def fields(self) -> list[dict]:
        return [
            {"key": "token", "label": "Integration Token", "type": "password",
             "placeholder": "secret_…", "required": True,
             "help": "Settings → Connections → Develop or manage integrations → New integration"},
            {"key": "database_id", "label": "Database ID", "type": "text",
             "placeholder": "32-character ID from Notion URL", "required": True,
             "help": "Open your Notion database → Share → Copy link → extract the ID"},
        ]

    def connect(self, config: dict) -> bool:
        self._token = config.get("token", "")
        self._database_id = config.get("database_id", "")
        return bool(self._token and self._database_id)

    def test(self) -> bool:
        try:
            from notion_client import Client
            db = Client(auth=self._token).databases.retrieve(self._database_id)
            return bool(db)
        except Exception:  # noqa: BLE001 -- test() is a user-initiated
            # "Test Connection" check against a third-party API (Notion);
            # failure modes span notion_client.errors.APIResponseError
            # (bad token, missing database access), the underlying httpx
            # exceptions it wraps (connection error, timeout), and malformed
            # self._token/_database_id access. Returning False is the
            # intended UI contract (verified: identical pattern across all
            # 10 scripts/integrations/*.py test() methods). Not logging here
            # is deliberate -- this runs on every "Test" button click during
            # setup, including expected failed attempts while a user is
            # still entering credentials, so a warning log would be noisy
            # rather than informative.
            return False
