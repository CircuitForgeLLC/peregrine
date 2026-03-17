from __future__ import annotations
import os
from datetime import datetime
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
        try:
            service = self._build_service()
            service.calendars().get(calendarId=self._config["calendar_id"]).execute()
            return True
        except Exception:
            return False

    def _build_service(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_path = os.path.expanduser(self._config["credentials_json"])
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return build("calendar", "v3", credentials=creds)

    def _fmt(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    def create_event(self, uid: str, title: str, start_dt: datetime,
                     end_dt: datetime, description: str = "") -> str:
        """Create a Google Calendar event. Returns the Google event ID."""
        service = self._build_service()
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": self._fmt(start_dt), "timeZone": "UTC"},
            "end":   {"dateTime": self._fmt(end_dt),   "timeZone": "UTC"},
            "extendedProperties": {"private": {"peregrine_uid": uid}},
        }
        result = service.events().insert(
            calendarId=self._config["calendar_id"], body=body
        ).execute()
        return result["id"]

    def update_event(self, uid: str, title: str, start_dt: datetime,
                     end_dt: datetime, description: str = "") -> str:
        """Update an existing Google Calendar event by its stored event ID (uid is the gcal id)."""
        service = self._build_service()
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": self._fmt(start_dt), "timeZone": "UTC"},
            "end":   {"dateTime": self._fmt(end_dt),   "timeZone": "UTC"},
        }
        result = service.events().update(
            calendarId=self._config["calendar_id"], eventId=uid, body=body
        ).execute()
        return result["id"]
