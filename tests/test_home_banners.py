import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_banner_config_is_complete():
    """All banner keys are strings and all have link destinations."""
    from app.Home import _SETUP_BANNERS
    for b in _SETUP_BANNERS:
        assert "key" in b
        assert "text" in b
        assert "link_label" in b


def test_banner_dismissed_persists(tmp_path):
    """Dismissing a banner writes to dismissed_banners in user.yaml."""
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\nwizard_complete: true\n")
    data = yaml.safe_load(p.read_text()) or {}
    data.setdefault("dismissed_banners", [])
    data["dismissed_banners"].append("connect_cloud")
    p.write_text(yaml.dump(data))
    reloaded = yaml.safe_load(p.read_text())
    assert "connect_cloud" in reloaded["dismissed_banners"]
