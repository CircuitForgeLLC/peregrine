from __future__ import annotations
import os
from scripts.integrations.base import IntegrationBase


class GoogleCalendarIntegration(IntegrationBase):
    name = "google_calendar"
    label = "Google Calendar"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "calendar_id", "label": "Calendar ID", "type": "text",
             "placeholder": "primary  or  xxxxx@group.calendar.google.com", "required": True,
             "help": "Settings → Calendars → [name] → Integrate calendar → Calendar ID"},
            {"key": "credentials_json", "label": "Service Account JSON path", "type": "text",
             "placeholder": "~/credentials/google-calendar-sa.json", "required": True,
             "help": "Download from Google Cloud Console → Service Accounts → Keys"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("calendar_id") and config.get("credentials_json"))

    def test(self) -> bool:
        # TODO: use google-api-python-client calendars().get()
        creds = os.path.expanduser(self._config.get("credentials_json", ""))
        return os.path.exists(creds)
