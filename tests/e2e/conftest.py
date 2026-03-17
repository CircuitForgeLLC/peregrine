"""
Peregrine E2E test harness — shared fixtures and Streamlit helpers.

Run with: pytest tests/e2e/ --mode=demo|cloud|local|all
"""
from __future__ import annotations
import os
import logging
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Page, BrowserContext

from tests.e2e.models import ErrorRecord, ModeConfig, diff_errors
from tests.e2e.modes.demo import DEMO
from tests.e2e.modes.cloud import CLOUD
from tests.e2e.modes.local import LOCAL

load_dotenv(".env.e2e")
log = logging.getLogger(__name__)

_ALL_MODES = {"demo": DEMO, "cloud": CLOUD, "local": LOCAL}

_CONSOLE_NOISE = [
    "WebSocket connection",
    "WebSocket is closed",
    "_stcore/stream",
    "favicon.ico",
]


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


def pytest_collection_modifyitems(config, items):
    """Skip E2E tests if --mode not explicitly passed (belt-and-suspenders isolation)."""
    # Only skip if we're collecting from tests/e2e/ without explicit --mode
    e2e_items = [i for i in items if "tests/e2e/" in str(i.fspath)]
    if e2e_items and not any("--mode" in arg for arg in config.invocation_params.args):
        skip = pytest.mark.skip(reason="E2E tests require explicit --mode flag")
        for item in e2e_items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def active_modes(pytestconfig) -> list[ModeConfig]:
    mode_arg = pytestconfig.getoption("--mode")
    if mode_arg == "all":
        return list(_ALL_MODES.values())
    return [_ALL_MODES[mode_arg]]


@pytest.fixture(scope="session", autouse=True)
def assert_instances_reachable(active_modes):
    """Fail fast with a clear message if any target instance is not running."""
    import socket
    from urllib.parse import urlparse
    for mode in active_modes:
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


@pytest.fixture(scope="session")
def mode_contexts(active_modes, playwright) -> dict[str, BrowserContext]:
    """One browser context per active mode, with auth injected via route handler."""
    from tests.e2e.modes.cloud import _get_jwt

    headless = os.environ.get("E2E_HEADLESS", "true").lower() != "false"
    slow_mo = int(os.environ.get("E2E_SLOW_MO", "0"))
    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    contexts = {}
    for mode in active_modes:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        if mode.name == "cloud":
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


def wait_for_streamlit(page: Page, timeout: int = 10_000) -> None:
    """
    Wait until Streamlit has finished rendering.
    Uses 2000ms idle window — NOT networkidle (Playwright's networkidle uses
    500ms which is too short for Peregrine's 3s sidebar fragment poller).
    """
    try:
        page.wait_for_selector('[data-testid="stSpinner"]', state="hidden", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')"
            "?.textContent?.includes('running')",
            timeout=5_000,
        )
    except Exception:
        pass
    page.wait_for_timeout(2_000)


def get_page_errors(page) -> list[ErrorRecord]:
    """Scan DOM for Streamlit error indicators."""
    errors: list[ErrorRecord] = []

    for el in page.query_selector_all('[data-testid="stException"]'):
        errors.append(ErrorRecord(
            type="exception",
            message=el.inner_text()[:500],
            element_html=el.inner_html()[:1000],
        ))

    for el in page.query_selector_all('[data-testid="stAlert"]'):
        # Streamlit 1.35+: st.error() renders child [data-testid="stAlertContentError"]
        # kind is a React prop — NOT a DOM attribute. Child detection is authoritative.
        if el.query_selector('[data-testid="stAlertContentError"]'):
            errors.append(ErrorRecord(
                type="alert",
                message=el.inner_text()[:500],
                element_html=el.inner_html()[:1000],
            ))

    return errors


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


def screenshot_on_fail(page: Page, mode_name: str, test_name: str) -> Path:
    results_dir = Path(f"tests/e2e/results/{mode_name}/screenshots")
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{test_name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path
