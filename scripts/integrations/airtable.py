from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class AirtableIntegration(IntegrationBase):
    name = "airtable"
    label = "Airtable"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "api_key", "label": "Personal Access Token", "type": "password",
             "placeholder": "patXXX…", "required": True,
             "help": "airtable.com/create/tokens"},
            {"key": "base_id", "label": "Base ID", "type": "text",
             "placeholder": "appXXX…", "required": True,
             "help": "From the API docs URL"},
            {"key": "table_name", "label": "Table name", "type": "text",
             "placeholder": "Jobs", "required": True,
             "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("api_key") and config.get("base_id"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.get(
                f"https://api.airtable.com/v0/{self._config['base_id']}/{self._config.get('table_name', '')}",
                headers={"Authorization": f"Bearer {self._config['api_key']}"},
                params={"maxRecords": 1},
                timeout=8,
            )
            return r.status_code == 200
        except Exception:
            return False
