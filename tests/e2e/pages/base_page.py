"""Base page object — navigation, error capture, interactable discovery."""
from __future__ import annotations
import logging
import warnings
import fnmatch
from dataclasses import dataclass

from playwright.sync_api import Page

from tests.e2e.models import ErrorRecord, ModeConfig

log = logging.getLogger(__name__)

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
    index: int


class BasePage:
    """Base page object for all Peregrine pages."""

    nav_label: str = ""

    def __init__(self, page: Page, mode: ModeConfig, console_messages: list):
        self.page = page
        self.mode = mode
        self._console_messages = console_messages

    def navigate(self) -> None:
        """Navigate to this page by clicking its sidebar nav link."""
        from tests.e2e.conftest import wait_for_streamlit
        sidebar = self.page.locator('[data-testid="stSidebarNav"]')
        sidebar.get_by_text(self.nav_label, exact=False).first.click()
        wait_for_streamlit(self.page)

    def get_errors(self) -> list[ErrorRecord]:
        from tests.e2e.conftest import get_page_errors
        return get_page_errors(self.page)

    def get_console_errors(self) -> list[str]:
        from tests.e2e.conftest import get_console_errors
        return get_console_errors(self._console_messages)

    def discover_interactables(self, skip_sidebar: bool = True) -> list[InteractableElement]:
        """Find all interactive elements on the current page, excluding sidebar."""
        found: list[InteractableElement] = []

        for selector in INTERACTABLE_SELECTORS:
            elements = self.page.query_selector_all(selector)
            for i, el in enumerate(elements):
                if skip_sidebar and el.evaluate(
                    "el => el.closest('[data-testid=\"stSidebar\"]') !== null"
                ):
                    continue
                label = (el.inner_text() or el.get_attribute("aria-label") or f"element-{i}").strip()
                label = label[:80]
                found.append(InteractableElement(label=label, selector=selector, index=i))

        for pattern in self.mode.expected_failures:
            matches = [e for e in found if fnmatch.fnmatch(e.label, pattern)]
            if len(matches) > 1:
                warnings.warn(
                    f"expected_failure pattern '{pattern}' matches {len(matches)} elements: "
                    + ", ".join(f'"{m.label}"' for m in matches),
                    stacklevel=2,
                )

        return found
