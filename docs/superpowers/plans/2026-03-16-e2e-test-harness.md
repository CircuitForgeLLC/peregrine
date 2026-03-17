# E2E Test Harness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-mode Playwright/pytest E2E harness that smoke-tests every Peregrine page and audits every interactable element across demo, cloud, and local instances, reporting unexpected errors and expected-failure regressions.

**Architecture:** Mode-parameterized pytest suite under `tests/e2e/` isolated from unit tests. Each mode (demo/cloud/local) declares its base URL, auth setup, and expected-failure patterns. A shared `conftest.py` provides Streamlit-aware helpers (settle waiter, DOM error scanner, console capture). Smoke pass checks pages on load; interaction pass dynamically discovers and clicks every button/tab/select, diffing errors before/after each click.

**Tech Stack:** Python 3.11, pytest, pytest-playwright, playwright (Chromium), pytest-json-report, python-dotenv. All installed in existing `job-seeker` conda env.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `tests/e2e/__init__.py` | Package marker |
| Create | `tests/e2e/conftest.py` | `--mode` option, browser fixture, Streamlit helpers, cloud auth |
| Create | `tests/e2e/models.py` | `ErrorRecord` dataclass, `ModeConfig` dataclass |
| Create | `tests/e2e/modes/__init__.py` | Package marker |
| Create | `tests/e2e/modes/demo.py` | Demo mode config (port 8504, expected_failures list) |
| Create | `tests/e2e/modes/cloud.py` | Cloud mode config (port 8505, Directus JWT auth) |
| Create | `tests/e2e/modes/local.py` | Local mode config (port 8502, no auth) |
| Create | `tests/e2e/pages/__init__.py` | Package marker |
| Create | `tests/e2e/pages/base_page.py` | `BasePage`: navigate, error scan, screenshot on fail |
| Create | `tests/e2e/pages/home_page.py` | Home page object + interactable inventory |
| Create | `tests/e2e/pages/job_review_page.py` | Job Review page object |
| Create | `tests/e2e/pages/apply_page.py` | Apply Workspace page object |
| Create | `tests/e2e/pages/interviews_page.py` | Interviews kanban page object |
| Create | `tests/e2e/pages/interview_prep_page.py` | Interview Prep page object |
| Create | `tests/e2e/pages/survey_page.py` | Survey Assistant page object |
| Create | `tests/e2e/pages/settings_page.py` | Settings page object (tab-aware) |
| Create | `tests/e2e/test_smoke.py` | Parametrized smoke pass |
| Create | `tests/e2e/test_interactions.py` | Parametrized interaction pass |
| Create | `tests/e2e/results/.gitkeep` | Keeps results dir in git; outputs gitignored |
| Create | `compose.e2e.yml` | Cloud instance E2E overlay (informational env vars) |
| Modify | `pytest.ini` | Add `--ignore=tests/e2e` to `addopts` |
| Modify | `requirements.txt` | Add pytest-playwright, pytest-json-report |

**Unit tests for helpers live at:** `tests/e2e/test_helpers.py` — tests for `diff_errors`, `ErrorRecord`, `ModeConfig`, fnmatch pattern validation, and JWT auth logic (mocked).

---

## Task 0: Virtual Display Setup (Xvfb)

**Files:**
- Modify: `manage.sh` (add `xvfb-run` wrapper for headed E2E sessions)

Heimdall has no physical display. Playwright runs headless by default (no display needed), but headed mode for debugging requires a virtual framebuffer. This is the same Xvfb setup planned for browser-based scraping — set it up once here.

- [ ] **Step 1: Check if Xvfb is installed**

```bash
which Xvfb && Xvfb -help 2>&1 | head -3
```

If missing:
```bash
sudo apt-get install -y xvfb
```

- [ ] **Step 2: Verify `pyvirtualdisplay` is available (optional Python wrapper)**

```bash
conda run -n job-seeker python -c "from pyvirtualdisplay import Display; print('ok')" 2>/dev/null || \
  conda run -n job-seeker pip install pyvirtualdisplay && echo "installed"
```

- [ ] **Step 3: Add `xvfb-run` wrapper to manage.sh e2e subcommand**

When `E2E_HEADLESS=false`, wrap the pytest call with `xvfb-run`:

```bash
e2e)
    MODE="${2:-demo}"
    RESULTS_DIR="tests/e2e/results/${MODE}"
    mkdir -p "${RESULTS_DIR}"
    HEADLESS="${E2E_HEADLESS:-true}"
    if [ "$HEADLESS" = "false" ]; then
        RUNNER="xvfb-run --auto-servernum --server-args='-screen 0 1280x900x24'"
    else
        RUNNER=""
    fi
    $RUNNER conda run -n job-seeker pytest tests/e2e/ \
        --mode="${MODE}" \
        --json-report \
        --json-report-file="${RESULTS_DIR}/report.json" \
        -v "${@:3}"
    ;;
```

- [ ] **Step 4: Test headless mode works (no display needed)**

```bash
conda run -n job-seeker python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('about:blank')
    b.close()
    print('headless ok')
"
```

Expected: `headless ok`

- [ ] **Step 5: Test headed mode via xvfb-run**

```bash
xvfb-run --auto-servernum conda run -n job-seeker python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    page = b.new_page()
    page.goto('about:blank')
    title = page.title()
    b.close()
    print('headed ok, title:', title)
"
```

Expected: `headed ok, title: `

- [ ] **Step 6: Commit**

```bash
git add manage.sh
git commit -m "chore(e2e): add xvfb-run wrapper for headed debugging sessions"
```

---

## Task 1: Install Dependencies + Scaffold Structure

**Files:**
- Modify: `requirements.txt`
- Modify: `pytest.ini`
- Create: `tests/e2e/__init__.py`, `tests/e2e/modes/__init__.py`, `tests/e2e/pages/__init__.py`, `tests/e2e/results/.gitkeep`

- [ ] **Step 1: Install new packages into conda env**

```bash
conda run -n job-seeker pip install pytest-playwright pytest-json-report
conda run -n job-seeker playwright install chromium
```

Expected: `playwright install chromium` downloads ~200MB Chromium binary. No errors.

- [ ] **Step 2: Verify playwright is importable**

