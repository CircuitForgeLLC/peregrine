from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class AppleCalendarIntegration(IntegrationBase):
    name = "apple_calendar"
    label = "Apple Calendar (CalDAV)"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "caldav_url", "label": "CalDAV URL", "type": "url",
             "placeholder": "https://caldav.icloud.com/", "required": True,
             "help": "iCloud: https://caldav.icloud.com/  |  self-hosted: your server URL"},
            {"key": "username", "label": "Apple ID / username", "type": "text",
             "placeholder": "you@icloud.com", "required": True,
             "help": ""},
            {"key": "app_password", "label": "App-Specific Password", "type": "password",
             "placeholder": "xxxx-xxxx-xxxx-xxxx", "required": True,
             "help": "appleid.apple.com → Security → App-Specific Passwords → Generate"},
            {"key": "calendar_name", "label": "Calendar name", "type": "text",
             "placeholder": "Interviews", "required": True,
             "help": "Name of the calendar to write interview events to"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(
            config.get("caldav_url") and
            config.get("username") and
            config.get("app_password")
        )

    def test(self) -> bool:
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._config["caldav_url"],
                username=self._config["username"],
                password=self._config["app_password"],
            )
            principal = client.principal()
            return principal is not None
        except Exception:
            return False
