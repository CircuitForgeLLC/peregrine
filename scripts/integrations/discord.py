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
        except Exception:
            return False
