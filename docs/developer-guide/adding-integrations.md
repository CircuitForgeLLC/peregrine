# Adding an Integration

Peregrine's integration system is auto-discovered — add a class and a config example, and it appears in the wizard and Settings automatically. No registration step is needed.

---

## Step 1 — Create the integration module

Create `scripts/integrations/myservice.py`:

```python
# scripts/integrations/myservice.py

from scripts.integrations.base import IntegrationBase


class MyServiceIntegration(IntegrationBase):
    name  = "myservice"      # must be unique; matches config filename
    label = "My Service"     # display name shown in the UI
    tier  = "free"           # "free" | "paid" | "premium"

    def fields(self) -> list[dict]:
        """Return form field definitions for the connection card in the wizard/Settings UI."""
        return [
            {
                "key":         "api_key",
                "label":       "API Key",
                "type":        "password",   # "text" | "password" | "url" | "checkbox"
                "placeholder": "sk-...",
                "required":    True,
                "help":        "Get your key at myservice.com/settings/api",
            },
            {
                "key":         "workspace_id",
                "label":       "Workspace ID",
                "type":        "text",
                "placeholder": "ws_abc123",
                "required":    True,
                "help":        "Found in your workspace URL",
            },
        ]

    def connect(self, config: dict) -> bool:
        """
        Store credentials in memory. Return True if all required fields are present.
        Does NOT verify credentials — call test() for that.
        """
        self._api_key      = config.get("api_key", "").strip()
        self._workspace_id = config.get("workspace_id", "").strip()
        return bool(self._api_key and self._workspace_id)

    def test(self) -> bool:
        """
        Verify the stored credentials actually work.
        Returns True on success, False on any failure.
        """
        try:
            import requests
            r = requests.get(
                "https://api.myservice.com/v1/ping",
                headers={"Authorization": f"Bearer {self._api_key}"},
                params={"workspace": self._workspace_id},
                timeout=5,
            )
            return r.ok
        except Exception:
            return False

    def sync(self, jobs: list[dict]) -> int:
        """
        Optional: push jobs to the external service.
        Return the count of successfully synced jobs.
        The default implementation in IntegrationBase returns 0 (no-op).
        Only override this if your integration supports job syncing
        (e.g. Notion, Airtable, Google Sheets).
        """
        synced = 0
        for job in jobs:
            try:
                self._push_job(job)
                synced += 1
            except Exception as e:
                print(f"[myservice] sync error for job {job.get('id')}: {e}")
        return synced

    def _push_job(self, job: dict) -> None:
        import requests
        requests.post(
            "https://api.myservice.com/v1/records",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "workspace":  self._workspace_id,
                "title":      job.get("title", ""),
                "company":    job.get("company", ""),
                "status":     job.get("status", "pending"),
                "url":        job.get("url", ""),
            },
            timeout=10,
        ).raise_for_status()
```

---

## Step 2 — Create the config example file

Create `config/integrations/myservice.yaml.example`:

```yaml
# config/integrations/myservice.yaml.example
# Copy to config/integrations/myservice.yaml and fill in your credentials.
# This file is gitignored — never commit the live credentials.
api_key: ""
workspace_id: ""
```

The live credentials file (`config/integrations/myservice.yaml`) is gitignored automatically via the `config/integrations/` entry in `.gitignore`.

---

## Step 3 — Auto-discovery

No registration step is needed. The integration registry (`scripts/integrations/__init__.py`) imports all `.py` files in the `integrations/` directory and discovers subclasses of `IntegrationBase` automatically.

On next startup, `myservice` will appear in:
- The first-run wizard Step 7 (Integrations)
- **Settings → Integrations** with a connection card rendered from `fields()`

---

## Step 4 — Tier-gate new features (optional)

If you want to gate a specific action (not just the integration itself) behind a tier, add an entry to `app/wizard/tiers.py`:

```python
FEATURES: dict[str, str] = {
    # ...existing entries...
    "myservice_sync": "paid",   # or "free" | "premium"
}
```

Then guard the action in the relevant UI page:

```python
from app.wizard.tiers import can_use
from scripts.user_profile import UserProfile

user = UserProfile()
if can_use(user.tier, "myservice_sync"):
    # show the sync button
else:
    st.info("MyService sync requires a Paid plan.")
```

---

## Step 5 — Write a test

Create or add to `tests/test_integrations.py`:

```python
# tests/test_integrations.py (add to existing file)

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from scripts.integrations.myservice import MyServiceIntegration


def test_fields_returns_required_keys():
    integration = MyServiceIntegration()
    fields = integration.fields()
    assert len(fields) >= 1
    for field in fields:
        assert "key" in field
        assert "label" in field
        assert "type" in field
        assert "required" in field


def test_connect_returns_true_with_valid_config():
    integration = MyServiceIntegration()
    result = integration.connect({"api_key": "sk-abc", "workspace_id": "ws-123"})
    assert result is True


def test_connect_returns_false_with_missing_required_field():
    integration = MyServiceIntegration()
    result = integration.connect({"api_key": "", "workspace_id": "ws-123"})
    assert result is False


def test_test_returns_true_on_200(tmp_path):
    integration = MyServiceIntegration()
    integration.connect({"api_key": "sk-abc", "workspace_id": "ws-123"})

    mock_resp = MagicMock()
    mock_resp.ok = True

    with patch("scripts.integrations.myservice.requests.get", return_value=mock_resp):
        assert integration.test() is True


def test_test_returns_false_on_error(tmp_path):
    integration = MyServiceIntegration()
    integration.connect({"api_key": "sk-abc", "workspace_id": "ws-123"})

    with patch("scripts.integrations.myservice.requests.get", side_effect=Exception("timeout")):
        assert integration.test() is False


def test_is_configured_reflects_file_presence(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "integrations").mkdir()

    assert MyServiceIntegration.is_configured(config_dir) is False

    (config_dir / "integrations" / "myservice.yaml").write_text("api_key: sk-abc\n")
    assert MyServiceIntegration.is_configured(config_dir) is True
```

---

## IntegrationBase Reference

All integrations inherit from `scripts/integrations/base.py`. Here is the full interface:

| Method / attribute | Required | Description |
|-------------------|----------|-------------|
| `name: str` | Yes | Machine key — must be unique. Matches the YAML config filename. |
| `label: str` | Yes | Human-readable display name for the UI. |
| `tier: str` | Yes | Minimum tier: `"free"`, `"paid"`, or `"premium"`. |
| `fields() -> list[dict]` | Yes | Returns form field definitions. Each dict: `key`, `label`, `type`, `placeholder`, `required`, `help`. |
| `connect(config: dict) -> bool` | Yes | Stores credentials in memory. Returns `True` if required fields are present. Does NOT verify credentials. |
| `test() -> bool` | Yes | Makes a real network call to verify stored credentials. Returns `True` on success. |
| `sync(jobs: list[dict]) -> int` | No | Pushes jobs to the external service. Returns count synced. Default is a no-op returning 0. |
| `config_path(config_dir: Path) -> Path` | Inherited | Returns `config_dir / "integrations" / f"{name}.yaml"`. |
| `is_configured(config_dir: Path) -> bool` | Inherited | Returns `True` if the config YAML file exists. |
| `save_config(config: dict, config_dir: Path)` | Inherited | Writes config dict to the YAML file. Call after `test()` returns `True`. |
| `load_config(config_dir: Path) -> dict` | Inherited | Loads and returns the YAML config, or `{}` if not configured. |

### Field type values

| `type` value | UI widget rendered |
|-------------|-------------------|
| `"text"` | Plain text input |
| `"password"` | Password input (masked) |
| `"url"` | URL input |
| `"checkbox"` | Boolean checkbox |