```bash
conda run -n job-seeker python -c "from playwright.sync_api import sync_playwright; print('ok')"
conda run -n job-seeker python -c "import pytest_playwright; print('ok')"
```

Expected: both print `ok`.

- [ ] **Step 3: Add deps to requirements.txt**

Add after the `playwright>=1.40` line (already present for LinkedIn scraper):

```
pytest-playwright>=0.4
pytest-json-report>=1.5
```

- [ ] **Step 4: Isolate E2E from unit tests**

`test_helpers.py` (unit tests for models/helpers) must be reachable by `pytest tests/`
without triggering E2E browser tests. Put it at `tests/test_e2e_helpers.py` — inside
`tests/` but outside `tests/e2e/`. The browser-dependent tests (`test_smoke.py`,
`test_interactions.py`) live in `tests/e2e/` and are only collected when explicitly
targeted with `pytest tests/e2e/ --mode=<mode>`.

Add a `tests/e2e/conftest.py` guard that skips E2E collection if `--mode` is not
provided (belt-and-suspenders — prevents accidental collection if someone runs
`pytest tests/e2e/` without `--mode`):

```python
# at top of tests/e2e/conftest.py — added in Task 4
def pytest_collection_modifyitems(config, items):
    if not config.getoption("--mode", default=None):
        skip = pytest.mark.skip(reason="E2E tests require --mode flag")
        for item in items:
            item.add_marker(skip)
```

Note: `test_helpers.py` in the file map above refers to `tests/test_e2e_helpers.py`.
Update the file map entry accordingly.

- [ ] **Step 5: Create directory skeleton**

```bash
mkdir -p /Library/Development/CircuitForge/peregrine/tests/e2e/modes
mkdir -p /Library/Development/CircuitForge/peregrine/tests/e2e/pages
mkdir -p /Library/Development/CircuitForge/peregrine/tests/e2e/results
touch tests/e2e/__init__.py
touch tests/e2e/modes/__init__.py
touch tests/e2e/pages/__init__.py
touch tests/e2e/results/.gitkeep
```

- [ ] **Step 6: Add results output to .gitignore**

Add to `.gitignore`:
```
tests/e2e/results/demo/
tests/e2e/results/cloud/
tests/e2e/results/local/
```

- [ ] **Step 7: Verify unit tests still pass (nothing broken)**

```bash
conda run -n job-seeker pytest tests/ -x -q 2>&1 | tail -5
```

Expected: same pass count as before, no collection errors.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini tests/e2e/ .gitignore
git commit -m "chore(e2e): scaffold E2E harness directory and install deps"
```

---

## Task 2: Models — `ErrorRecord` and `ModeConfig` (TDD)

**Files:**
- Create: `tests/e2e/models.py`
- Create: `tests/e2e/test_helpers.py` (unit tests for models + helpers)

- [ ] **Step 1: Write failing tests for `ErrorRecord`**

Create `tests/e2e/test_helpers.py`:

```python
"""Unit tests for E2E harness models and helper utilities."""
import fnmatch
import pytest
from tests.e2e.models import ErrorRecord, ModeConfig, diff_errors


def test_error_record_equality():
    a = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    b = ErrorRecord(type="exception", message="boom", element_html="<div>boom</div>")
    assert a == b


def test_error_record_inequality():
    a = ErrorRecord(type="exception", message="boom", element_html="")
    b = ErrorRecord(type="alert", message="boom", element_html="")
    assert a != b


def test_diff_errors_returns_new_only():
    before = [ErrorRecord("exception", "old error", "")]
    after = [
        ErrorRecord("exception", "old error", ""),
        ErrorRecord("alert", "new error", ""),
    ]
    result = diff_errors(before, after)
    assert result == [ErrorRecord("alert", "new error", "")]


def test_diff_errors_empty_when_no_change():
    errors = [ErrorRecord("exception", "x", "")]
    assert diff_errors(errors, errors) == []


def test_diff_errors_empty_before():
    after = [ErrorRecord("alert", "boom", "")]
    assert diff_errors([], after) == after


def test_mode_config_expected_failure_match():
    config = ModeConfig(
        name="demo",
        base_url="http://localhost:8504",
        auth_setup=lambda ctx: None,
        expected_failures=["Fetch*", "Generate Cover Letter"],
        results_dir=None,
        settings_tabs=["👤 My Profile"],
    )
    assert config.matches_expected_failure("Fetch New Jobs")
    assert config.matches_expected_failure("Generate Cover Letter")
    assert not config.matches_expected_failure("View Jobs")


def test_mode_config_no_expected_failures():
    config = ModeConfig(
        name="local",
        base_url="http://localhost:8502",
        auth_setup=lambda ctx: None,
        expected_failures=[],
        results_dir=None,
        settings_tabs=[],
    )
    assert not config.matches_expected_failure("Fetch New Jobs")
