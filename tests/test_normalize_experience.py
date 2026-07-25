"""Tests for dev_api._normalize_experience() format detection."""


def test_normalize_experience_resume_parser_format(monkeypatch, tmp_path):
    monkeypatch.setenv("STAGING_DB", str(tmp_path / "test.db"))
    import dev_api
    raw = [{
        "title": "Software Engineer",
        "company": "Acme Corp",
        "start_date": "2020",
        "end_date": "2023",
        "bullets": ["Built the thing", "Shipped the other thing"],
    }]
    out = dev_api._normalize_experience(raw)
    assert len(out) == 1
    entry = out[0]
    assert entry["title"] == "Software Engineer"
    assert entry["company"] == "Acme Corp"
    assert entry["period"] == "2020 - 2023"
    assert entry["responsibilities"] == "Built the thing\nShipped the other thing"
    assert entry["skills"] == []


def test_normalize_experience_resume_parser_format_no_bullets(monkeypatch, tmp_path):
    monkeypatch.setenv("STAGING_DB", str(tmp_path / "test.db"))
    import dev_api
    raw = [{
        "title": "Intern",
        "company": "Startup",
        "start_date": "2019",
        "end_date": "present",
        "bullets": [],
    }]
    out = dev_api._normalize_experience(raw)
    assert out[0]["responsibilities"] == ""
    assert out[0]["period"] == "2019 - present"


def test_normalize_experience_vue_format_passthrough(monkeypatch, tmp_path):
    monkeypatch.setenv("STAGING_DB", str(tmp_path / "test.db"))
    import dev_api
    raw = [{
        "title": "Designer",
        "company": "Acme",
        "period": "2021 - 2022",
        "responsibilities": "Designed things",
        "skills": ["Figma"],
    }]
    out = dev_api._normalize_experience(raw)
    assert out[0]["period"] == "2021 - 2022"
    assert out[0]["responsibilities"] == "Designed things"


def test_normalize_experience_aihawk_format(monkeypatch, tmp_path):
    monkeypatch.setenv("STAGING_DB", str(tmp_path / "test.db"))
    import dev_api
    raw = [{
        "position": "Engineer",
        "company": "Acme",
        "employment_period": "2018 - 2020",
        "key_responsibilities": {"1": "Did a thing"},
        "skills_acquired": ["Python"],
    }]
    out = dev_api._normalize_experience(raw)
    assert out[0]["title"] == "Engineer"
    assert out[0]["period"] == "2018 - 2020"
    assert out[0]["responsibilities"] == "Did a thing"
    assert out[0]["skills"] == ["Python"]
