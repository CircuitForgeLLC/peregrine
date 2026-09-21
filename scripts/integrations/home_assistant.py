from __future__ import annotations

from scripts.integrations.base import IntegrationBase


class HomeAssistantIntegration(IntegrationBase):
    name = "home_assistant"
    label = "Home Assistant"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "base_url", "label": "Home Assistant URL", "type": "url",
             "placeholder": "http://homeassistant.local:8123", "required": True,
             "help": ""},
            {"key": "token", "label": "Long-Lived Access Token", "type": "password",
             "placeholder": "eyJ0eXAiOiJKV1Qi…", "required": True,
             "help": "Profile → Long-Lived Access Tokens → Create Token"},
            {"key": "notification_service", "label": "Notification service", "type": "text",
             "placeholder": "notify.mobile_app_my_phone", "required": True,
             "help": "Developer Tools → Services → search 'notify' to find yours"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("base_url") and config.get("token"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.get(
                f"{self._config['base_url'].rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {self._config['token']}"},
                timeout=8,
            )
            return r.status_code == 200
        except Exception:  # noqa: BLE001 -- test() is a user-initiated
            # "Test Connection" check against a third-party API (Home
            # Assistant); failure modes span requests exceptions (connection
            # error, timeout, TLS -- often a self-hosted instance with a
            # self-signed cert or on a LAN address), and malformed
            # self._config access. Returning False is the intended UI
            # contract (verified: identical pattern across all 10
            # scripts/integrations/*.py test() methods). Not logging here is
            # deliberate -- this runs on every "Test" button click during
            # setup, including expected failed attempts while a user is
            # still entering credentials, so a warning log would be noisy
            # rather than informative.
            return False
