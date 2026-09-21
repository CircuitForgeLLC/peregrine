from __future__ import annotations

from scripts.integrations.base import IntegrationBase


class DiscordIntegration(IntegrationBase):
    name = "discord"
    label = "Discord (webhook)"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "webhook_url", "label": "Webhook URL", "type": "url",
             "placeholder": "https://discord.com/api/webhooks/…", "required": True,
             "help": "Server Settings → Integrations → Webhooks → New Webhook → Copy URL"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("webhook_url"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.post(
                self._config["webhook_url"],
                json={"content": "Peregrine connected successfully."},
                timeout=8,
            )
            return r.status_code in (200, 204)
        except Exception:  # noqa: BLE001 -- test() is a user-initiated
            # "Test Connection" check against a third-party API (Discord
            # webhook); failure modes span requests exceptions (connection
            # error, timeout, TLS), and malformed self._config access.
            # Returning False is the intended UI contract (verified:
            # identical pattern across all 10 scripts/integrations/*.py
            # test() methods). Not logging here is deliberate -- this runs
            # on every "Test" button click during setup, including expected
            # failed attempts while a user is still entering credentials, so
            # a warning log would be noisy rather than informative.
            return False
