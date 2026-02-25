"""Step 7 — Optional integrations (cloud storage, calendars, notifications).

This step is never mandatory — validate() always returns [].
Helper functions support the wizard UI for tier-filtered integration cards.
"""
from __future__ import annotations
from pathlib import Path


def validate(data: dict) -> list[str]:
    """Integrations step is optional — never blocks Finish."""
    return []


def get_available(tier: str) -> list[str]:
    """Return list of integration names available for the given tier.

    An integration is available if the user's tier meets or exceeds the
    integration's minimum required tier (as declared by cls.tier).
    """
    from scripts.integrations import REGISTRY
    from app.wizard.tiers import TIERS

    available = []
    for name, cls in REGISTRY.items():
        try:
            if TIERS.index(tier) >= TIERS.index(cls.tier):
                available.append(name)
        except ValueError:
            pass  # unknown tier string — skip
    return available


def is_connected(name: str, config_dir: Path) -> bool:
    """Return True if a live config file exists for this integration."""
    return (config_dir / "integrations" / f"{name}.yaml").exists()
