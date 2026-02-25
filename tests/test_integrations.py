import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_base_class_is_importable():
    from scripts.integrations.base import IntegrationBase
    assert IntegrationBase is not None


def test_base_class_is_abstract():
    from scripts.integrations.base import IntegrationBase
    import inspect
    assert inspect.isabstract(IntegrationBase)


def test_registry_is_importable():
    from scripts.integrations import REGISTRY
    assert isinstance(REGISTRY, dict)


def test_registry_returns_integration_base_subclasses():
    """Any entries in the registry must be IntegrationBase subclasses."""
    from scripts.integrations import REGISTRY
    from scripts.integrations.base import IntegrationBase
    for name, cls in REGISTRY.items():
        assert issubclass(cls, IntegrationBase), f"{name} is not an IntegrationBase subclass"


def test_base_class_has_required_class_attributes():
    """Subclasses must define name, label, tier at the class level."""
    from scripts.integrations.base import IntegrationBase

    class ConcreteIntegration(IntegrationBase):
        name = "test"
        label = "Test Integration"
        tier = "free"

        def fields(self): return []
        def connect(self, config): return True
        def test(self): return True

    instance = ConcreteIntegration()
    assert instance.name == "test"
    assert instance.label == "Test Integration"
    assert instance.tier == "free"


def test_fields_returns_list_of_dicts():
    """fields() must return a list of dicts with key, label, type."""
    from scripts.integrations.base import IntegrationBase

    class TestIntegration(IntegrationBase):
        name = "test2"
        label = "Test 2"
        tier = "free"

        def fields(self):
            return [{"key": "token", "label": "API Token", "type": "password",
                     "placeholder": "abc", "required": True, "help": ""}]

        def connect(self, config): return bool(config.get("token"))
        def test(self): return True

    inst = TestIntegration()
    result = inst.fields()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["key"] == "token"


def test_save_and_load_config(tmp_path):
    """save_config writes yaml; load_config reads it back."""
    from scripts.integrations.base import IntegrationBase
    import yaml

    class TestIntegration(IntegrationBase):
        name = "savetest"
        label = "Save Test"
        tier = "free"
        def fields(self): return []
        def connect(self, config): return True
        def test(self): return True

    inst = TestIntegration()
    config = {"token": "abc123", "database_id": "xyz"}
    inst.save_config(config, tmp_path)

    saved_file = tmp_path / "integrations" / "savetest.yaml"
    assert saved_file.exists()

    loaded = inst.load_config(tmp_path)
    assert loaded["token"] == "abc123"
    assert loaded["database_id"] == "xyz"


def test_is_configured(tmp_path):
    from scripts.integrations.base import IntegrationBase

    class TestIntegration(IntegrationBase):
        name = "cfgtest"
        label = "Cfg Test"
        tier = "free"
        def fields(self): return []
        def connect(self, config): return True
        def test(self): return True

    assert TestIntegration.is_configured(tmp_path) is False
    # Create the file
    (tmp_path / "integrations").mkdir(parents=True)
    (tmp_path / "integrations" / "cfgtest.yaml").write_text("token: x\n")
    assert TestIntegration.is_configured(tmp_path) is True


def test_sync_default_returns_zero():
    from scripts.integrations.base import IntegrationBase

    class TestIntegration(IntegrationBase):
        name = "synctest"
        label = "Sync Test"
        tier = "free"
        def fields(self): return []
        def connect(self, config): return True
        def test(self): return True

    inst = TestIntegration()
    assert inst.sync([]) == 0
    assert inst.sync([{"id": 1}]) == 0


def test_registry_has_all_13_integrations():
    """After all modules are implemented, registry should have 13 entries."""
    from scripts.integrations import REGISTRY
    expected = {
        "notion", "google_drive", "google_sheets", "airtable",
        "dropbox", "onedrive", "mega", "nextcloud",
        "google_calendar", "apple_calendar",
        "slack", "discord", "home_assistant",
    }
    assert expected == set(REGISTRY.keys()), (
        f"Missing: {expected - set(REGISTRY.keys())}, "
        f"Extra: {set(REGISTRY.keys()) - expected}"
    )


def test_all_integrations_have_required_attributes():
    from scripts.integrations import REGISTRY
    for name, cls in REGISTRY.items():
        assert hasattr(cls, "name") and cls.name, f"{name} missing .name"
        assert hasattr(cls, "label") and cls.label, f"{name} missing .label"
        assert hasattr(cls, "tier") and cls.tier in ("free", "paid", "premium"), f"{name} invalid .tier"


def test_all_integrations_fields_schema():
    from scripts.integrations import REGISTRY
    for name, cls in REGISTRY.items():
        inst = cls()
        fields = inst.fields()
        assert isinstance(fields, list), f"{name}.fields() must return list"
        for f in fields:
            assert "key" in f, f"{name} field missing 'key'"
            assert "label" in f, f"{name} field missing 'label'"
            assert "type" in f, f"{name} field missing 'type'"
            assert f["type"] in ("text", "password", "url", "checkbox"), \
                f"{name} field type must be text/password/url/checkbox"


def test_free_integrations():
    from scripts.integrations import REGISTRY
    free_integrations = {"google_drive", "dropbox", "onedrive", "mega", "nextcloud", "discord", "home_assistant"}
    for name in free_integrations:
        assert name in REGISTRY, f"{name} not in registry"
        assert REGISTRY[name].tier == "free", f"{name} should be tier='free'"


def test_paid_integrations():
    from scripts.integrations import REGISTRY
    paid_integrations = {"notion", "google_sheets", "airtable", "google_calendar", "apple_calendar", "slack"}
    for name in paid_integrations:
        assert name in REGISTRY, f"{name} not in registry"
        assert REGISTRY[name].tier == "paid", f"{name} should be tier='paid'"
