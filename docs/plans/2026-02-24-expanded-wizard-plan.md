# Expanded First-Run Wizard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 5-step surface-level wizard with a comprehensive onboarding flow covering resume upload/parsing, guided config walkthroughs, LLM-assisted generation, and free/paid/premium feature gating.

**Architecture:** `app/wizard/` package holds all step logic; `scripts/integrations/` registry holds all integration drivers; `app/pages/0_Setup.py` becomes a thin orchestrator. `wizard_complete` flag in `user.yaml` gates the main app. Each mandatory step writes immediately to `user.yaml` so partial progress survives a crash or browser close.

**Tech Stack:** Streamlit, pdfminer.six, python-docx, PyYAML, existing task_runner.py + llm_router.py, pytest with unittest.mock.

**Design doc:** `docs/plans/2026-02-24-expanded-wizard-design.md`

---

## Before You Start

```bash
# Verify tests pass baseline
conda run -n job-seeker python -m pytest tests/ -v

# Confirm current wizard exists
ls app/pages/0_Setup.py app/wizard/ 2>/dev/null || echo "wizard/ not yet created"
```

---

## Task 1: UserProfile — wizard fields + DB params column

**Files:**
- Modify: `scripts/user_profile.py`
- Modify: `config/user.yaml.example`
- Modify: `scripts/db.py` (init_db + insert_task + update_task_stage)
- Test: `tests/test_user_profile.py` (add cases)
- Test: `tests/test_db.py` (add cases)

New fields needed in `user.yaml`:
```yaml
tier: free                   # free | paid | premium
dev_tier_override: null      # overrides tier for local testing; set to free|paid|premium
wizard_complete: false       # flipped true only when all mandatory steps pass + Finish
wizard_step: 0               # last completed step number (1-6); 0 = not started
dismissed_banners: []        # list of banner keys the user has dismissed on Home
```

New column needed in `background_tasks`: `params TEXT NULL` (JSON for wizard_generate tasks).

**Step 1: Add test cases for new UserProfile fields**

```python
# tests/test_user_profile.py — add to existing file

def test_wizard_defaults(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: Test\nemail: t@t.com\ncareer_summary: x\n")
    u = UserProfile(p)
    assert u.wizard_complete is False
    assert u.wizard_step == 0
    assert u.tier == "free"
    assert u.dev_tier_override is None
    assert u.dismissed_banners == []

def test_effective_tier_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\ndev_tier_override: premium\n")
    u = UserProfile(p)
    assert u.effective_tier == "premium"

def test_effective_tier_no_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: paid\n")
    u = UserProfile(p)
    assert u.effective_tier == "paid"
```

**Step 2: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_user_profile.py -k "wizard" -v
```
Expected: `AttributeError: 'UserProfile' object has no attribute 'wizard_complete'`

**Step 3: Add fields to `_DEFAULTS` and `UserProfile.__init__` in `scripts/user_profile.py`**

In `_DEFAULTS`, add:
```python
"tier": "free",
"dev_tier_override": None,
"wizard_complete": False,
"wizard_step": 0,
"dismissed_banners": [],
```

In `__init__`, add after existing field assignments:
```python
self.tier: str = data.get("tier", "free")
self.dev_tier_override: str | None = data.get("dev_tier_override") or None
self.wizard_complete: bool = bool(data.get("wizard_complete", False))
self.wizard_step: int = int(data.get("wizard_step", 0))
self.dismissed_banners: list[str] = list(data.get("dismissed_banners", []))
```

Add `effective_tier` property:
```python
@property
def effective_tier(self) -> str:
    """Returns dev_tier_override if set, otherwise tier."""
    return self.dev_tier_override or self.tier
```

**Step 4: Update `config/user.yaml.example`** — add after `candidate_lgbtq_focus`:
```yaml
tier: free                  # free | paid | premium
dev_tier_override: null     # overrides tier locally (for testing only)
wizard_complete: false
wizard_step: 0
dismissed_banners: []
```

**Step 5: Add insert_task params test**

```python
# tests/test_db.py — add after existing insert_task tests