```

- [ ] **Step 2: Run test — confirm it fails (models don't exist yet)**

```bash
conda run -n job-seeker pytest tests/e2e/test_helpers.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError` — models not yet written.

- [ ] **Step 3: Write `models.py`**

Create `tests/e2e/models.py`:

```python
"""Shared data models for the Peregrine E2E test harness."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class ErrorRecord:
    type: str       # "exception" | "alert"
    message: str
    element_html: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ErrorRecord):
            return NotImplemented
        return (self.type, self.message) == (other.type, other.message)

    def __hash__(self) -> int:
        return hash((self.type, self.message))


def diff_errors(before: list[ErrorRecord], after: list[ErrorRecord]) -> list[ErrorRecord]:
    """Return errors in `after` that were not present in `before`."""
    before_set = set(before)
    return [e for e in after if e not in before_set]


@dataclass
class ModeConfig:
    name: str
    base_url: str
    auth_setup: Callable[[Any], None]   # (BrowserContext) -> None
    expected_failures: list[str]        # fnmatch glob patterns against element labels
    results_dir: Path | None
    settings_tabs: list[str]            # tabs expected to be present in this mode

    def matches_expected_failure(self, label: str) -> bool:
        """Return True if label matches any expected_failure pattern (fnmatch)."""
        return any(fnmatch.fnmatch(label, pattern) for pattern in self.expected_failures)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
conda run -n job-seeker pytest tests/e2e/test_helpers.py -v
```

Expected: 7 tests, all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/models.py tests/e2e/test_helpers.py
git commit -m "feat(e2e): add ErrorRecord, ModeConfig, diff_errors models with tests"
```

---

## Task 3: Mode Configs — demo, cloud, local

**Files:**
- Create: `tests/e2e/modes/demo.py`
- Create: `tests/e2e/modes/cloud.py`
- Create: `tests/e2e/modes/local.py`

No browser needed yet — these are pure data/config. Tests for auth logic (cloud) come in Task 4.

- [ ] **Step 1: Write `modes/demo.py`**

```python
"""Demo mode config — port 8504, DEMO_MODE=true, LLM/scraping neutered."""
from pathlib import Path
from tests.e2e.models import ModeConfig

# Base tabs present in all modes
_BASE_SETTINGS_TABS = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data",
]

DEMO = ModeConfig(
    name="demo",
    base_url="http://localhost:8504",
    auth_setup=lambda ctx: None,   # no auth in demo mode
    expected_failures=[
        "Fetch*",                   # "Fetch New Jobs" — discovery blocked
        "Generate Cover Letter*",   # LLM blocked
        "Generate*",                # any other Generate button
        "Analyze Screenshot*",      # vision service blocked
        "Push to Calendar*",        # calendar push blocked
        "Sync Email*",              # email sync blocked
        "Start Email Sync*",
    ],
    results_dir=Path("tests/e2e/results/demo"),
    settings_tabs=_BASE_SETTINGS_TABS,   # no Privacy or Developer tab in demo
)
```

- [ ] **Step 2: Write `modes/local.py`**

```python
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
```

- [ ] **Step 3: Write `modes/cloud.py` (auth logic placeholder — full impl in Task 4)**

```python
"""Cloud mode config — port 8505, CLOUD_MODE=true, Directus JWT auth."""
from __future__ import annotations
import os
import time
import logging
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from tests.e2e.models import ModeConfig

load_dotenv(".env.e2e")

log = logging.getLogger(__name__)

_BASE_SETTINGS_TABS = [
    "👤 My Profile", "📝 Resume Profile", "🔎 Search",
    "⚙️ System", "🎯 Fine-Tune", "🔑 License", "💾 Data", "🔒 Privacy",
]

# Token cache — refreshed if within 100s of expiry
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _get_jwt() -> str:
    """
    Acquire a Directus JWT for the e2e test user.
    Strategy A: user/pass login (preferred).
    Strategy B: persistent JWT from E2E_DIRECTUS_JWT env var.
    Caches the token and refreshes 100s before expiry.
    """
    # Strategy B fallback first check
    if not os.environ.get("E2E_DIRECTUS_EMAIL"):
        jwt = os.environ.get("E2E_DIRECTUS_JWT", "")
        if not jwt:
            raise RuntimeError("Cloud mode requires E2E_DIRECTUS_EMAIL+PASSWORD or E2E_DIRECTUS_JWT in .env.e2e")
        return jwt

    # Check cache
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 100:
        return _token_cache["token"]

    # Strategy A: fresh login
    directus_url = os.environ.get("E2E_DIRECTUS_URL", "http://172.31.0.2:8055")
    resp = requests.post(
        f"{directus_url}/auth/login",
        json={
            "email": os.environ["E2E_DIRECTUS_EMAIL"],
            "password": os.environ["E2E_DIRECTUS_PASSWORD"],
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    token = data["access_token"]
    expires_in_ms = data.get("expires", 900_000)

    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + (expires_in_ms / 1000)
    log.info("Acquired Directus JWT for e2e test user (expires in %ds)", expires_in_ms // 1000)
    return token


def _cloud_auth_setup(context: Any) -> None:
    """Inject X-CF-Session header with real Directus JWT into all browser requests."""
    jwt = _get_jwt()
    # X-CF-Session value is parsed by cloud_session.py as a cookie-format string:
    # it looks for cf_session=<jwt> within the header value.
    context.set_extra_http_headers({"X-CF-Session": f"cf_session={jwt}"})


CLOUD = ModeConfig(
    name="cloud",
    base_url="http://localhost:8505",
    auth_setup=_cloud_auth_setup,
    expected_failures=[],
    results_dir=Path("tests/e2e/results/cloud"),
    settings_tabs=_BASE_SETTINGS_TABS,
)
```

- [ ] **Step 4: Add JWT auth tests to `tests/test_e2e_helpers.py`**

Append to `tests/test_e2e_helpers.py` (note: outside `tests/e2e/`):

```python
from unittest.mock import patch, MagicMock
import time


def test_get_jwt_strategy_b_fallback(monkeypatch):
    """Falls back to persistent JWT when no email env var set."""
    monkeypatch.delenv("E2E_DIRECTUS_EMAIL", raising=False)
    monkeypatch.setenv("E2E_DIRECTUS_JWT", "persistent.jwt.token")
    # Reset module-level cache
    import tests.e2e.modes.cloud as cloud_mod
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})
    assert cloud_mod._get_jwt() == "persistent.jwt.token"


def test_get_jwt_strategy_b_raises_if_no_token(monkeypatch):
    """Raises if neither email nor JWT env var is set."""
    monkeypatch.delenv("E2E_DIRECTUS_EMAIL", raising=False)
    monkeypatch.delenv("E2E_DIRECTUS_JWT", raising=False)
    import tests.e2e.modes.cloud as cloud_mod
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})
    with pytest.raises(RuntimeError, match="Cloud mode requires"):
        cloud_mod._get_jwt()


def test_get_jwt_strategy_a_login(monkeypatch):
    """Strategy A: calls Directus /auth/login and caches token."""
    monkeypatch.setenv("E2E_DIRECTUS_EMAIL", "e2e@circuitforge.tech")
    monkeypatch.setenv("E2E_DIRECTUS_PASSWORD", "testpass")
    monkeypatch.setenv("E2E_DIRECTUS_URL", "http://fake-directus:8055")

    import tests.e2e.modes.cloud as cloud_mod
    cloud_mod._token_cache.update({"token": None, "expires_at": 0.0})

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"access_token": "fresh.jwt", "expires": 900_000}}
    mock_resp.raise_for_status = lambda: None

    with patch("tests.e2e.modes.cloud.requests.post", return_value=mock_resp) as mock_post:
        token = cloud_mod._get_jwt()

    assert token == "fresh.jwt"
    mock_post.assert_called_once()
    assert cloud_mod._token_cache["token"] == "fresh.jwt"


def test_get_jwt_uses_cache(monkeypatch):
    """Returns cached token if not yet expired."""
    monkeypatch.setenv("E2E_DIRECTUS_EMAIL", "e2e@circuitforge.tech")
    import tests.e2e.modes.cloud as cloud_mod
    cloud_mod._token_cache.update({"token": "cached.jwt", "expires_at": time.time() + 500})
    with patch("tests.e2e.modes.cloud.requests.post") as mock_post:
        token = cloud_mod._get_jwt()
    assert token == "cached.jwt"
    mock_post.assert_not_called()
```

- [ ] **Step 5: Run tests**

```bash
conda run -n job-seeker pytest tests/test_e2e_helpers.py -v
```

Expected: 11 tests, all PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/modes/ tests/e2e/test_helpers.py
git commit -m "feat(e2e): add mode configs (demo/cloud/local) with Directus JWT auth"
```

---

## Task 4: `conftest.py` — Browser Fixtures + Streamlit Helpers

**Files:**
- Create: `tests/e2e/conftest.py`

This is the heart of the harness. No unit tests for the browser fixtures themselves (they require a live browser), but the helper functions that don't touch the browser get tested in `test_helpers.py`.

- [ ] **Step 1: Add `get_page_errors` and `get_console_errors` tests to `test_helpers.py`**

These functions take a `page` object. We can test them with a mock that mimics Playwright's `page.query_selector_all()` and `page.evaluate()` return shapes:

```python
def test_get_page_errors_finds_exceptions(monkeypatch):
    """get_page_errors returns ErrorRecord for stException elements."""
    from tests.e2e.conftest import get_page_errors

    mock_el = MagicMock()
    mock_el.get_attribute.return_value = None   # no kind attr
    mock_el.inner_text.return_value = "RuntimeError: boom"
    mock_el.inner_html.return_value = "<div>RuntimeError: boom</div>"

    mock_page = MagicMock()
    mock_page.query_selector_all.side_effect = lambda sel: (
        [mock_el] if "stException" in sel else []
    )

    errors = get_page_errors(mock_page)
    assert len(errors) == 1
    assert errors[0].type == "exception"
    assert "boom" in errors[0].message


def test_get_page_errors_finds_alert_errors(monkeypatch):
    """get_page_errors returns ErrorRecord for stAlert with stAlertContentError child.

    In Streamlit 1.35+, st.error() renders a child [data-testid="stAlertContentError"].
    The kind attribute is a React prop — it is NOT available via get_attribute() in the DOM.
    Detection must use the child element, not the attribute.
    """
    from tests.e2e.conftest import get_page_errors

    # Mock the child error element that Streamlit 1.35+ renders inside st.error()
    mock_child = MagicMock()

    mock_el = MagicMock()
    mock_el.query_selector.return_value = mock_child   # stAlertContentError found
    mock_el.inner_text.return_value = "Something went wrong"
    mock_el.inner_html.return_value = "<div>Something went wrong</div>"

    mock_page = MagicMock()
    mock_page.query_selector_all.side_effect = lambda sel: (
        [] if "stException" in sel else [mock_el]
    )

    errors = get_page_errors(mock_page)
    assert len(errors) == 1
    assert errors[0].type == "alert"


def test_get_page_errors_ignores_non_error_alerts(monkeypatch):
    """get_page_errors does NOT flag st.warning() or st.info() alerts."""
    from tests.e2e.conftest import get_page_errors

    mock_el = MagicMock()
    mock_el.query_selector.return_value = None   # no stAlertContentError child
    mock_el.inner_text.return_value = "Just a warning"

    mock_page = MagicMock()
    mock_page.query_selector_all.side_effect = lambda sel: (
        [] if "stException" in sel else [mock_el]
    )

    errors = get_page_errors(mock_page)
    assert errors == []


def test_get_console_errors_filters_noise():
    """get_console_errors filters benign Streamlit WebSocket reconnect messages."""
    from tests.e2e.conftest import get_console_errors

    messages = [
        MagicMock(type="error", text="WebSocket connection closed"),   # benign
        MagicMock(type="error", text="TypeError: cannot read property"),  # real
        MagicMock(type="log", text="irrelevant"),
    ]
    errors = get_console_errors(messages)
    assert errors == ["TypeError: cannot read property"]
```

- [ ] **Step 2: Run tests — confirm they fail (conftest not yet written)**

```bash
conda run -n job-seeker pytest tests/e2e/test_helpers.py::test_get_page_errors_finds_exceptions -v 2>&1 | tail -5
```

Expected: `ImportError` from `tests.e2e.conftest`.

- [ ] **Step 3: Write `tests/e2e/conftest.py`**

```python
"""
Peregrine E2E test harness — shared fixtures and Streamlit helpers.

