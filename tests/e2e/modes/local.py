"""Local mode config — port 8502, full features, no auth."""
from pathlib import Path
from tests.e2e.models import ModeConfig

_BASE_SETTINGS_TABS = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data",
]

LOCAL = ModeConfig(
    name="local",
    base_url="http://localhost:8502",
    auth_setup=lambda ctx: None,
    expected_failures=[],
    results_dir=Path("tests/e2e/results/local"),
    settings_tabs=_BASE_SETTINGS_TABS,
)
