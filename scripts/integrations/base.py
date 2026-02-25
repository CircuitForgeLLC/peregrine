"""Base class for all Peregrine integrations."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import yaml


class IntegrationBase(ABC):
    """All integrations inherit from this class.

    Subclasses must declare class-level attributes:
        name  : str   — machine key, matches yaml filename (e.g. "notion")
        label : str   — display name (e.g. "Notion")
        tier  : str   — minimum tier required: "free" | "paid" | "premium"
    """

    name: str
    label: str
    tier: str

    @abstractmethod
    def fields(self) -> list[dict]:
        """Return form field definitions for the wizard connection card.

        Each dict must contain:
            key         : str   — yaml key for config
            label       : str   — display label
            type        : str   — "text" | "password" | "url" | "checkbox"
            placeholder : str   — hint text
            required    : bool  — whether the field must be non-empty to connect
            help        : str   — help tooltip text
        """

    @abstractmethod
    def connect(self, config: dict) -> bool:
        """Store config in memory, return True if required fields are present.

        Does not verify credentials — call test() for that.
        """

    @abstractmethod
    def test(self) -> bool:
        """Verify the stored credentials actually work. Returns True on success."""

    def sync(self, jobs: list[dict]) -> int:
        """Push jobs to the external service. Returns count synced.

        Override in subclasses that support job syncing (e.g. Notion, Airtable).
        Default implementation is a no-op returning 0.
        """
        return 0

    @classmethod
    def config_path(cls, config_dir: Path) -> Path:
        """Return the path where this integration's config yaml is stored."""
        return config_dir / "integrations" / f"{cls.name}.yaml"

    @classmethod
    def is_configured(cls, config_dir: Path) -> bool:
        """Return True if a config file exists for this integration."""
        return cls.config_path(config_dir).exists()

    def save_config(self, config: dict, config_dir: Path) -> None:
        """Write config to config/integrations/<name>.yaml.

        Only call this after test() returns True.
        """
        path = self.config_path(config_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))

    def load_config(self, config_dir: Path) -> dict:
        """Load and return this integration's config yaml, or {} if not configured."""
        path = self.config_path(config_dir)
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}