Run with: pytest tests/e2e/ --mode=demo|cloud|local|all
"""
from __future__ import annotations
import os
import time
import logging
from pathlib import Path
from typing import Generator

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Page, BrowserContext, sync_playwright

from tests.e2e.models import ErrorRecord, ModeConfig, diff_errors
from tests.e2e.modes.demo import DEMO
from tests.e2e.modes.cloud import CLOUD
from tests.e2e.modes.local import LOCAL

load_dotenv(".env.e2e")
log = logging.getLogger(__name__)

_ALL_MODES = {"demo": DEMO, "cloud": CLOUD, "local": LOCAL}

# ── Noise filter for console errors ──────────────────────────────────────────
_CONSOLE_NOISE = [
    "WebSocket connection",
    "WebSocket is closed",
    "_stcore/stream",
    "favicon.ico",
]


# ── pytest option ─────────────────────────────────────────────────────────────
def pytest_addoption(parser):
    parser.addoption(
        "--mode",
        action="store",
        default="demo",
        choices=["demo", "cloud", "local", "all"],
        help="Which Peregrine instance(s) to test against",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: mark test as E2E (requires running Peregrine instance)")


# ── Active mode(s) fixture ────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def active_modes(pytestconfig) -> list[ModeConfig]:
    mode_arg = pytestconfig.getoption("--mode")
    if mode_arg == "all":
        return list(_ALL_MODES.values())
    return [_ALL_MODES[mode_arg]]


# ── Browser fixture (session-scoped, headless by default) ─────────────────────
@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "viewport": {"width": 1280, "height": 900},
        "ignore_https_errors": True,
    }


# ── Instance availability guard ───────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def assert_instances_reachable(active_modes):
    """Fail fast with a clear message if any target instance is not running."""
    import socket
    for mode in active_modes:
        from urllib.parse import urlparse
        parsed = urlparse(mode.base_url)
        host, port = parsed.hostname, parsed.port or 80
        try:
            with socket.create_connection((host, port), timeout=3):
                pass
        except OSError:
            pytest.exit(
                f"[{mode.name}] Instance not reachable at {mode.base_url} — "
                "start the instance before running E2E tests.",
                returncode=1,
            )


# ── Per-mode browser context with auth injected ───────────────────────────────
@pytest.fixture(scope="session")
def mode_contexts(active_modes, playwright) -> dict[str, BrowserContext]:
    """One browser context per active mode, with auth injected via route handler.

    Cloud mode uses context.route() to inject a fresh JWT on every request —
    this ensures the token cache refresh logic in cloud.py is exercised mid-run,
    even if a test session exceeds the 900s Directus JWT TTL.
    """
    from tests.e2e.modes.cloud import _get_jwt

    headless = os.environ.get("E2E_HEADLESS", "true").lower() != "false"
    slow_mo = int(os.environ.get("E2E_SLOW_MO", "0"))
    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    contexts = {}
    for mode in active_modes:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        if mode.name == "cloud":
            # Route-based JWT injection: _get_jwt() is called on each request,
            # so the token cache refresh fires naturally during long runs.
            def _inject_jwt(route, request):
                jwt = _get_jwt()
                headers = {**request.headers, "x-cf-session": f"cf_session={jwt}"}
                route.continue_(headers=headers)
            ctx.route(f"{mode.base_url}/**", _inject_jwt)
        else:
            mode.auth_setup(ctx)
        contexts[mode.name] = ctx
    yield contexts
    browser.close()


# ── Streamlit helper: wait for page to settle ─────────────────────────────────
def wait_for_streamlit(page: Page, timeout: int = 10_000) -> None:
    """
    Wait until Streamlit has finished rendering:
    1. No stSpinner visible
    2. No stStatusWidget showing 'running'
    3. 2000ms idle window (accounts for 3s fragment poller between ticks)

    NOTE: Do NOT use page.wait_for_load_state("networkidle") — Playwright's
    networkidle uses a hard-coded 500ms idle window which is too short for
    Peregrine's sidebar fragment poller (fires every 3s). We implement our
    own 2000ms window instead.
    """
    # Wait for spinners to clear
    try:
        page.wait_for_selector('[data-testid="stSpinner"]', state="hidden", timeout=timeout)
    except Exception:
        pass  # spinner may not be present at all — not an error
    # Wait for status widget to stop showing 'running'
    try:
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')"
            "?.textContent?.includes('running')",
            timeout=5_000,
        )
    except Exception:
        pass
    # 2000ms settle window — long enough to confirm quiet between fragment poll ticks
    page.wait_for_timeout(2_000)


# ── Streamlit helper: scan DOM for errors ────────────────────────────────────
def get_page_errors(page) -> list[ErrorRecord]:
    """
    Scan the DOM for Streamlit error indicators:
    - [data-testid="stException"] — unhandled Python exceptions
    - [data-testid="stAlert"] with kind="error" — st.error() calls
    """
    errors: list[ErrorRecord] = []

    for el in page.query_selector_all('[data-testid="stException"]'):
        errors.append(ErrorRecord(
            type="exception",
            message=el.inner_text()[:500],
            element_html=el.inner_html()[:1000],
        ))

    for el in page.query_selector_all('[data-testid="stAlert"]'):
        # In Streamlit 1.35+, st.error() renders a child [data-testid="stAlertContentError"].
        # The `kind` attribute is a React prop, not a DOM attribute — get_attribute("kind")
        # always returns None in production. Use child element detection as the authoritative check.
        if el.query_selector('[data-testid="stAlertContentError"]'):
            errors.append(ErrorRecord(
                type="alert",
                message=el.inner_text()[:500],
                element_html=el.inner_html()[:1000],
            ))

    return errors


# ── Streamlit helper: capture console errors ──────────────────────────────────
def get_console_errors(messages) -> list[str]:
    """Filter browser console messages to real errors, excluding Streamlit noise."""
    result = []
    for msg in messages:
        if msg.type != "error":
            continue
        text = msg.text
        if any(noise in text for noise in _CONSOLE_NOISE):
            continue
        result.append(text)
    return result


# ── Screenshot helper ─────────────────────────────────────────────────────────
def screenshot_on_fail(page: Page, mode_name: str, test_name: str) -> Path:
    results_dir = Path(f"tests/e2e/results/{mode_name}/screenshots")
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{test_name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
```

- [ ] **Step 4: Run helper tests — confirm they pass**

```bash
conda run -n job-seeker pytest tests/e2e/test_helpers.py -v
```

Expected: all tests PASS (including the new `get_page_errors` and `get_console_errors` tests).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/conftest.py tests/e2e/test_helpers.py
git commit -m "feat(e2e): add conftest with Streamlit helpers, browser fixtures, console filter"
```

---

## Task 5: `BasePage` + Page Objects

**Files:**
- Create: `tests/e2e/pages/base_page.py`
- Create: `tests/e2e/pages/home_page.py`
- Create: `tests/e2e/pages/job_review_page.py`
- Create: `tests/e2e/pages/apply_page.py`
- Create: `tests/e2e/pages/interviews_page.py`
- Create: `tests/e2e/pages/interview_prep_page.py`
- Create: `tests/e2e/pages/survey_page.py`
- Create: `tests/e2e/pages/settings_page.py`

- [ ] **Step 1: Write `base_page.py`**

```python
"""Base page object — navigation, error capture, interactable discovery."""
from __future__ import annotations
import logging
import warnings
import fnmatch
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from playwright.sync_api import Page

from tests.e2e.conftest import wait_for_streamlit, get_page_errors, get_console_errors
from tests.e2e.models import ErrorRecord, ModeConfig

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# Selectors for interactive elements to audit
INTERACTABLE_SELECTORS = [
    '[data-testid="baseButton-primary"] button',
    '[data-testid="baseButton-secondary"] button',
    '[data-testid="stTab"] button[role="tab"]',
    '[data-testid="stSelectbox"]',
    '[data-testid="stCheckbox"] input',
]


@dataclass
class InteractableElement:
    label: str
    selector: str
    index: int      # nth match for this selector


class BasePage:
    """Base page object for all Peregrine pages."""

    nav_label: str = ""   # sidebar nav link text — override in subclass

    def __init__(self, page: Page, mode: ModeConfig, console_messages: list):
        self.page = page
        self.mode = mode
        self._console_messages = console_messages

    def navigate(self) -> None:
        """Navigate to this page by clicking its sidebar nav link."""
        sidebar = self.page.locator('[data-testid="stSidebarNav"]')
        sidebar.get_by_text(self.nav_label, exact=False).first.click()
        wait_for_streamlit(self.page)

    def get_errors(self) -> list[ErrorRecord]:
        return get_page_errors(self.page)

    def get_console_errors(self) -> list[str]:
        return get_console_errors(self._console_messages)

    def discover_interactables(self, skip_sidebar: bool = True) -> list[InteractableElement]:
        """
        Find all interactive elements on the current page.
        Excludes sidebar elements (navigation handled separately).
        """
        found: list[InteractableElement] = []
        seen_labels: dict[str, int] = {}

        for selector in INTERACTABLE_SELECTORS:
            elements = self.page.query_selector_all(selector)
            for i, el in enumerate(elements):
                # Skip sidebar elements
                if skip_sidebar and el.evaluate(
                    "el => el.closest('[data-testid=\"stSidebar\"]') !== null"
                ):
                    continue
                label = (el.inner_text() or el.get_attribute("aria-label") or f"element-{i}").strip()
                label = label[:80]  # truncate for report readability
                found.append(InteractableElement(label=label, selector=selector, index=i))

        # Warn on ambiguous expected_failure patterns
        for pattern in self.mode.expected_failures:
            matches = [e for e in found if fnmatch.fnmatch(e.label, pattern)]
            if len(matches) > 1:
                warnings.warn(
                    f"expected_failure pattern '{pattern}' matches {len(matches)} elements: "
                    + ", ".join(f'"{m.label}"' for m in matches),
                    stacklevel=2,
                )

        return found
```

- [ ] **Step 2: Write page objects for all 7 pages**

Each page object only needs to declare its `nav_label`. Significant page-specific logic goes here later if needed (e.g., Settings tab iteration).

Create `tests/e2e/pages/home_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class HomePage(BasePage):
    nav_label = "Home"
```

Create `tests/e2e/pages/job_review_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class JobReviewPage(BasePage):
    nav_label = "Job Review"
```

Create `tests/e2e/pages/apply_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class ApplyPage(BasePage):
    nav_label = "Apply Workspace"
```

Create `tests/e2e/pages/interviews_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class InterviewsPage(BasePage):
    nav_label = "Interviews"
```

Create `tests/e2e/pages/interview_prep_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class InterviewPrepPage(BasePage):
    nav_label = "Interview Prep"
```

Create `tests/e2e/pages/survey_page.py`:
```python
from tests.e2e.pages.base_page import BasePage

class SurveyPage(BasePage):
    nav_label = "Survey Assistant"
```

Create `tests/e2e/pages/settings_page.py`:
```python
"""Settings page — tab-aware page object."""
from __future__ import annotations
import logging

from tests.e2e.pages.base_page import BasePage, InteractableElement
from tests.e2e.conftest import wait_for_streamlit

log = logging.getLogger(__name__)


class SettingsPage(BasePage):
    nav_label = "Settings"

    def discover_interactables(self, skip_sidebar: bool = True) -> list[InteractableElement]:
        """
        Settings has multiple tabs. Click each expected tab, collect interactables
        within it, then return the full combined list.
        """
        all_elements: list[InteractableElement] = []
        tab_labels = self.mode.settings_tabs

        for tab_label in tab_labels:
            # Click the tab
            # Match on full label text — Playwright's filter(has_text=) handles emoji correctly.
            # Do NOT use tab_label.split()[-1]: "My Profile" and "Resume Profile" both end
            # in "Profile" causing a collision that silently skips Resume Profile's interactables.
            tab_btn = self.page.locator(
                '[data-testid="stTab"] button[role="tab"]'
            ).filter(has_text=tab_label)
            if tab_btn.count() == 0:
                log.warning("Settings tab not found: %s", tab_label)
                continue
            tab_btn.first.click()
            wait_for_streamlit(self.page)

            # Collect non-tab interactables within this tab's content
            tab_elements = super().discover_interactables(skip_sidebar=skip_sidebar)
            # Exclude the tab buttons themselves (already clicked)
            tab_elements = [
                e for e in tab_elements
                if 'role="tab"' not in e.selector
            ]
            all_elements.extend(tab_elements)

        return all_elements
```

- [ ] **Step 3: Verify imports work**

```bash
conda run -n job-seeker python -c "
from tests.e2e.pages.home_page import HomePage
from tests.e2e.pages.settings_page import SettingsPage
print('page objects ok')
"
```

Expected: `page objects ok`

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/pages/
git commit -m "feat(e2e): add BasePage and 7 page objects"
```

---

## Task 6: Smoke Tests

**Files:**
- Create: `tests/e2e/test_smoke.py`

- [ ] **Step 1: Write `test_smoke.py`**

```python
"""
Smoke pass — navigate each page, wait for Streamlit to settle, assert no errors on load.
Errors on page load are always real bugs (not mode-specific).

