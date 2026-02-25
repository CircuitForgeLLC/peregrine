# Testing

Peregrine has a test suite covering the core scripts layer, LLM router, integrations, wizard steps, and database helpers.

---

## Running the Test Suite

```bash
conda run -n job-seeker python -m pytest tests/ -v
```

Or using the direct binary (recommended to avoid runaway process spawning):

```bash
/path/to/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

`pytest.ini` scopes test collection to `tests/` only:

```ini
[pytest]
testpaths = tests
```

Do not widen this — the `aihawk/` subtree has its own test files that pull in GPU dependencies.

---

## What Is Covered

The suite currently has approximately 219 tests covering:

| Module | What is tested |
|--------|---------------|
| `scripts/db.py` | CRUD helpers, status transitions, dedup logic |
| `scripts/llm_router.py` | Fallback chain, backend selection, vision routing, error handling |
| `scripts/match.py` | Keyword scoring, gap calculation |
| `scripts/imap_sync.py` | Email parsing, classification label mapping |
| `scripts/company_research.py` | Prompt construction, output parsing |
| `scripts/generate_cover_letter.py` | Mission alignment detection, prompt injection |
| `scripts/task_runner.py` | Task submission, dedup, status transitions |
| `scripts/user_profile.py` | Accessor methods, defaults, YAML round-trip |
| `scripts/integrations/` | Base class contract, per-driver `fields()` and `connect()` |
| `app/wizard/tiers.py` | `can_use()`, `tier_label()`, edge cases |
| `scripts/custom_boards/` | Scraper return shape, HTTP error handling |

---

## Test Structure

Tests live in `tests/`. File naming mirrors the module being tested:

```
tests/
  test_db.py
  test_llm_router.py
  test_match.py
  test_imap_sync.py
  test_company_research.py
  test_cover_letter.py
  test_task_runner.py
  test_user_profile.py
  test_integrations.py
  test_tiers.py
  test_adzuna.py
  test_theladders.py
```

---

## Key Patterns

### tmp_path for YAML files

Use pytest's built-in `tmp_path` fixture for any test that reads or writes YAML config files:

```python
def test_user_profile_reads_name(tmp_path):
    config = tmp_path / "user.yaml"
    config.write_text("name: Alice\nemail: alice@example.com\n")

    from scripts.user_profile import UserProfile
    profile = UserProfile(config_path=config)
    assert profile.name == "Alice"
```

### Mocking LLM calls

Never make real LLM calls in tests. Patch `LLMRouter.complete`:

```python
from unittest.mock import patch

def test_cover_letter_calls_llm(tmp_path):
    with patch("scripts.generate_cover_letter.LLMRouter") as MockRouter:
        MockRouter.return_value.complete.return_value = "Dear Hiring Manager,\n..."
        from scripts.generate_cover_letter import generate
        result = generate(job={...}, user_profile={...})

    assert "Dear Hiring Manager" in result
    MockRouter.return_value.complete.assert_called_once()
```

### Mocking HTTP in scraper tests

```python
from unittest.mock import patch

def test_adzuna_returns_jobs():
    with patch("scripts.custom_boards.adzuna.requests.get") as mock_get:
        mock_get.return_value.ok = True
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"results": [...]}

        from scripts.custom_boards.adzuna import scrape
        jobs = scrape(profile={...}, db_path="nonexistent.db")

    assert len(jobs) > 0
```

### In-memory SQLite for DB tests

```python
import sqlite3, tempfile, os

def test_insert_job():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from scripts.db import init_db, insert_job
        init_db(db_path)
        insert_job(db_path, title="CSM", company="Acme", url="https://example.com/1", ...)
        # assert...
    finally:
        os.unlink(db_path)
```

---

## What NOT to Test

- **Streamlit widget rendering** — Streamlit has no headless test support. Do not try to test `st.button()` or `st.text_input()` calls. Test the underlying script functions instead.
- **Real network calls** — always mock HTTP and LLM clients
- **Real GPU inference** — mock the vision service and LLM router

---

## Adding Tests for New Code

### New scraper

Create `tests/test_myboard.py`. Required test cases:
1. Happy path: mock HTTP returns valid data → correct job dict shape
2. HTTP error: mock raises `Exception` → function returns `[]` (does not raise)
3. Empty results: API returns `{"results": []}` → function returns `[]`

### New integration

Add to `tests/test_integrations.py`. Required test cases:
1. `fields()` returns list of dicts with required keys
2. `connect()` returns `True` with valid config, `False` with missing required field
3. `test()` returns `True` with mocked successful HTTP, `False` with exception
4. `is_configured()` reflects file presence in `tmp_path`

### New wizard step

Add to `tests/test_wizard_steps.py`. Test the step's pure-logic functions (validation, data extraction). Do not test the Streamlit rendering.

### New tier feature gate

Add to `tests/test_tiers.py`:

```python
from app.wizard.tiers import can_use

def test_my_new_feature_requires_paid():
    assert can_use("free", "my_new_feature") is False
    assert can_use("paid", "my_new_feature") is True
    assert can_use("premium", "my_new_feature") is True
```
