from __future__ import annotations
from scripts.integrations.base import IntegrationBase


class SlackIntegration(IntegrationBase):
    name = "slack"
    label = "Slack"
    tier = "paid"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "webhook_url", "label": "Incoming Webhook URL", "type": "url",
             "placeholder": "https://hooks.slack.com/services/…", "required": True,
             "help": "api.slack.com → Your Apps → Incoming Webhooks → Add New Webhook"},
            {"key": "channel", "label": "Channel (optional)", "type": "text",
             "placeholder": "#job-alerts", "required": False,
             "help": "Leave blank to use the webhook's default channel"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("webhook_url"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.post(
                self._config["webhook_url"],
                json={"text": "Peregrine connected successfully."},
                timeout=8,
            )
            return r.status_code == 200
        except Exception:
            return False
