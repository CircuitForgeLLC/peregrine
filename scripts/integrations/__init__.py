"""Integration registry — auto-discovers all IntegrationBase subclasses.

Import this module to get REGISTRY: {name: IntegrationClass}.
Integration modules are imported here; only successfully imported ones
appear in the registry.
"""
from __future__ import annotations
from scripts.integrations.base import IntegrationBase

# Import all integration modules to register their subclasses.
# Wrapped in try/except so missing modules don't break the registry.
_INTEGRATION_MODULES = [
    "scripts.integrations.notion",
    "scripts.integrations.google_drive",
    "scripts.integrations.google_sheets",
    "scripts.integrations.airtable",
    "scripts.integrations.dropbox",
    "scripts.integrations.onedrive",
    "scripts.integrations.mega",
    "scripts.integrations.nextcloud",
    "scripts.integrations.google_calendar",
    "scripts.integrations.apple_calendar",
    "scripts.integrations.slack",
    "scripts.integrations.discord",
    "scripts.integrations.home_assistant",
]

for _mod in _INTEGRATION_MODULES:
    try:
        __import__(_mod)
    except ImportError:
        pass  # module not yet implemented or missing optional dependency


def _build_registry() -> dict[str, type[IntegrationBase]]:
    """Collect all IntegrationBase subclasses that have a name attribute."""
    registry: dict[str, type[IntegrationBase]] = {}
    for cls in IntegrationBase.__subclasses__():
        if hasattr(cls, "name") and cls.name:
            registry[cls.name] = cls
    return registry


REGISTRY: dict[str, type[IntegrationBase]] = _build_registry()
