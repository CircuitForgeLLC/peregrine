from __future__ import annotations
from datetime import datetime, timedelta, timezone
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

    def _get_calendar(self):
        """Return the configured caldav Calendar object."""
        import caldav
        client = caldav.DAVClient(
            url=self._config["caldav_url"],
            username=self._config["username"],
            password=self._config["app_password"],
        )
        principal = client.principal()
        cal_name = self._config.get("calendar_name", "Interviews")
        for cal in principal.calendars():
            if cal.name == cal_name:
                return cal
        # Calendar not found — create it
        return principal.make_calendar(name=cal_name)

    def create_event(self, uid: str, title: str, start_dt: datetime,
                     end_dt: datetime, description: str = "") -> str:
        """Create a calendar event. Returns the UID (used as calendar_event_id)."""
        from icalendar import Calendar, Event
        cal = Calendar()
        cal.add("prodid", "-//CircuitForge Peregrine//EN")
        cal.add("version", "2.0")
        event = Event()
        event.add("uid", uid)
        event.add("summary", title)
        event.add("dtstart", start_dt)
        event.add("dtend", end_dt)
        event.add("description", description)
        cal.add_component(event)
        dav_cal = self._get_calendar()
        dav_cal.add_event(cal.to_ical().decode())
        return uid

    def update_event(self, uid: str, title: str, start_dt: datetime,
                     end_dt: datetime, description: str = "") -> str:
        """Update an existing event by UID, or create it if not found."""
        from icalendar import Calendar, Event
        dav_cal = self._get_calendar()
        try:
            existing = dav_cal.event_by_uid(uid)
            cal = Calendar()
            cal.add("prodid", "-//CircuitForge Peregrine//EN")
            cal.add("version", "2.0")
            event = Event()
            event.add("uid", uid)
            event.add("summary", title)
            event.add("dtstart", start_dt)
            event.add("dtend", end_dt)
            event.add("description", description)
            cal.add_component(event)
            existing.data = cal.to_ical().decode()
            existing.save()
        except Exception:
            return self.create_event(uid, title, start_dt, end_dt, description)
        return uid