Run: pytest tests/e2e/test_smoke.py --mode=demo
"""
from __future__ import annotations
import pytest
from playwright.sync_api import sync_playwright

from tests.e2e.conftest import wait_for_streamlit, get_page_errors, get_console_errors, screenshot_on_fail
from tests.e2e.models import ModeConfig
from tests.e2e.pages.home_page import HomePage
from tests.e2e.pages.job_review_page import JobReviewPage
from tests.e2e.pages.apply_page import ApplyPage
from tests.e2e.pages.interviews_page import InterviewsPage
from tests.e2e.pages.interview_prep_page import InterviewPrepPage
from tests.e2e.pages.survey_page import SurveyPage
from tests.e2e.pages.settings_page import SettingsPage

PAGE_CLASSES = [
    HomePage, JobReviewPage, ApplyPage, InterviewsPage,
    InterviewPrepPage, SurveyPage, SettingsPage,
]


@pytest.mark.e2e
def test_smoke_all_pages(active_modes, mode_contexts, playwright):
    """For each active mode: navigate to every page and assert no errors on load."""
    failures: list[str] = []

    for mode in active_modes:
        ctx = mode_contexts[mode.name]
        page = ctx.new_page()
        console_msgs: list = []
        page.on("console", lambda msg: console_msgs.append(msg))

        # Navigate to app root first to establish session
        page.goto(mode.base_url)
        wait_for_streamlit(page)

        for PageClass in PAGE_CLASSES:
            pg = PageClass(page, mode, console_msgs)
            pg.navigate()
            console_msgs.clear()  # reset per-page

            dom_errors = pg.get_errors()
            console_errors = pg.get_console_errors()

            if dom_errors or console_errors:
                shot_path = screenshot_on_fail(page, mode.name, f"smoke_{PageClass.__name__}")
                detail = "\n".join(
                    [f"  DOM: {e.message}" for e in dom_errors]
                    + [f"  Console: {e}" for e in console_errors]
                )
                failures.append(
                    f"[{mode.name}] {PageClass.nav_label} — errors on load:\n{detail}\n  screenshot: {shot_path}"
                )

        page.close()

    if failures:
        pytest.fail("Smoke test failures:\n\n" + "\n\n".join(failures))
```

- [ ] **Step 2: Run smoke test against demo mode (demo must be running at 8504)**

```bash
conda run -n job-seeker pytest tests/e2e/test_smoke.py --mode=demo -v -s 2>&1 | tail -30
```

Expected: test runs and reports results. Failures are expected — that's the point of this tool. Record what breaks.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_smoke.py
git commit -m "feat(e2e): add smoke test pass for all pages across modes"
```

---

## Task 7: Interaction Tests

**Files:**
- Create: `tests/e2e/test_interactions.py`

- [ ] **Step 1: Write `test_interactions.py`**

```python
"""
Interaction pass — discover every interactable element on each page, click it,
diff errors before/after. Demo mode XFAIL patterns are checked; unexpected passes
are flagged as regressions.