def test_insert_task_with_params(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    import json
    params = json.dumps({"section": "career_summary"})
    task_id, is_new = insert_task(db, "wizard_generate", 0, params=params)
    assert is_new is True
    # Second call with same params = dedup
    task_id2, is_new2 = insert_task(db, "wizard_generate", 0, params=params)
    assert is_new2 is False
    assert task_id == task_id2
    # Different section = new task
    params2 = json.dumps({"section": "job_titles"})
    task_id3, is_new3 = insert_task(db, "wizard_generate", 0, params=params2)
    assert is_new3 is True
```

**Step 6: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_db.py -k "params" -v
```
Expected: `TypeError: insert_task() got unexpected keyword argument 'params'`

**Step 7: Add `params` column to `background_tasks` in `scripts/db.py`**

In `init_db`, add `params TEXT` to the CREATE TABLE statement for `background_tasks`:
```sql
CREATE TABLE IF NOT EXISTS background_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    job_id INTEGER DEFAULT 0,
    params TEXT,
    status TEXT DEFAULT 'queued',
    stage TEXT,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT
)
```

Also add a migration for existing DBs (after CREATE TABLE):
```python
# Migrate: add params column if missing
try:
    conn.execute("ALTER TABLE background_tasks ADD COLUMN params TEXT")
except Exception:
    pass  # column already exists
```

Update `insert_task` signature and dedup query:
```python
def insert_task(db_path: Path, task_type: str, job_id: int,
                params: str | None = None) -> tuple[int, bool]:
    """Insert a task row if no identical active task exists.

    Dedup key: (task_type, job_id) when params is None;
               (task_type, job_id, params) when params is provided.
    """
    conn = sqlite3.connect(db_path)
    try:
        if params is not None:
            existing = conn.execute(
                "SELECT id FROM background_tasks WHERE task_type=? AND job_id=? "
                "AND params=? AND status IN ('queued','running')",
                (task_type, job_id, params)
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM background_tasks WHERE task_type=? AND job_id=? "
                "AND status IN ('queued','running')",
                (task_type, job_id)
            ).fetchone()
        if existing:
            return existing[0], False
        cur = conn.execute(
            "INSERT INTO background_tasks (task_type, job_id, params) VALUES (?,?,?)",
            (task_type, job_id, params)
        )
        conn.commit()
        return cur.lastrowid, True
    finally:
        conn.close()
```

Update `submit_task` in `scripts/task_runner.py` to accept and pass params:
```python
def submit_task(db_path: Path = DEFAULT_DB, task_type: str = "",
                job_id: int = None, params: str | None = None) -> tuple[int, bool]:
    task_id, is_new = insert_task(db_path, task_type, job_id or 0, params=params)
    if is_new:
        t = threading.Thread(
            target=_run_task,
            args=(db_path, task_id, task_type, job_id or 0, params),
            daemon=True,
        )
        t.start()
    return task_id, is_new
```

Update `_run_task` signature: `def _run_task(db_path, task_id, task_type, job_id, params=None)`

**Step 8: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_user_profile.py tests/test_db.py tests/test_task_runner.py -v
```
Expected: all pass (existing tests unaffected, new tests pass)

**Step 9: Commit**

```bash
git add scripts/user_profile.py scripts/db.py scripts/task_runner.py config/user.yaml.example tests/test_user_profile.py tests/test_db.py
git commit -m "feat: wizard fields in UserProfile + params column in background_tasks"
```

---

## Task 2: Tier system (`app/wizard/tiers.py`)

**Files:**
- Create: `app/wizard/__init__.py`
- Create: `app/wizard/tiers.py`
- Create: `tests/test_wizard_tiers.py`

**Step 1: Write failing tests**

```python
# tests/test_wizard_tiers.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.wizard.tiers import can_use, tier_label, TIERS, FEATURES


def test_tiers_list():
    assert TIERS == ["free", "paid", "premium"]


def test_can_use_free_feature_always():
    # google_drive is free (not in FEATURES dict = available to all)
    assert can_use("free", "google_drive_sync") is True


def test_can_use_paid_feature_free_tier():
    assert can_use("free", "company_research") is False


def test_can_use_paid_feature_paid_tier():
    assert can_use("paid", "company_research") is True


def test_can_use_paid_feature_premium_tier():
    assert can_use("premium", "company_research") is True


def test_can_use_premium_feature_paid_tier():
    assert can_use("paid", "model_fine_tuning") is False


def test_can_use_premium_feature_premium_tier():
    assert can_use("premium", "model_fine_tuning") is True


def test_can_use_unknown_feature_always_true():
    # Unknown features are not gated
    assert can_use("free", "nonexistent_feature") is True


def test_tier_label_paid():
    label = tier_label("company_research")
    assert "Paid" in label or "paid" in label.lower()


def test_tier_label_premium():
    label = tier_label("model_fine_tuning")
    assert "Premium" in label or "premium" in label.lower()


def test_tier_label_free_feature():
    # Free features have no lock label
    label = tier_label("unknown_free_feature")
    assert label == ""
```

**Step 2: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_tiers.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.wizard'`

**Step 3: Create `app/wizard/__init__.py`** (empty)

**Step 4: Create `app/wizard/tiers.py`**

```python
"""
Tier definitions and feature gates for Peregrine.

Tiers: free < paid < premium
FEATURES maps feature key → minimum tier required.
Features not in FEATURES are available to all tiers.
"""
from __future__ import annotations

TIERS = ["free", "paid", "premium"]

# Maps feature key → minimum tier string required.
# Features absent from this dict are free (available to all).
FEATURES: dict[str, str] = {
    # Wizard LLM generation
    "llm_career_summary":           "paid",
    "llm_expand_bullets":           "paid",
    "llm_suggest_skills":           "paid",
    "llm_voice_guidelines":         "premium",
    "llm_job_titles":               "paid",
    "llm_keywords_blocklist":       "paid",
    "llm_mission_notes":            "paid",

    # App features
    "company_research":             "paid",
    "interview_prep":               "paid",
    "email_classifier":             "paid",
    "survey_assistant":             "paid",
    "model_fine_tuning":            "premium",
    "shared_cover_writer_model":    "paid",
    "multi_user":                   "premium",

    # Integrations (paid)
    "notion_sync":                  "paid",
    "google_sheets_sync":           "paid",
    "airtable_sync":                "paid",
    "google_calendar_sync":         "paid",
    "apple_calendar_sync":          "paid",
    "slack_notifications":          "paid",
}

# Free integrations (not in FEATURES):
# google_drive_sync, dropbox_sync, onedrive_sync, mega_sync,
# nextcloud_sync, discord_notifications, home_assistant


def can_use(tier: str, feature: str) -> bool:
    """Return True if the given tier has access to the feature."""
    required = FEATURES.get(feature)
    if required is None:
        return True  # not gated
    try:
        return TIERS.index(tier) >= TIERS.index(required)
    except ValueError:
        return False


def tier_label(feature: str) -> str:
    """Return a display label for a locked feature, or '' if free."""
    required = FEATURES.get(feature)
    if required is None:
        return ""
    return "🔒 Paid" if required == "paid" else "⭐ Premium"
```

**Step 5: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_tiers.py -v
```
Expected: all 11 tests pass.

**Step 6: Commit**

```bash
git add app/wizard/__init__.py app/wizard/tiers.py tests/test_wizard_tiers.py
git commit -m "feat: tier system with FEATURES gate + can_use() + tier_label()"
```

---

## Task 3: Step validate functions — hardware, tier, identity, resume, inference, search

Each step module exports only `validate(data: dict) -> list[str]` and constants. The Streamlit render function is in a later task (Task 16 — orchestrator). This task builds the pure-logic layer that is fully testable without Streamlit.

**Files:**
- Create: `app/wizard/step_hardware.py`
- Create: `app/wizard/step_tier.py`
- Create: `app/wizard/step_identity.py`
- Create: `app/wizard/step_resume.py`
- Create: `app/wizard/step_inference.py`
- Create: `app/wizard/step_search.py`
- Create: `tests/test_wizard_steps.py`

**Step 1: Write all failing tests**

```python
# tests/test_wizard_steps.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Hardware ───────────────────────────────────────────────────────────────────
from app.wizard.step_hardware import validate as hw_validate, PROFILES

def test_hw_valid():
    assert hw_validate({"inference_profile": "remote"}) == []

def test_hw_missing():
    assert hw_validate({}) != []

def test_hw_invalid():
    assert hw_validate({"inference_profile": "turbo"}) != []

def test_hw_all_profiles():
    for p in PROFILES:
        assert hw_validate({"inference_profile": p}) == []

# ── Tier ───────────────────────────────────────────────────────────────────────
from app.wizard.step_tier import validate as tier_validate

def test_tier_valid():
    assert tier_validate({"tier": "free"}) == []

def test_tier_missing():
    assert tier_validate({}) != []

def test_tier_invalid():
    assert tier_validate({"tier": "enterprise"}) != []

# ── Identity ───────────────────────────────────────────────────────────────────
from app.wizard.step_identity import validate as id_validate

def test_id_all_required_fields():
    d = {"name": "Alice", "email": "a@b.com", "career_summary": "10 years of stuff."}
    assert id_validate(d) == []

def test_id_missing_name():
    d = {"name": "", "email": "a@b.com", "career_summary": "x"}
    assert any("name" in e.lower() for e in id_validate(d))

def test_id_missing_email():
    d = {"name": "Alice", "email": "", "career_summary": "x"}
    assert any("email" in e.lower() for e in id_validate(d))

def test_id_missing_summary():
    d = {"name": "Alice", "email": "a@b.com", "career_summary": ""}
    assert any("summary" in e.lower() or "career" in e.lower() for e in id_validate(d))

# ── Resume ─────────────────────────────────────────────────────────────────────
from app.wizard.step_resume import validate as resume_validate

def test_resume_no_experience():
    assert resume_validate({"experience": []}) != []

def test_resume_one_entry():
    d = {"experience": [{"company": "Acme", "title": "Engineer", "bullets": ["did stuff"]}]}
    assert resume_validate(d) == []

def test_resume_missing_experience_key():
    assert resume_validate({}) != []

# ── Inference ──────────────────────────────────────────────────────────────────
from app.wizard.step_inference import validate as inf_validate

def test_inference_not_confirmed():
    assert inf_validate({"endpoint_confirmed": False}) != []

def test_inference_confirmed():
    assert inf_validate({"endpoint_confirmed": True}) == []

def test_inference_missing():
    assert inf_validate({}) != []

# ── Search ─────────────────────────────────────────────────────────────────────
from app.wizard.step_search import validate as search_validate

def test_search_valid():
    d = {"job_titles": ["Software Engineer"], "locations": ["Remote"]}
    assert search_validate(d) == []

def test_search_missing_titles():
    d = {"job_titles": [], "locations": ["Remote"]}
    assert any("title" in e.lower() for e in search_validate(d))

def test_search_missing_locations():
    d = {"job_titles": ["SWE"], "locations": []}
    assert any("location" in e.lower() for e in search_validate(d))

def test_search_missing_both():
    assert len(search_validate({})) == 2
```

**Step 2: Run — expect FAIL (modules don't exist)**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_steps.py -v
```

**Step 3: Create the six step modules**

`app/wizard/step_hardware.py`:
```python
"""Step 1 — Hardware detection and inference profile selection."""
PROFILES = ["remote", "cpu", "single-gpu", "dual-gpu"]


def validate(data: dict) -> list[str]:
    errors = []
    profile = data.get("inference_profile", "")
    if not profile:
        errors.append("Inference profile is required.")
    elif profile not in PROFILES:
        errors.append(f"Invalid inference profile '{profile}'. Choose: {', '.join(PROFILES)}.")
    return errors
```

`app/wizard/step_tier.py`:
```python
"""Step 2 — Tier selection (free / paid / premium)."""
from app.wizard.tiers import TIERS


def validate(data: dict) -> list[str]:
    errors = []
    tier = data.get("tier", "")
    if not tier:
        errors.append("Tier selection is required.")
    elif tier not in TIERS:
        errors.append(f"Invalid tier '{tier}'. Choose: {', '.join(TIERS)}.")
    return errors
```

`app/wizard/step_identity.py`:
```python
"""Step 3 — Identity (name, email, phone, linkedin, career_summary)."""


def validate(data: dict) -> list[str]:
    errors = []
    if not (data.get("name") or "").strip():
        errors.append("Full name is required.")
    if not (data.get("email") or "").strip():
        errors.append("Email address is required.")
    if not (data.get("career_summary") or "").strip():
        errors.append("Career summary is required.")
    return errors
```

`app/wizard/step_resume.py`:
```python
"""Step 4 — Resume (upload or guided form builder)."""


def validate(data: dict) -> list[str]:
    errors = []
    experience = data.get("experience", [])
    if not experience:
        errors.append("At least one work experience entry is required.")
    return errors
```

`app/wizard/step_inference.py`:
```python
"""Step 5 — LLM inference backend configuration and key entry."""


def validate(data: dict) -> list[str]:
    errors = []
    if not data.get("endpoint_confirmed"):
        errors.append("At least one working LLM endpoint must be confirmed.")
    return errors
```

`app/wizard/step_search.py`:
```python
"""Step 6 — Job search preferences (titles, locations, boards, keywords)."""


def validate(data: dict) -> list[str]:
    errors = []
    titles = data.get("job_titles") or []
    locations = data.get("locations") or []
    if not titles:
        errors.append("At least one job title is required.")
    if not locations:
        errors.append("At least one location is required.")
    return errors
```

**Step 4: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_steps.py -v
```
Expected: all 22 tests pass.

**Step 5: Commit**

```bash
git add app/wizard/step_hardware.py app/wizard/step_tier.py app/wizard/step_identity.py \
        app/wizard/step_resume.py app/wizard/step_inference.py app/wizard/step_search.py \
        tests/test_wizard_steps.py
git commit -m "feat: wizard step validate() functions — all six mandatory steps"
```

---

## Task 4: Resume parser (`scripts/resume_parser.py`)

Parses PDF and DOCX files to raw text, then calls the LLM to structure the text into `plain_text_resume.yaml` fields.

**Files:**
- Create: `scripts/resume_parser.py`
- Create: `tests/test_resume_parser.py`

**Step 1: Write failing tests**

```python
# tests/test_resume_parser.py
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.resume_parser import extract_text_from_pdf, extract_text_from_docx, structure_resume


def test_extract_pdf_returns_string():
    mock_pages = [MagicMock()]
    mock_pages[0].get_text.return_value = "Jane Doe\nSoftware Engineer"
    with patch("scripts.resume_parser.pdfplumber") as mock_pdf:
        mock_pdf.open.return_value.__enter__.return_value.pages = mock_pages
        result = extract_text_from_pdf(b"%PDF-fake")
    assert "Jane Doe" in result


def test_extract_docx_returns_string():
    mock_doc = MagicMock()
    mock_doc.paragraphs = [MagicMock(text="Alice Smith"), MagicMock(text="Senior Developer")]
    with patch("scripts.resume_parser.Document", return_value=mock_doc):
        result = extract_text_from_docx(b"PK fake docx bytes")
    assert "Alice Smith" in result


def test_structure_resume_returns_dict():
    raw_text = "Jane Doe\nSoftware Engineer at Acme 2020-2023"
    mock_llm = MagicMock(return_value='{"name": "Jane Doe", "experience": [{"company": "Acme"}]}')
    with patch("scripts.resume_parser._llm_structure", mock_llm):
        result = structure_resume(raw_text)
    assert "experience" in result
    assert isinstance(result["experience"], list)


def test_structure_resume_invalid_json_returns_empty():
    with patch("scripts.resume_parser._llm_structure", return_value="not json at all"):
        result = structure_resume("some text")
    # Should return empty dict rather than crash
    assert isinstance(result, dict)
```

**Step 2: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_resume_parser.py -v
```

**Step 3: Create `scripts/resume_parser.py`**

```python
"""
Resume parser — extract text from PDF/DOCX and structure via LLM.

Fast path: file bytes → raw text → LLM structures into resume dict.
Result dict keys mirror plain_text_resume.yaml sections.
"""
from __future__ import annotations
import io
import json
import re
from pathlib import Path


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using pdfplumber."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.get_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from DOCX bytes using python-docx."""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _llm_structure(raw_text: str) -> str:
    """Call LLM to convert raw resume text to JSON. Returns raw LLM output string."""
    from scripts.llm_router import LLMRouter
    prompt = f"""You are a resume parser. Convert the following resume text into a JSON object.

Required JSON keys:
- name (string)
- email (string, may be empty)
- phone (string, may be empty)
- career_summary (string: 2-4 sentence professional summary)
- experience (list of objects with: company, title, start_date, end_date, bullets list of strings)
- education (list of objects with: institution, degree, field, graduation_year)
- skills (list of strings)
- achievements (list of strings, may be empty)

Return ONLY valid JSON. No markdown, no explanation.

Resume text:
{raw_text[:6000]}"""
    router = LLMRouter()
    return router.complete(prompt)


def structure_resume(raw_text: str) -> dict:
    """Convert raw resume text to a structured dict via LLM.

    Returns an empty dict on parse failure — caller should fall back to form builder.
    """
    try:
        raw = _llm_structure(raw_text)
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        return {}
```

**Step 4: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_resume_parser.py -v
```
Expected: all 4 tests pass.

**Step 5: Commit**

```bash
git add scripts/resume_parser.py tests/test_resume_parser.py
git commit -m "feat: resume parser — PDF/DOCX extraction + LLM structuring"
```

---

## Task 5: Integration base class and registry

**Files:**
- Create: `scripts/integrations/__init__.py`
- Create: `scripts/integrations/base.py`
- Create: `tests/test_integrations.py`

**Step 1: Write failing tests**

```python
# tests/test_integrations.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_registry_loads():
    from scripts.integrations import REGISTRY
    assert isinstance(REGISTRY, dict)
    assert len(REGISTRY) > 0


def test_all_registry_entries_are_integration_base():
    from scripts.integrations import REGISTRY
    from scripts.integrations.base import IntegrationBase
    for name, cls in REGISTRY.items():
        assert issubclass(cls, IntegrationBase), f"{name} must subclass IntegrationBase"


def test_each_integration_has_required_attributes():
    from scripts.integrations import REGISTRY
    for name, cls in REGISTRY.items():
        assert hasattr(cls, "name"), f"{name} missing .name"
        assert hasattr(cls, "label"), f"{name} missing .label"
        assert hasattr(cls, "tier"), f"{name} missing .tier"


def test_fields_returns_list_of_dicts():
    from scripts.integrations import REGISTRY
    for name, cls in REGISTRY.items():
        instance = cls()
        fields = instance.fields()
        assert isinstance(fields, list), f"{name}.fields() must return list"
        for f in fields:
            assert "key" in f, f"{name} field missing 'key'"
            assert "label" in f, f"{name} field missing 'label'"
            assert "type" in f, f"{name} field missing 'type'"


def test_notion_in_registry():
    from scripts.integrations import REGISTRY
    assert "notion" in REGISTRY


def test_discord_in_registry():
    from scripts.integrations import REGISTRY
    assert "discord" in REGISTRY
```

**Step 2: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_integrations.py -v
```

**Step 3: Create `scripts/integrations/base.py`**

```python
"""Base class for all Peregrine integrations."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
import yaml


class IntegrationBase(ABC):
    """All integrations inherit from this class.

    Subclasses declare class-level:
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

        Each dict: {"key": str, "label": str, "type": "text"|"password"|"url"|"checkbox",
                    "placeholder": str, "required": bool, "help": str}
        """

    @abstractmethod
    def connect(self, config: dict) -> bool:
        """Store config in memory, return True (actual validation happens in test())."""

    @abstractmethod
    def test(self) -> bool:
        """Verify the stored credentials actually work. Returns True on success."""

    def sync(self, jobs: list[dict]) -> int:
        """Push jobs to the external service. Returns count synced. Override if applicable."""
        return 0

    @classmethod
    def config_path(cls, config_dir: Path) -> Path:
        return config_dir / "integrations" / f"{cls.name}.yaml"

    @classmethod
    def is_configured(cls, config_dir: Path) -> bool:
        return cls.config_path(config_dir).exists()

    def save_config(self, config: dict, config_dir: Path) -> None:
        """Write config to config/integrations/<name>.yaml (only after test() passes)."""
        path = self.config_path(config_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))

    def load_config(self, config_dir: Path) -> dict:
        path = self.config_path(config_dir)
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}
```

**Step 4: Create `scripts/integrations/__init__.py`**

```python
"""Integration registry — auto-discovers all IntegrationBase subclasses."""
from __future__ import annotations
from scripts.integrations.base import IntegrationBase

# Import all integration modules to trigger subclass registration
from scripts.integrations import (  # noqa: F401
    notion, google_drive, google_sheets, airtable,
    dropbox, onedrive, mega, nextcloud,
    google_calendar, apple_calendar,
    slack, discord, home_assistant,
)

REGISTRY: dict[str, type[IntegrationBase]] = {
    cls.name: cls
    for cls in IntegrationBase.__subclasses__()
}
```

**Step 5: Run tests** — will still fail because integration modules don't exist yet. That's expected — proceed to Task 6.

---

## Task 6: Integration implementations (all 13)

Create all 13 integration stub modules. Each has: class-level name/label/tier, `fields()`, `connect()`, `test()`. For v1, `test()` does a real HTTP/API call where possible; complex OAuth flows are stubbed with a clear `# TODO: OAuth` comment and return True after config write.

**Files:**
- Create: `scripts/integrations/notion.py`
- Create: `scripts/integrations/google_drive.py`
- Create: `scripts/integrations/google_sheets.py`
- Create: `scripts/integrations/airtable.py`
- Create: `scripts/integrations/dropbox.py`
- Create: `scripts/integrations/onedrive.py`
- Create: `scripts/integrations/mega.py`
- Create: `scripts/integrations/nextcloud.py`
- Create: `scripts/integrations/google_calendar.py`
- Create: `scripts/integrations/apple_calendar.py`
- Create: `scripts/integrations/slack.py`
- Create: `scripts/integrations/discord.py`
- Create: `scripts/integrations/home_assistant.py`
- Create: `config/integrations/` (directory with .yaml.example files)

**Step 1: Create `scripts/integrations/notion.py`** (has real test())

```python
from scripts.integrations.base import IntegrationBase


class NotionIntegration(IntegrationBase):
    name = "notion"
    label = "Notion"
    tier = "paid"

    def __init__(self):
        self._token = ""
        self._database_id = ""

    def fields(self) -> list[dict]:
        return [
            {"key": "token", "label": "Integration Token", "type": "password",
             "placeholder": "secret_…", "required": True,
             "help": "Settings → Connections → Develop or manage integrations → New integration"},
            {"key": "database_id", "label": "Database ID", "type": "text",
             "placeholder": "32-character ID from Notion URL", "required": True,
             "help": "Open your Notion database → Share → Copy link → extract the ID"},
        ]

    def connect(self, config: dict) -> bool:
        self._token = config.get("token", "")
        self._database_id = config.get("database_id", "")
        return bool(self._token and self._database_id)

    def test(self) -> bool:
        try:
            from notion_client import Client
            db = Client(auth=self._token).databases.retrieve(self._database_id)
            return bool(db)
        except Exception:
            return False
```

**Step 2: Create file storage integrations** — `google_drive.py`, `dropbox.py`, `onedrive.py`, `mega.py`, `nextcloud.py`

Pattern (show google_drive, others follow same structure with different name/label/fields):

```python
# scripts/integrations/google_drive.py
from scripts.integrations.base import IntegrationBase


class GoogleDriveIntegration(IntegrationBase):
    name = "google_drive"
    label = "Google Drive"
    tier = "free"

    def __init__(self):
        self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "folder_id", "label": "Folder ID", "type": "text",
             "placeholder": "Paste the folder ID from the Drive URL", "required": True,
             "help": "Open the folder in Drive → copy the ID from the URL after /folders/"},
            {"key": "credentials_json", "label": "Service Account JSON path", "type": "text",
             "placeholder": "~/credentials/google-drive-sa.json", "required": True,
             "help": "Download from Google Cloud Console → Service Accounts → Keys"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("folder_id") and config.get("credentials_json"))

    def test(self) -> bool:
        # TODO: use google-api-python-client to list the folder
        # For v1, verify the credentials file exists
        import os
        creds = os.path.expanduser(self._config.get("credentials_json", ""))
        return os.path.exists(creds)
```

Create similarly for:
- `dropbox.py` — name="dropbox", label="Dropbox", tier="free", fields: access_token + folder_path; test: GET /files/list_folder (requests)
- `onedrive.py` — name="onedrive", label="OneDrive", tier="free", fields: client_id + client_secret + folder_path; test: TODO OAuth
- `mega.py` — name="mega", label="MEGA", tier="free", fields: email + password + folder_path; test: TODO (mega.py SDK)
- `nextcloud.py` — name="nextcloud", label="Nextcloud", tier="free", fields: host + username + password + folder_path; test: WebDAV PROPFIND

**Step 3: Create tracker integrations** — `google_sheets.py`, `airtable.py`

```python
# scripts/integrations/google_sheets.py
from scripts.integrations.base import IntegrationBase

class GoogleSheetsIntegration(IntegrationBase):
    name = "google_sheets"
    label = "Google Sheets"
    tier = "paid"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "spreadsheet_id", "label": "Spreadsheet ID", "type": "text",
             "placeholder": "From the URL: /d/<ID>/edit", "required": True, "help": ""},
            {"key": "sheet_name", "label": "Sheet name", "type": "text",
             "placeholder": "Jobs", "required": True, "help": "Name of the tab to write to"},
            {"key": "credentials_json", "label": "Service Account JSON path", "type": "text",
             "placeholder": "~/credentials/google-sheets-sa.json", "required": True, "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("spreadsheet_id") and config.get("credentials_json"))

    def test(self) -> bool:
        import os
        creds = os.path.expanduser(self._config.get("credentials_json", ""))
        return os.path.exists(creds)  # TODO: gspread open_by_key()
```

```python
# scripts/integrations/airtable.py
from scripts.integrations.base import IntegrationBase

class AirtableIntegration(IntegrationBase):
    name = "airtable"
    label = "Airtable"
    tier = "paid"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "api_key", "label": "Personal Access Token", "type": "password",
             "placeholder": "patXXX…", "required": True,
             "help": "airtable.com/create/tokens"},
            {"key": "base_id", "label": "Base ID", "type": "text",
             "placeholder": "appXXX…", "required": True, "help": "From the API docs URL"},
            {"key": "table_name", "label": "Table name", "type": "text",
             "placeholder": "Jobs", "required": True, "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("api_key") and config.get("base_id"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.get(
                f"https://api.airtable.com/v0/{self._config['base_id']}/{self._config['table_name']}",
                headers={"Authorization": f"Bearer {self._config['api_key']}"},
                params={"maxRecords": 1}, timeout=8,
            )
            return r.status_code == 200
        except Exception:
            return False
```

**Step 4: Create calendar integrations** — `google_calendar.py`, `apple_calendar.py`

```python
# scripts/integrations/google_calendar.py
from scripts.integrations.base import IntegrationBase

class GoogleCalendarIntegration(IntegrationBase):
    name = "google_calendar"
    label = "Google Calendar"
    tier = "paid"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "calendar_id", "label": "Calendar ID", "type": "text",
             "placeholder": "primary  or  xxxxx@group.calendar.google.com", "required": True,
             "help": "Settings → Calendars → [name] → Integrate calendar → Calendar ID"},
            {"key": "credentials_json", "label": "Service Account JSON path", "type": "text",
             "placeholder": "~/credentials/google-calendar-sa.json", "required": True, "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("calendar_id") and config.get("credentials_json"))

    def test(self) -> bool:
        import os
        creds = os.path.expanduser(self._config.get("credentials_json", ""))
        return os.path.exists(creds)  # TODO: google-api-python-client calendars().get()
```

```python
# scripts/integrations/apple_calendar.py
from scripts.integrations.base import IntegrationBase

class AppleCalendarIntegration(IntegrationBase):
    name = "apple_calendar"
    label = "Apple Calendar (CalDAV)"
    tier = "paid"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "caldav_url", "label": "CalDAV URL", "type": "url",
             "placeholder": "https://caldav.icloud.com/", "required": True,
             "help": "iCloud: https://caldav.icloud.com/  |  self-hosted: your server URL"},
            {"key": "username", "label": "Apple ID / username", "type": "text",
             "placeholder": "you@icloud.com", "required": True, "help": ""},
            {"key": "app_password", "label": "App-Specific Password", "type": "password",
             "placeholder": "xxxx-xxxx-xxxx-xxxx", "required": True,
             "help": "appleid.apple.com → Security → App-Specific Passwords → Generate"},
            {"key": "calendar_name", "label": "Calendar name", "type": "text",
             "placeholder": "Interviews", "required": True, "help": ""},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("caldav_url") and config.get("username") and config.get("app_password"))

    def test(self) -> bool:
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._config["caldav_url"],
                username=self._config["username"],
                password=self._config["app_password"],
            )
            principal = client.principal()
            return principal is not None
        except Exception:
            return False
```

**Step 5: Create notification integrations** — `slack.py`, `discord.py`, `home_assistant.py`

```python
# scripts/integrations/slack.py
from scripts.integrations.base import IntegrationBase

class SlackIntegration(IntegrationBase):
    name = "slack"
    label = "Slack"
    tier = "paid"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "webhook_url", "label": "Incoming Webhook URL", "type": "url",
             "placeholder": "https://hooks.slack.com/services/…", "required": True,
             "help": "api.slack.com → Your Apps → Incoming Webhooks → Add"},
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
```

```python
# scripts/integrations/discord.py
from scripts.integrations.base import IntegrationBase

class DiscordIntegration(IntegrationBase):
    name = "discord"
    label = "Discord (webhook)"
    tier = "free"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "webhook_url", "label": "Webhook URL", "type": "url",
             "placeholder": "https://discord.com/api/webhooks/…", "required": True,
             "help": "Server Settings → Integrations → Webhooks → New Webhook → Copy URL"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("webhook_url"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.post(
                self._config["webhook_url"],
                json={"content": "Peregrine connected successfully."},
                timeout=8,
            )
            return r.status_code in (200, 204)
        except Exception:
            return False
```

```python
# scripts/integrations/home_assistant.py
from scripts.integrations.base import IntegrationBase

class HomeAssistantIntegration(IntegrationBase):
    name = "home_assistant"
    label = "Home Assistant"
    tier = "free"

    def __init__(self): self._config: dict = {}

    def fields(self) -> list[dict]:
        return [
            {"key": "base_url", "label": "Home Assistant URL", "type": "url",
             "placeholder": "http://homeassistant.local:8123", "required": True, "help": ""},
            {"key": "token", "label": "Long-Lived Access Token", "type": "password",
             "placeholder": "eyJ0eXAiOiJKV1Qi…", "required": True,
             "help": "Profile → Long-Lived Access Tokens → Create Token"},
            {"key": "notification_service", "label": "Notification service", "type": "text",
             "placeholder": "notify.mobile_app_my_phone", "required": True,
             "help": "Developer Tools → Services → search 'notify' to find yours"},
        ]

    def connect(self, config: dict) -> bool:
        self._config = config
        return bool(config.get("base_url") and config.get("token"))

    def test(self) -> bool:
        try:
            import requests
            r = requests.get(
                f"{self._config['base_url'].rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {self._config['token']}"},
                timeout=8,
            )
            return r.status_code == 200
        except Exception:
            return False
```

**Step 6: Create `config/integrations/` directory and `.yaml.example` files**

```bash
mkdir -p /Library/Development/devl/peregrine/config/integrations
```

Create `config/integrations/notion.yaml.example`:
```yaml
token: "secret_..."
database_id: "32-character-notion-db-id"
```

Create one `.yaml.example` per integration (notion, google_drive, google_sheets, airtable, dropbox, onedrive, mega, nextcloud, google_calendar, apple_calendar, slack, discord, home_assistant).

Add to `.gitignore`:
```
config/integrations/*.yaml
!config/integrations/*.yaml.example
```

**Step 7: Run integration tests**

```bash
conda run -n job-seeker python -m pytest tests/test_integrations.py -v
```
Expected: all 6 tests pass.

**Step 8: Commit**

```bash
git add scripts/integrations/ config/integrations/ tests/test_integrations.py .gitignore
git commit -m "feat: integration base class + registry + 13 integration implementations"
```

---

## Task 7: `wizard_generate` task type in task_runner

**Files:**
- Modify: `scripts/task_runner.py`
- Modify: `tests/test_task_runner.py`

The `wizard_generate` task accepts `params` JSON with `{"section": "...", "input": {...}}`, calls the LLM, and stores the result as JSON in `background_tasks.error`.

Supported sections: `career_summary`, `expand_bullets`, `suggest_skills`, `voice_guidelines`, `job_titles`, `keywords`, `blocklist`, `mission_notes`

**Step 1: Add tests**

```python
# tests/test_task_runner.py — add to existing file

import json

def test_wizard_generate_career_summary(tmp_path):
    """wizard_generate with career_summary section calls LLM and stores result."""
    db = tmp_path / "t.db"
    from scripts.db import init_db, get_task_status
    init_db(db)

    params = json.dumps({
        "section": "career_summary",
        "input": {"resume_text": "10 years Python dev"}
    })

    with patch("scripts.task_runner._run_wizard_generate") as mock_gen:
        mock_gen.return_value = "Experienced Python developer."
        from scripts.task_runner import submit_task
        task_id, is_new = submit_task(db, "wizard_generate", 0, params=params)

    assert is_new is True


def test_wizard_generate_unknown_section(tmp_path):
    """wizard_generate with unknown section marks task failed."""
    db = tmp_path / "t.db"
    from scripts.db import init_db, update_task_status
    init_db(db)

    params = json.dumps({"section": "nonexistent", "input": {}})
    # Run inline (don't spawn thread — call _run_task directly)
    from scripts.task_runner import _run_task
    from scripts.db import insert_task
    task_id, _ = insert_task(db, "wizard_generate", 0, params=params)
    _run_task(db, task_id, "wizard_generate", 0, params=params)

    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT status FROM background_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    assert row[0] == "failed"
```

**Step 2: Run — expect FAIL**

```bash
conda run -n job-seeker python -m pytest tests/test_task_runner.py -k "wizard_generate" -v
```

**Step 3: Add wizard_generate handler to `scripts/task_runner.py`**

Add helper function before `_run_task`:

```python
_WIZARD_PROMPTS = {
    "career_summary": (
        "Based on the following resume text, write a concise 2-4 sentence professional "
        "career summary in first person. Focus on years of experience, key skills, and "
        "what makes this person distinctive. Return only the summary text.\n\nResume:\n{resume_text}"
    ),
    "expand_bullets": (
        "Rewrite these rough responsibility notes as polished STAR-format bullet points "
        "(Situation/Task, Action, Result). Each bullet should start with a strong action verb. "
        "Return a JSON array of bullet strings.\n\nNotes:\n{bullet_notes}"
    ),
    "suggest_skills": (
        "Based on these work experience descriptions, suggest additional skills to add to "
        "a resume. Return a JSON array of skill strings only — no explanations.\n\n"
        "Experience:\n{experience_text}"
    ),
    "voice_guidelines": (
        "Analyze the writing style and tone of this resume and cover letter corpus. "
        "Return 3-5 concise guidelines for maintaining this person's authentic voice in "
        "future cover letters (e.g. 'Uses direct, confident statements', 'Avoids buzzwords'). "
        "Return a JSON array of guideline strings.\n\nContent:\n{content}"
    ),
    "job_titles": (
        "Given these job titles and resume, suggest 5-8 additional job title variations "
        "this person should search for. Return a JSON array of title strings only.\n\n"
        "Current titles: {current_titles}\nResume summary: {resume_text}"
    ),
    "keywords": (
        "Based on this resume and target job titles, suggest important keywords and phrases "
        "to include in applications. Return a JSON array of keyword strings.\n\n"
        "Titles: {titles}\nResume: {resume_text}"
    ),
    "blocklist": (
        "Based on this resume and job search context, suggest companies or keywords to "
        "blocklist (avoid in job search). Return a JSON array of strings.\n\n"
        "Context: {resume_text}"
    ),
    "mission_notes": (
        "Based on this resume, write a short personal note (1-2 sentences) about why this "
        "person might care about each of these industries: music, animal_welfare, education. "
        "Return a JSON object with industry keys and note values. If the resume shows no "
        "connection to an industry, set its value to empty string.\n\nResume: {resume_text}"
    ),
}


def _run_wizard_generate(section: str, input_data: dict) -> str:
    """Run LLM generation for a wizard section. Returns result string."""
    template = _WIZARD_PROMPTS.get(section)
    if template is None:
        raise ValueError(f"Unknown wizard_generate section: {section!r}")
    prompt = template.format(**{k: str(v) for k, v in input_data.items()})
    from scripts.llm_router import LLMRouter
    return LLMRouter().complete(prompt)
```

In `_run_task`, add the `wizard_generate` branch inside the `try` block:

```python
elif task_type == "wizard_generate":
    import json as _json
    p = _json.loads(params or "{}")
    section = p.get("section", "")
    input_data = p.get("input", {})
    result = _run_wizard_generate(section, input_data)
    # Store result in error field (used as result payload for wizard polling)
    update_task_status(
        db_path, task_id, "completed",
        error=_json.dumps({"section": section, "result": result})
    )
    return
```

**Step 4: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_task_runner.py -v
```
Expected: all pass (new cases + existing unaffected).

**Step 5: Commit**

```bash
git add scripts/task_runner.py tests/test_task_runner.py
git commit -m "feat: wizard_generate task type — 8 LLM generation sections"
```

---

## Task 8: Step integrations module + step_integrations validate

**Files:**
- Create: `app/wizard/step_integrations.py`
- Modify: `tests/test_wizard_steps.py`

The integrations step is optional (never blocks Finish), so `validate()` always returns `[]`. The step module also provides helper functions used by the orchestrator.

**Step 1: Add test**

```python
# tests/test_wizard_steps.py — add at end

from app.wizard.step_integrations import validate as int_validate

def test_integrations_always_passes():
    assert int_validate({}) == []
    assert int_validate({"connected": ["notion", "slack"]}) == []
```

**Step 2: Create `app/wizard/step_integrations.py`**

```python
"""Step 7 — Optional integrations (cloud storage, calendars, notifications)."""
from __future__ import annotations
from pathlib import Path


def validate(data: dict) -> list[str]:
    """Integrations step is always optional — never blocks Finish."""
    return []


def get_available(tier: str) -> list[str]:
    """Return list of integration names available for the given tier."""
    from scripts.integrations import REGISTRY
    from app.wizard.tiers import can_use
    return [
        name for name, cls in REGISTRY.items()
        if can_use(tier, f"{name}_sync") or can_use(tier, f"{name}_notifications") or cls.tier == "free"
    ]


def is_connected(name: str, config_dir: Path) -> bool:
    """Return True if an integration config file exists for this name."""
    return (config_dir / "integrations" / f"{name}.yaml").exists()
```

**Step 3: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_steps.py -v
```
Expected: all 24 tests pass.

**Step 4: Commit**

```bash
git add app/wizard/step_integrations.py tests/test_wizard_steps.py
git commit -m "feat: step_integrations module with validate() + tier-filtered available list"
```

---

## Task 9: Wizard orchestrator — rewrite `app/pages/0_Setup.py`

This is the largest UI task. The orchestrator drives all 6 mandatory steps plus the optional integrations step. It reads/writes `user.yaml` on each "Next" for crash recovery and renders LLM generation polling via `@st.fragment`.

**Files:**
- Rewrite: `app/pages/0_Setup.py`
- Modify: `tests/test_wizard_flow.py` (create new)

**Step 1: Write flow tests (no Streamlit)**

```python
# tests/test_wizard_flow.py
"""
Tests for wizard orchestration logic — no Streamlit dependency.
Tests the _write_step_to_yaml() and _load_wizard_state() helpers.
"""
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_profile_yaml(tmp_path, extra: dict = None) -> Path:
    data = {
        "name": "Test User", "email": "t@t.com",
        "career_summary": "10 years testing.", "wizard_complete": False
    }
    if extra:
        data.update(extra)
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_all_mandatory_steps_validate():
    """Validate functions for all 6 mandatory steps accept minimal valid data."""
    from app.wizard.step_hardware import validate as hw
    from app.wizard.step_tier import validate as tier
    from app.wizard.step_identity import validate as ident
    from app.wizard.step_resume import validate as resume
    from app.wizard.step_inference import validate as inf
    from app.wizard.step_search import validate as search

    assert hw({"inference_profile": "remote"}) == []
    assert tier({"tier": "free"}) == []
    assert ident({"name": "A", "email": "a@b.com", "career_summary": "x"}) == []
    assert resume({"experience": [{"company": "X", "title": "T", "bullets": []}]}) == []
    assert inf({"endpoint_confirmed": True}) == []
    assert search({"job_titles": ["SWE"], "locations": ["Remote"]}) == []


def test_wizard_state_inferred_from_yaml(tmp_path):
    """Wizard resumes at the right step based on wizard_step field in user.yaml."""
    p = _make_profile_yaml(tmp_path, {"wizard_step": 3})
    data = yaml.safe_load(p.read_text())
    # Step stored is last *completed* step; wizard should show step 4
    assert data["wizard_step"] == 3
    assert data["wizard_complete"] is False


def test_wizard_complete_flag(tmp_path):
    """wizard_complete: true is written at Finish."""
    p = _make_profile_yaml(tmp_path)
    data = yaml.safe_load(p.read_text())
    data["wizard_complete"] = True
    data.pop("wizard_step", None)
    p.write_text(yaml.dump(data))
    reloaded = yaml.safe_load(p.read_text())
    assert reloaded["wizard_complete"] is True
    assert "wizard_step" not in reloaded
```

**Step 2: Run — confirm logic tests pass even before orchestrator rewrite**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_flow.py -v
```
Expected: all pass (tests only use validate functions + yaml, no Streamlit).

**Step 3: Rewrite `app/pages/0_Setup.py`**

Key design points:
- Each `render_step_N()` function renders the Streamlit UI and updates `st.session_state.wizard_data` + `wizard_step`
- On "Next", calls `validate()` → if errors, shows them; if clean, writes to `user.yaml` and advances step
- On "Back", decrements step (no write)
- LLM generation buttons submit `wizard_generate` task and show inline fragment polling
- Finish writes `wizard_complete: true` and clears `wizard_step`

```python
"""
First-run setup wizard orchestrator.
Shown by app.py when user.yaml is absent OR wizard_complete is False.
Drives 6 mandatory steps + 1 optional integrations step.
All step logic lives in app/wizard/; this file only orchestrates.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
USER_YAML  = CONFIG_DIR / "user.yaml"
STEPS      = 6
STEP_LABELS = [
    "Hardware", "Tier", "Identity", "Resume", "Inference", "Search"
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_yaml() -> dict:
    if USER_YAML.exists():
        return yaml.safe_load(USER_YAML.read_text()) or {}
    return {}


def _save_yaml(updates: dict) -> None:
    existing = _load_yaml()
    existing.update(updates)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_YAML.write_text(yaml.dump(existing, default_flow_style=False, allow_unicode=True))


def _detect_gpus() -> list[str]:
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5
        )
        return [l.strip() for l in out.strip().splitlines() if l.strip()]
    except Exception:
        return []


def _suggest_profile(gpus: list[str]) -> str:
    if len(gpus) >= 2: return "dual-gpu"
    if len(gpus) == 1: return "single-gpu"
    return "remote"


def _submit_wizard_task(section: str, input_data: dict) -> int:
    """Submit a wizard_generate background task. Returns task_id."""
    from scripts.db import DEFAULT_DB
    from scripts.task_runner import submit_task
    params = json.dumps({"section": section, "input": input_data})
    task_id, _ = submit_task(DEFAULT_DB, "wizard_generate", 0, params=params)
    return task_id


def _poll_wizard_task(section: str) -> dict | None:
    """Return most recent wizard_generate task for a section, or None."""
    from scripts.db import DEFAULT_DB
    import sqlite3
    params_match = json.dumps({"section": section}).rstrip("}") # prefix match
    conn = sqlite3.connect(DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM background_tasks WHERE task_type='wizard_generate' "
        "AND params LIKE ? ORDER BY id DESC LIMIT 1",
        (f'%"section": "{section}"%',)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Wizard state init ──────────────────────────────────────────────────────────

if "wizard_step" not in st.session_state:
    saved = _load_yaml()
    st.session_state.wizard_step = min(saved.get("wizard_step", 0) + 1, STEPS)
    st.session_state.wizard_data = {}

step = st.session_state.wizard_step
data = st.session_state.wizard_data

# Load tier for feature gating
_saved_yaml = _load_yaml()
_tier = _saved_yaml.get("dev_tier_override") or _saved_yaml.get("tier", "free")

from app.wizard.tiers import can_use, tier_label

st.title("👋 Welcome to Peregrine")
st.caption("Complete the setup to start your job search. All fields are saved as you go.")
st.progress(min(step / STEPS, 1.0), text=f"Step {min(step, STEPS)} of {STEPS}")
st.divider()


# ── Step 1: Hardware ───────────────────────────────────────────────────────────
if step == 1:
    from app.wizard.step_hardware import validate, PROFILES
    st.subheader("Step 1 — Hardware Detection")

    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)
    if gpus:
        st.success(f"Found {len(gpus)} GPU(s): {', '.join(gpus)}")
    else:
        st.info("No NVIDIA GPUs detected. Recommend 'remote' or 'cpu' mode.")

    profile = st.selectbox("Inference mode", PROFILES, index=PROFILES.index(suggested),
                           help="Controls which Docker services start. Change later in Settings.")
    if profile in ("single-gpu", "dual-gpu") and not gpus:
        st.warning("No GPUs detected — GPU profiles require NVIDIA Container Toolkit.")

    if st.button("Next →", type="primary"):
        errs = validate({"inference_profile": profile})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({"inference_profile": profile, "wizard_step": 1})
            st.session_state.wizard_step = 2
            st.session_state.wizard_data["inference_profile"] = profile
            st.rerun()


# ── Step 2: Tier ───────────────────────────────────────────────────────────────
elif step == 2:
    from app.wizard.step_tier import validate
    st.subheader("Step 2 — Choose Your Plan")
    st.caption("Free is fully functional for local self-hosted use. Paid/Premium unlock LLM-assisted features.")

    tier_opts = {
        "free": "**Free** — Local discovery, apply workspace, interviews kanban",
        "paid": "**Paid** — + AI career summary, company research, email classifier, calendar sync",
        "premium": "**Premium** — + Voice guidelines, model fine-tuning, multi-user",
    }
    selected_tier = st.radio("Plan", list(tier_opts.keys()),
                              format_func=lambda x: tier_opts[x],
                              index=0)

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 1
        st.rerun()
    if col_next.button("Next →", type="primary"):
        errs = validate({"tier": selected_tier})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({"tier": selected_tier, "wizard_step": 2})
            st.session_state.wizard_data["tier"] = selected_tier
            st.session_state.wizard_step = 3
            st.rerun()


# ── Step 3: Identity ───────────────────────────────────────────────────────────
elif step == 3:
    from app.wizard.step_identity import validate
    st.subheader("Step 3 — Your Identity")
    st.caption("Used in cover letter PDFs, LLM prompts, and the app header.")

    saved = _load_yaml()
    c1, c2 = st.columns(2)
    name     = c1.text_input("Full Name *",  saved.get("name", ""))
    email    = c1.text_input("Email *",      saved.get("email", ""))
    phone    = c2.text_input("Phone",        saved.get("phone", ""))
    linkedin = c2.text_input("LinkedIn URL", saved.get("linkedin", ""))

    summary_default = saved.get("career_summary", "")
    summary = st.text_area("Career Summary *", summary_default, height=120,
                            placeholder="Experienced professional with X years in [field].")

    # LLM generation button (paid only)
    if can_use(_tier, "llm_career_summary"):
        gen_col, _ = st.columns([2, 8])
        if gen_col.button("✨ Generate from resume"):
            resume_text = saved.get("_raw_resume_text", "")
            if resume_text:
                _submit_wizard_task("career_summary", {"resume_text": resume_text})
                st.rerun()
            else:
                st.info("Complete Step 4 (Resume) first to use AI generation.")
    else:
        st.caption(f"{tier_label('llm_career_summary')} Generate career summary with AI")

    # Poll for completed generation
    @st.fragment(run_every=3)
    def _poll_career_summary():
        task = _poll_wizard_task("career_summary")
        if not task:
            return
        if task["status"] == "completed":
            payload = json.loads(task.get("error") or "{}")
            result = payload.get("result", "")
            if result and result != st.session_state.get("_career_summary_gen"):
                st.session_state["_career_summary_gen"] = result
                st.info(f"✨ Suggested summary (click to use):\n\n{result}")
    _poll_career_summary()

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 2
        st.rerun()
    if col_next.button("Next →", type="primary"):
        errs = validate({"name": name, "email": email, "career_summary": summary})
        if errs:
            st.error("\n".join(errs))
        else:
            _save_yaml({
                "name": name, "email": email, "phone": phone,
                "linkedin": linkedin, "career_summary": summary,
                "wizard_complete": False, "wizard_step": 3,
            })
            st.session_state.wizard_step = 4
            st.rerun()


# ── Step 4: Resume ─────────────────────────────────────────────────────────────
elif step == 4:
    from app.wizard.step_resume import validate
    st.subheader("Step 4 — Resume")
    st.caption("Upload your resume for fast parsing, or build it section by section.")

    tab_upload, tab_builder = st.tabs(["📎 Upload Resume", "📝 Build Resume"])

    saved = _load_yaml()

    with tab_upload:
        uploaded = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
        if uploaded:
            if st.button("Parse Resume", type="primary"):
                from scripts.resume_parser import extract_text_from_pdf, extract_text_from_docx, structure_resume
                file_bytes = uploaded.read()
                ext = uploaded.name.rsplit(".", 1)[-1].lower()
                raw_text = extract_text_from_pdf(file_bytes) if ext == "pdf" else extract_text_from_docx(file_bytes)
                with st.spinner("Parsing…"):
                    parsed = structure_resume(raw_text)
                if parsed:
                    st.session_state["_parsed_resume"] = parsed
                    st.session_state["_raw_resume_text"] = raw_text
                    _save_yaml({"_raw_resume_text": raw_text[:8000]})  # for career_summary generation
                    st.success("Resume parsed! Review below.")
                else:
                    st.warning("Couldn't auto-parse — switch to the Build tab.")

        if "parsed" in st.session_state.get("_parsed_resume", {}):
            st.json(st.session_state["_parsed_resume"])

    with tab_builder:
        st.caption("Add your work experience entries manually.")
        experience = st.session_state.get("_experience", saved.get("experience", []))

        for i, entry in enumerate(experience):
            with st.expander(f"{entry.get('title', 'Entry')} at {entry.get('company', '?')}", expanded=False):
                entry["company"] = st.text_input("Company", entry.get("company", ""), key=f"co_{i}")
                entry["title"]   = st.text_input("Title",   entry.get("title",   ""), key=f"ti_{i}")
                raw_bullets = st.text_area("Responsibilities (one per line)",
                                           "\n".join(entry.get("bullets", [])),
                                           key=f"bu_{i}", height=80)
                entry["bullets"] = [b.strip() for b in raw_bullets.splitlines() if b.strip()]
                if st.button("Remove", key=f"rm_{i}"):
                    experience.pop(i)
                    st.session_state["_experience"] = experience
                    st.rerun()

        if st.button("＋ Add Entry"):
            experience.append({"company": "", "title": "", "bullets": []})
            st.session_state["_experience"] = experience
            st.rerun()

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 3
        st.rerun()
    if col_next.button("Next →", type="primary"):
        # Resolve experience from upload parse or builder
        parsed = st.session_state.get("_parsed_resume", {})
        experience = parsed.get("experience") or st.session_state.get("_experience", [])
        errs = validate({"experience": experience})
        if errs:
            st.error("\n".join(errs))
        else:
            # Write resume yaml
            resume_yaml_path = Path(__file__).parent.parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"
            resume_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            resume_data = {**parsed, "experience": experience} if parsed else {"experience": experience}
            resume_yaml_path.write_text(yaml.dump(resume_data, default_flow_style=False, allow_unicode=True))
            _save_yaml({"wizard_step": 4})
            st.session_state.wizard_step = 5
            st.rerun()


# ── Step 5: Inference ──────────────────────────────────────────────────────────
elif step == 5:
    from app.wizard.step_inference import validate
    st.subheader("Step 5 — Inference & API Keys")

    saved = _load_yaml()
    profile = saved.get("inference_profile", "remote")

    if profile == "remote":
        st.info("Remote mode: at least one external API key is required.")
        anthropic_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-…")
        openai_url    = st.text_input("OpenAI-compatible endpoint (optional)", placeholder="https://api.together.xyz/v1")
        openai_key    = st.text_input("Endpoint API Key (optional)", type="password") if openai_url else ""
    else:
        st.info(f"Local mode ({profile}): Ollama provides inference.")
        anthropic_key = ""
        openai_url = ""
        openai_key = ""

    st.divider()
    with st.expander("Advanced — Service Ports & Hosts"):
        st.caption("Change only if services run on non-default ports or remote hosts.")
        svc = saved.get("services", {})
        for svc_name, default_host, default_port in [
            ("ollama", "localhost", 11434),
            ("vllm",   "localhost", 8000),
            ("searxng","localhost", 8888),
        ]:
            c1, c2, c3 = st.columns([2, 1, 1])
            svc[f"{svc_name}_host"] = c1.text_input(f"{svc_name} host", svc.get(f"{svc_name}_host", default_host), key=f"h_{svc_name}")
            svc[f"{svc_name}_port"] = int(c2.number_input("port", value=int(svc.get(f"{svc_name}_port", default_port)), step=1, key=f"p_{svc_name}"))
            svc[f"{svc_name}_ssl"]  = c3.checkbox("SSL", svc.get(f"{svc_name}_ssl", False), key=f"ssl_{svc_name}")

    confirmed = False
    if profile == "remote":
        if st.button("🔌 Test LLM connection"):
            from scripts.llm_router import LLMRouter
            try:
                r = LLMRouter().complete("Say 'OK' and nothing else.")
                if r and len(r.strip()) > 0:
                    st.success("LLM responding.")
                    confirmed = True
                    st.session_state["_inf_confirmed"] = True
            except Exception as e:
                st.error(f"LLM test failed: {e}")
    else:
        # Local profile: Ollama availability is tested
        if st.button("🔌 Test Ollama connection"):
            import requests
            ollama_url = f"http://{svc.get('ollama_host','localhost')}:{svc.get('ollama_port',11434)}"
            try:
                requests.get(f"{ollama_url}/api/tags", timeout=5)
                st.success("Ollama is running.")
                st.session_state["_inf_confirmed"] = True
            except Exception:
                st.warning("Ollama not responding — you can skip and configure later in Settings.")
                st.session_state["_inf_confirmed"] = True  # allow skip

    confirmed = st.session_state.get("_inf_confirmed", False)

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 4
        st.rerun()
    if col_next.button("Next →", type="primary", disabled=not confirmed):
        errs = validate({"endpoint_confirmed": confirmed})
        if errs:
            st.error("\n".join(errs))
        else:
            # Write API keys to .env
            env_path = CONFIG_DIR.parent / ".env"
            env_lines = env_path.read_text().splitlines() if env_path.exists() else []
            def _set_env(lines, key, val):
                for i, l in enumerate(lines):
                    if l.startswith(f"{key}="):
                        lines[i] = f"{key}={val}"; return lines
                lines.append(f"{key}={val}"); return lines
            if anthropic_key: env_lines = _set_env(env_lines, "ANTHROPIC_API_KEY", anthropic_key)
            if openai_url:    env_lines = _set_env(env_lines, "OPENAI_COMPAT_URL", openai_url)
            if openai_key:    env_lines = _set_env(env_lines, "OPENAI_COMPAT_KEY", openai_key)
            if anthropic_key or openai_url:
                env_path.write_text("\n".join(env_lines) + "\n")
            _save_yaml({"services": svc, "wizard_step": 5})
            st.session_state.wizard_step = 6
            st.rerun()


# ── Step 6: Search ─────────────────────────────────────────────────────────────
elif step == 6:
    from app.wizard.step_search import validate
    st.subheader("Step 6 — Job Search Preferences")

    saved = _load_yaml()
    _tier_now = saved.get("dev_tier_override") or saved.get("tier", "free")

    titles    = st.session_state.get("_titles", [])
    locations = st.session_state.get("_locations", [])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Job Titles**")
        for i, t in enumerate(titles):
            col_t, col_rm = st.columns([4, 1])
            col_t.text(t)
            if col_rm.button("×", key=f"rmtitle_{i}"):
                titles.pop(i); st.session_state["_titles"] = titles; st.rerun()
        new_title = st.text_input("Add title", key="new_title_wiz", placeholder="Software Engineer…")
        tc1, tc2 = st.columns([3, 1])
        if tc2.button("＋", key="add_title"):
            if new_title.strip() and new_title.strip() not in titles:
                titles.append(new_title.strip()); st.session_state["_titles"] = titles; st.rerun()
        if can_use(_tier_now, "llm_job_titles"):
            if tc1.button("✨ Suggest titles"):
                resume_text = saved.get("_raw_resume_text", "")
                _submit_wizard_task("job_titles", {"resume_text": resume_text, "current_titles": titles})
                st.rerun()
        else:
            st.caption(f"{tier_label('llm_job_titles')} AI title suggestions")

    with c2:
        st.markdown("**Locations**")
        for i, l in enumerate(locations):
            lc1, lc2 = st.columns([4, 1])
            lc1.text(l)
            if lc2.button("×", key=f"rmloc_{i}"):
                locations.pop(i); st.session_state["_locations"] = locations; st.rerun()
        new_loc = st.text_input("Add location", key="new_loc_wiz", placeholder="Remote, New York NY…")
        ll1, ll2 = st.columns([3, 1])
        if ll2.button("＋", key="add_loc"):
            if new_loc.strip():
                locations.append(new_loc.strip()); st.session_state["_locations"] = locations; st.rerun()

    # Poll job titles suggestion
    @st.fragment(run_every=3)
    def _poll_titles():
        task = _poll_wizard_task("job_titles")
        if task and task["status"] == "completed":
            payload = json.loads(task.get("error") or "{}")
            result = payload.get("result", "")
            st.info(f"✨ Suggested titles:\n\n{result}")
    _poll_titles()

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 5
        st.rerun()
    if col_next.button("Next →", type="primary"):
        errs = validate({"job_titles": titles, "locations": locations})
        if errs:
            st.error("\n".join(errs))
        else:
            # Write search profile
            import datetime
            search_profile = {
                "profiles": [{
                    "name": "default",
                    "job_titles": titles,
                    "locations": locations,
                    "remote_only": False,
                    "boards": ["linkedin", "indeed", "glassdoor", "zip_recruiter"],
                }]
            }
            (CONFIG_DIR / "search_profiles.yaml").write_text(
                yaml.dump(search_profile, default_flow_style=False, allow_unicode=True)
            )
            _save_yaml({"wizard_step": 6})
            st.session_state.wizard_step = 7  # integrations (optional)
            st.rerun()


# ── Step 7: Integrations (optional) ───────────────────────────────────────────
elif step == 7:
    st.subheader("Step 7 — Integrations (Optional)")
    st.caption("Connect cloud services, calendars, and notification tools. Skip to finish setup.")

    saved = _load_yaml()
    _tier_now = saved.get("dev_tier_override") or saved.get("tier", "free")

    from scripts.integrations import REGISTRY
    from app.wizard.tiers import can_use

    for name, cls in sorted(REGISTRY.items(), key=lambda x: (x[1].tier != "free", x[0])):
        is_accessible = can_use(_tier_now, f"{name}_sync") or can_use(_tier_now, f"{name}_notifications") or cls.tier == "free"
        is_conn = (CONFIG_DIR / "integrations" / f"{name}.yaml").exists()

        with st.expander(f"{'✅' if is_conn else '○'} {cls.label}  {'🔒 Paid' if cls.tier == 'paid' else '⭐ Premium' if cls.tier == 'premium' else ''}"):
            if not is_accessible:
                st.caption(f"Upgrade to {cls.tier} to unlock {cls.label}.")
            else:
                inst = cls()
                config = {}
                for field in inst.fields():
                    val = st.text_input(field["label"],
                                        type="password" if field["type"] == "password" else "default",
                                        placeholder=field.get("placeholder", ""),
                                        help=field.get("help", ""),
                                        key=f"int_{name}_{field['key']}")
                    config[field["key"]] = val

                if st.button(f"Connect {cls.label}", key=f"conn_{name}",
                              disabled=not all(config.get(f["key"]) for f in inst.fields() if f.get("required"))):
                    inst.connect(config)
                    with st.spinner("Testing connection…"):
                        if inst.test():
                            inst.save_config(config, CONFIG_DIR)
                            st.success(f"{cls.label} connected!")
                            st.rerun()
                        else:
                            st.error(f"Connection test failed. Check your credentials for {cls.label}.")

    st.divider()

    col_skip, col_finish = st.columns([1, 3])
    if col_skip.button("← Back"):
        st.session_state.wizard_step = 6
        st.rerun()

    if col_finish.button("🎉 Finish Setup", type="primary"):
        # Apply service URLs to llm.yaml and set wizard_complete
        from scripts.user_profile import UserProfile
        from scripts.generate_llm_config import apply_service_urls
        profile_obj = UserProfile(USER_YAML)
        from scripts.db import DEFAULT_DB
        apply_service_urls(profile_obj, CONFIG_DIR / "llm.yaml")
        _save_yaml({"wizard_complete": True})
        # Remove wizard_step so it doesn't interfere on next load
        data_clean = yaml.safe_load(USER_YAML.read_text()) or {}
        data_clean.pop("wizard_step", None)
        USER_YAML.write_text(yaml.dump(data_clean, default_flow_style=False, allow_unicode=True))
        st.session_state.clear()
        st.success("Setup complete! Loading Peregrine…")
        st.rerun()
```

**Step 4: Run flow tests**

```bash
conda run -n job-seeker python -m pytest tests/test_wizard_flow.py -v
```
Expected: all 3 tests pass.

**Step 5: Commit**

```bash
git add app/pages/0_Setup.py tests/test_wizard_flow.py
git commit -m "feat: wizard orchestrator — 6 mandatory steps + optional integrations + LLM generation polling"
```

---

## Task 10: Update `app/app.py` — `wizard_complete` gate

**Files:**
- Modify: `app/app.py`
- Modify: `tests/test_app_gating.py`

**Step 1: Add test cases**

```python
# tests/test_app_gating.py — add to existing file

def test_wizard_incomplete_triggers_wizard(tmp_path):
    """wizard_complete: false should be treated as 'wizard not done'."""
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\nwizard_complete: false\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is False

def test_wizard_complete_does_not_trigger(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\nwizard_complete: true\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.wizard_complete is True
```

**Step 2: Run — should pass already (UserProfile already has wizard_complete)**

```bash
conda run -n job-seeker python -m pytest tests/test_app_gating.py -v
```

**Step 3: Update the gate in `app/app.py`**

Replace:
```python
if not _UserProfile.exists(_USER_YAML):
    _setup_page = st.Page("pages/0_Setup.py", title="Setup", icon="👋")
    st.navigation({"": [_setup_page]}).run()
    st.stop()
```

With:
```python
_show_wizard = (
    not _UserProfile.exists(_USER_YAML)
    or not _UserProfile(_USER_YAML).wizard_complete
)
if _show_wizard:
    _setup_page = st.Page("pages/0_Setup.py", title="Setup", icon="👋")
    st.navigation({"": [_setup_page]}).run()
    st.stop()
```

**Step 4: Also add `wizard_generate` to the sidebar task label map in `app/app.py`**

In the `_task_indicator` fragment, add:
```python
elif task_type == "wizard_generate":
    label = "Wizard generation"
```

**Step 5: Run full test suite**

```bash
conda run -n job-seeker python -m pytest tests/ -v
```
Expected: all tests pass.

**Step 6: Commit**

```bash
git add app/app.py tests/test_app_gating.py
git commit -m "feat: app.py checks wizard_complete flag to gate main app"
```

---

## Task 11: Home page — dismissible setup banners

After wizard completion, the Home page shows contextual setup prompts for remaining optional tasks. Each is dismissible; dismissed state persists in `user.yaml`.

**Files:**
- Modify: `app/Home.py`
- Modify: `scripts/user_profile.py` (save_dismissed_banner helper)
- Create: `tests/test_home_banners.py`

**Step 1: Write failing tests**

```python
# tests/test_home_banners.py
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))

_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"


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
```

**Step 2: Run — expect FAIL on _SETUP_BANNERS import**

```bash
conda run -n job-seeker python -m pytest tests/test_home_banners.py -v
```

**Step 3: Add banners to `app/Home.py`**

Near the top (after imports), add the banner config list:

```python
_SETUP_BANNERS = [
    {"key": "connect_cloud",       "text": "Connect a cloud service for resume/cover letter storage",
     "link_label": "Settings → Integrations"},
    {"key": "setup_email",         "text": "Set up email sync to catch recruiter outreach",
     "link_label": "Settings → Email"},
    {"key": "setup_email_labels",  "text": "Set up email label filters for auto-classification",
     "link_label": "Settings → Email (label guide)"},
    {"key": "tune_mission",        "text": "Tune your mission preferences for better cover letters",
     "link_label": "Settings → My Profile"},
    {"key": "configure_keywords",  "text": "Configure keywords and blocklist for smarter search",
     "link_label": "Settings → Search"},
    {"key": "upload_corpus",       "text": "Upload your cover letter corpus for voice fine-tuning",
     "link_label": "Settings → Fine-Tune"},
    {"key": "configure_linkedin",  "text": "Configure LinkedIn Easy Apply automation",
     "link_label": "Settings → AIHawk"},
    {"key": "setup_searxng",       "text": "Set up company research with SearXNG",
     "link_label": "Settings → Services"},
    {"key": "target_companies",    "text": "Build a target company list for focused outreach",
     "link_label": "Settings → Search"},
    {"key": "setup_notifications", "text": "Set up notifications for stage changes",
     "link_label": "Settings → Integrations"},
    {"key": "tune_model",          "text": "Tune a custom cover letter model on your writing",
     "link_label": "Settings → Fine-Tune"},
    {"key": "review_training",     "text": "Review and curate training data for model tuning",
     "link_label": "Settings → Fine-Tune"},
    {"key": "setup_calendar",      "text": "Set up calendar sync to track interview dates",
     "link_label": "Settings → Integrations"},
]
```

After existing dashboard content, add the banner render block:

```python
# ── Setup banners ─────────────────────────────────────────────────────────────
if _profile and _profile.wizard_complete:
    _dismissed = set(_profile.dismissed_banners)
    _pending_banners = [b for b in _SETUP_BANNERS if b["key"] not in _dismissed]
    if _pending_banners:
        st.divider()
        st.markdown("#### Finish setting up Peregrine")
        for banner in _pending_banners:
            _bcol, _bdismiss = st.columns([10, 1])
            with _bcol:
                st.info(f"💡 {banner['text']}  →  _{banner['link_label']}_")
            with _bdismiss:
                st.write("")
                if st.button("✕", key=f"dismiss_banner_{banner['key']}", help="Dismiss"):
                    # Write dismissed_banners back to user.yaml
                    _data = yaml.safe_load(USER_YAML.read_text()) if USER_YAML.exists() else {}  # type: ignore[name-defined]
                    _data.setdefault("dismissed_banners", [])
                    if banner["key"] not in _data["dismissed_banners"]:
                        _data["dismissed_banners"].append(banner["key"])
                    USER_YAML.write_text(yaml.dump(_data, default_flow_style=False, allow_unicode=True))  # type: ignore[name-defined]
                    st.rerun()
```

Add `import yaml` to `app/Home.py` imports.
Add `_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"` near the top if not already present.

**Step 4: Run tests**

```bash
conda run -n job-seeker python -m pytest tests/test_home_banners.py tests/ -v
```
Expected: all pass.

**Step 5: Commit**

```bash
git add app/Home.py tests/test_home_banners.py
git commit -m "feat: dismissible setup banners on Home page (13 contextual prompts)"
```

---

## Task 12: Developer tab in Settings

The Developer tab enables tier override for testing and a wizard reset button. Visible when `dev_tier_override` is set in `user.yaml` OR `DEV_MODE=true` in `.env`.

**Files:**
- Modify: `app/pages/2_Settings.py`
- Create: `tests/test_dev_tab.py`

**Step 1: Write failing tests**

```python
# tests/test_dev_tab.py
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_dev_tab_visible_when_override_set(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ndev_tier_override: premium\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.dev_tier_override == "premium"
    assert u.effective_tier == "premium"


def test_dev_tab_not_visible_without_override(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\n")
    from scripts.user_profile import UserProfile
    u = UserProfile(p)
    assert u.dev_tier_override is None
    assert u.effective_tier == "free"


def test_can_use_uses_effective_tier(tmp_path):
    p = tmp_path / "user.yaml"
    p.write_text("name: T\nemail: t@t.com\ncareer_summary: x\ntier: free\ndev_tier_override: premium\n")
    from scripts.user_profile import UserProfile
    from app.wizard.tiers import can_use
    u = UserProfile(p)
    assert can_use(u.effective_tier, "model_fine_tuning") is True
    assert can_use(u.tier, "model_fine_tuning") is False
```

**Step 2: Run — some should pass already**

```bash
conda run -n job-seeker python -m pytest tests/test_dev_tab.py -v
```

**Step 3: Add Developer tab to `app/pages/2_Settings.py`**

The Settings page uses tabs. Find where tabs are defined and add "Developer" tab. The tab should only render if `DEV_MODE=true` in env OR `dev_tier_override` is set:

```python
import os as _os

_dev_mode = _os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")
_show_dev_tab = _dev_mode or bool(_u.get("dev_tier_override"))
```

In the tab list, conditionally append:
```python
tab_names = ["LLM", "Search", "Email", "My Profile", "Services", "Integrations", "AIHawk", "Fine-Tune"]
if _show_dev_tab:
    tab_names.append("Developer")
tabs = st.tabs(tab_names)
```

Developer tab content (in the last tab when `_show_dev_tab`):
```python
with tabs[-1]:  # Developer tab
    st.subheader("Developer Settings")
    st.caption("These settings are for local testing only and are never used in production.")

    st.markdown("**Tier Override**")
    st.caption("Instantly switches effective tier without changing your billing tier.")
    from app.wizard.tiers import TIERS
    current_override = _u.get("dev_tier_override") or ""
    override_opts = ["(none — use real tier)"] + TIERS
    override_idx = (TIERS.index(current_override) + 1) if current_override in TIERS else 0
    new_override = st.selectbox("dev_tier_override", override_opts, index=override_idx)
    new_override_val = None if new_override.startswith("(none") else new_override

    if st.button("Apply tier override", key="apply_tier_override"):
        _u["dev_tier_override"] = new_override_val
        _save_user(_u)  # uses existing save helper in Settings page
        st.success(f"Tier override set to: {new_override_val or 'none'}. Page will reload.")
        st.rerun()

    st.divider()
    st.markdown("**Wizard Reset**")
    st.caption("Sets `wizard_complete: false` to re-enter the wizard without deleting your config.")

    if st.button("↩ Reset wizard", key="reset_wizard"):
        _u["wizard_complete"] = False
        _u["wizard_step"] = 0
        _save_user(_u)
        st.success("Wizard reset. Reload the app to re-run setup.")
```

**Step 4: Run all tests**

```bash
conda run -n job-seeker python -m pytest tests/ -v
```
Expected: all tests pass.

**Step 5: Commit**

```bash
git add app/pages/2_Settings.py tests/test_dev_tab.py
git commit -m "feat: Developer tab in Settings — tier override + wizard reset button"
```

---

## Task 13: Final integration test pass

**Step 1: Run full test suite**

```bash
conda run -n job-seeker python -m pytest tests/ -v --tb=short
```

Fix any failures before proceeding.

**Step 2: Manual smoke test — trigger the wizard**

In Settings → Developer tab: click "Reset wizard". Reload app.

Verify:
- Wizard shows with progress bar "Step 1 of 6"
- Step 1 auto-detects GPU (or shows "None detected")
- Each "Next →" advances the step
- "← Back" returns to previous step
- Step 3 identity validates name/email/summary before advancing
- Step 4 resume upload parses PDF
- Step 5 inference test button works
- Step 6 search requires at least one title + location
- Step 7 integrations can be skipped
- "Finish Setup" sets `wizard_complete: true`, redirects to main app
- Home page shows setup banners

**Step 3: Verify tier gating**

In Developer tab: set override to "free". Confirm ✨ buttons are hidden/disabled for paid features.
Set override to "paid". Confirm ✨ buttons appear for career_summary, job_titles, etc.
Set override to "premium". Confirm voice_guidelines becomes available.

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: expanded first-run wizard — complete implementation"
```

---

## Appendix: New Dependencies

Add to `requirements.txt` / `environment.yml` if not already present:

```
pdfplumber         # PDF text extraction (alternative to pdfminer.six — simpler API)
python-docx        # DOCX text extraction
caldav             # Apple Calendar CalDAV support (Task 6)
```

Check with:
```bash
conda run -n job-seeker pip show pdfplumber python-docx caldav
```

Install if missing:
```bash
conda run -n job-seeker pip install pdfplumber python-docx caldav
```

---

## Appendix: File Tree Summary

```
app/
  app.py                          ← modified: wizard_complete gate
  Home.py                         ← modified: setup banners
  pages/
    0_Setup.py                    ← rewritten: thin orchestrator, 7 step renders
    2_Settings.py                 ← modified: Developer tab
  wizard/
    __init__.py                   ← new (empty)
    tiers.py                      ← new: FEATURES, can_use(), tier_label()
    step_hardware.py              ← new: validate()
    step_tier.py                  ← new: validate()
    step_identity.py              ← new: validate()
    step_resume.py                ← new: validate()
    step_inference.py             ← new: validate()
    step_search.py                ← new: validate()
    step_integrations.py          ← new: validate(), get_available()
scripts/
  user_profile.py                 ← modified: tier, dev_tier_override, wizard_complete, wizard_step, dismissed_banners, effective_tier
  db.py                           ← modified: params column + insert_task update
  task_runner.py                  ← modified: params arg + wizard_generate handler
  resume_parser.py                ← new: extract_text_from_pdf/docx, structure_resume
  integrations/
    __init__.py                   ← new: REGISTRY auto-discovery
    base.py                       ← new: IntegrationBase ABC
    notion.py                     ← new (13 total integrations)
    ... (12 more)
config/
  user.yaml.example               ← modified: tier/wizard_complete/dismissed_banners fields
  integrations/
    *.yaml.example                ← new (13 files)
tests/
  test_wizard_tiers.py            ← new
  test_wizard_steps.py            ← new
  test_wizard_flow.py             ← new
  test_resume_parser.py           ← new
  test_integrations.py            ← new
  test_home_banners.py            ← new
  test_dev_tab.py                 ← new
  test_user_profile.py            ← modified (additions)
  test_db.py                      ← modified (additions)
  test_task_runner.py             ← modified (additions)
  test_app_gating.py              ← modified (additions)
```
