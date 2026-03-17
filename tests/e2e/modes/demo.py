"""Demo mode config — port 8504, DEMO_MODE=true, LLM/scraping neutered."""
from pathlib import Path
from tests.e2e.models import ModeConfig

_BASE_SETTINGS_TABS = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data",
]

DEMO = ModeConfig(
    name="demo",
    base_url="http://localhost:8504",
    auth_setup=lambda ctx: None,
    expected_failures=[
        "Fetch*",
        "Generate Cover Letter*",
        "Generate*",
        "Analyze Screenshot*",
        "Push to Calendar*",
        "Sync Email*",
        "Start Email Sync*",
    ],
    results_dir=Path("tests/e2e/results/demo"),
    settings_tabs=_BASE_SETTINGS_TABS,
)