Run: pytest tests/e2e/test_interactions.py --mode=demo -v
"""
from __future__ import annotations
import pytest

from tests.e2e.conftest import (
    wait_for_streamlit, get_page_errors, screenshot_on_fail,
)
from tests.e2e.models import ModeConfig, diff_errors
from tests.e2e.pages.home_page import HomePage
from tests.e2e.pages.job_review_page import JobReviewPage
from tests.e2e.pages.apply_page import ApplyPage
from tests.e2e.pages.interviews_page import InterviewsPage
from tests.e2e.pages.interview_prep_page import InterviewPrepPage
from tests.e2e.pages.survey_page import SurveyPage
from tests.e2e.pages.settings_page import SettingsPage

PAGE_CLASSES = [
    HomePage, JobReviewPage, ApplyPage, InterviewsPage,
    InterviewPrepPage, SurveyPage, SettingsPage,
]


@pytest.mark.e2e
def test_interactions_all_pages(active_modes, mode_contexts, playwright):
    """
    For each active mode and page: click every discovered interactable,
    diff errors, XFAIL expected demo failures, FAIL on unexpected errors.
    XPASS (expected failure that didn't fail) is also reported.
    """
    failures: list[str] = []
    xfails: list[str] = []
    xpasses: list[str] = []

    for mode in active_modes:
        ctx = mode_contexts[mode.name]
        page = ctx.new_page()
        console_msgs: list = []
        page.on("console", lambda msg: console_msgs.append(msg))

        page.goto(mode.base_url)
        wait_for_streamlit(page)

        for PageClass in PAGE_CLASSES:
            pg = PageClass(page, mode, console_msgs)
            pg.navigate()

            elements = pg.discover_interactables()

            for element in elements:
                # Reset to this page before each interaction
                pg.navigate()

                before = pg.get_errors()

                # Interact with element (click for buttons/tabs/checkboxes, open for selects)
                try:
                    all_matches = page.query_selector_all(element.selector)
                    # Filter out sidebar elements
                    content_matches = [
                        el for el in all_matches
                        if not el.evaluate(
                            "el => el.closest('[data-testid=\"stSidebar\"]') !== null"
                        )
                    ]
                    if element.index < len(content_matches):
                        content_matches[element.index].click()
                    else:
                        continue  # element disappeared after navigation reset
                except Exception as e:
                    failures.append(
                        f"[{mode.name}] {PageClass.nav_label} / '{element.label}' — "
                        f"could not interact: {e}"
                    )
                    continue

                wait_for_streamlit(page)
                after = pg.get_errors()
                new_errors = diff_errors(before, after)

                is_expected = mode.matches_expected_failure(element.label)

                if new_errors:
                    if is_expected:
                        xfails.append(
                            f"[{mode.name}] {PageClass.nav_label} / '{element.label}' "
                            f"(expected) — {new_errors[0].message[:120]}"
                        )
                    else:
                        shot = screenshot_on_fail(
                            page, mode.name,
                            f"interact_{PageClass.__name__}_{element.label[:30]}"
                        )
                        failures.append(
                            f"[{mode.name}] {PageClass.nav_label} / '{element.label}' — "
                            f"unexpected error: {new_errors[0].message[:200]}\n  screenshot: {shot}"
                        )
                else:
                    if is_expected:
                        xpasses.append(
                            f"[{mode.name}] {PageClass.nav_label} / '{element.label}' "
                            f"— expected to fail but PASSED (neutering guard may be broken!)"
                        )

        page.close()

    # Report summary
    report_lines = []
    if xfails:
        report_lines.append(f"XFAIL ({len(xfails)} expected failures, demo mode working correctly):")
        report_lines.extend(f"  {x}" for x in xfails)
    if xpasses:
        report_lines.append(f"\nXPASS — REGRESSION ({len(xpasses)} neutering guards broken!):")
        report_lines.extend(f"  {x}" for x in xpasses)
    if failures:
        report_lines.append(f"\nFAIL ({len(failures)} unexpected errors):")
        report_lines.extend(f"  {x}" for x in failures)

    if report_lines:
        print("\n\n=== E2E Interaction Report ===\n" + "\n".join(report_lines))

    # XPASSes are regressions — fail the test
    if xpasses or failures:
        pytest.fail(
            f"{len(failures)} unexpected error(s), {len(xpasses)} xpass regression(s). "
            "See report above."
        )
```

- [ ] **Step 2: Run interaction test against demo**

```bash
conda run -n job-seeker pytest tests/e2e/test_interactions.py --mode=demo -v -s 2>&1 | tail -40
```

Expected: test runs; XFAILs are logged (LLM buttons in demo mode), any unexpected errors are reported as FAILs. First run will reveal what demo seed data gaps exist.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_interactions.py
git commit -m "feat(e2e): add interaction audit pass with XFAIL/XPASS reporting"
```

---

## Task 8: `compose.e2e.yml`, Reporting Config + Prerequisites

**Note:** `.env.e2e` and `.env.e2e.example` were already created during pre-implementation
setup (Directus test user provisioned at `e2e@circuitforge.tech`, credentials stored).
This task verifies they exist and adds the remaining config files.

**Files:**
- Create: `compose.e2e.yml`

- [ ] **Step 1: Verify `.env.e2e` and `.env.e2e.example` exist**

```bash
ls -la .env.e2e .env.e2e.example
```

Expected: both files present. If `.env.e2e` is missing, copy from example and fill in credentials.

- [ ] **Step 2: Seed `background_tasks` table to empty state for cloud/local runs**

Cloud and local mode instances may have background tasks in their DBs that cause
Peregrine's sidebar fragment poller to fire continuously, interfering with
`wait_for_streamlit`. Clear completed/stuck tasks before running E2E:

```bash
# For cloud instance DB (e2e-test-runner user)
sqlite3 /devl/menagerie-data/e2e-test-runner/peregrine/staging.db \
  "DELETE FROM background_tasks WHERE status IN ('completed','failed','running');"

# For local instance DB
sqlite3 data/staging.db \
  "DELETE FROM background_tasks WHERE status IN ('completed','failed','running');"
```

Add this as a step in the `manage.sh e2e` subcommand — run before pytest.

- [ ] **Step 3: Write `compose.e2e.yml`**

```yaml
# compose.e2e.yml — E2E test overlay for cloud instance
# Usage: docker compose -f compose.cloud.yml -f compose.e2e.yml up -d
#
# No secrets here — credentials live in .env.e2e (gitignored)
# This file is safe to commit.
services:
  peregrine-cloud:
    environment:
      - E2E_TEST_USER_ID=e2e-test-runner
      - E2E_TEST_USER_EMAIL=e2e@circuitforge.tech
```

- [ ] **Step 2: Add `--json-report` to E2E run commands in manage.sh**

Find the section in `manage.sh` that handles test commands, or add a new `e2e` subcommand:

```bash
e2e)
    MODE="${2:-demo}"
    RESULTS_DIR="tests/e2e/results/${MODE}"
    mkdir -p "${RESULTS_DIR}"
    conda run -n job-seeker pytest tests/e2e/ \
        --mode="${MODE}" \
        --json-report \
        --json-report-file="${RESULTS_DIR}/report.json" \
        --playwright-screenshot=on \
        -v "$@"
    ;;
```

- [ ] **Step 3: Add results dirs to `.gitignore`**

Ensure these lines are in `.gitignore` (from Task 1, verify they're present):
```
tests/e2e/results/demo/
tests/e2e/results/cloud/
tests/e2e/results/local/
```

- [ ] **Step 4: Test the manage.sh e2e command**

```bash
bash manage.sh e2e demo 2>&1 | tail -20
```

Expected: pytest runs with JSON report output.

- [ ] **Step 5: Commit**

```bash
git add compose.e2e.yml manage.sh
git commit -m "feat(e2e): add compose.e2e.yml overlay and manage.sh e2e subcommand"
```

---

## Task 9: Final Verification Run

- [ ] **Step 1: Run full unit test suite — verify nothing broken**

```bash
conda run -n job-seeker pytest tests/ -q 2>&1 | tail -10
```

Expected: same pass count as before this feature branch, no regressions.

- [ ] **Step 2: Run E2E helper unit tests**

```bash
conda run -n job-seeker pytest tests/e2e/test_helpers.py -v
```

Expected: all PASS.

- [ ] **Step 3: Run smoke pass (demo mode)**

```bash
bash manage.sh e2e demo tests/e2e/test_smoke.py 2>&1 | tail -30
```

Record any failures — these become demo data gap issues to fix separately.

- [ ] **Step 4: Run interaction pass (demo mode)**

```bash
bash manage.sh e2e demo tests/e2e/test_interactions.py 2>&1 | tail -40
```

Record XFAILs (expected) and any unexpected FAILs (open issues).

- [ ] **Step 5: Open issues for each unexpected FAIL**

For each unexpected error surfaced by the interaction pass, open a Forgejo issue:
```bash
# Example — adapt per actual failures found
gh issue create --repo git.opensourcesolarpunk.com/Circuit-Forge/peregrine \
  --title "demo: <page>/<button> triggers unexpected error" \
  --label "bug,demo-mode" \
  --body "Surfaced by E2E interaction pass. Error: <message>"
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore(e2e): final verification — harness complete"
```

---

## Quick Reference

```bash
# Unit tests only (no browser needed)
conda run -n job-seeker pytest tests/ -q

# E2E helper unit tests
conda run -n job-seeker pytest tests/e2e/test_helpers.py -v

# Demo smoke pass
bash manage.sh e2e demo tests/e2e/test_smoke.py

# Demo interaction pass
bash manage.sh e2e demo tests/e2e/test_interactions.py

# All modes (all three instances must be running)
bash manage.sh e2e all

# Headed browser for debugging (slow motion)
E2E_HEADLESS=false E2E_SLOW_MO=500 conda run -n job-seeker pytest tests/e2e/ --mode=demo -v -s

# View HTML report
conda run -n job-seeker playwright show-report tests/e2e/results/demo/playwright-report
```
