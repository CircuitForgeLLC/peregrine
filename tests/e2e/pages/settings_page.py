"""Settings page — tab-aware page object."""
from __future__ import annotations
import logging

from tests.e2e.pages.base_page import BasePage, InteractableElement

log = logging.getLogger(__name__)


class SettingsPage(BasePage):
    nav_label = "Settings"

    def discover_interactables(self, skip_sidebar: bool = True) -> list[InteractableElement]:
        """
        Settings has multiple tabs. Click each expected tab, collect interactables,
        return the full combined list.
        """
        from tests.e2e.conftest import wait_for_streamlit

        all_elements: list[InteractableElement] = []
        tab_labels = self.mode.settings_tabs

        for tab_label in tab_labels:
            # Match on full label text — handles emoji correctly.
            # Do NOT use tab_label.split()[-1]: "My Profile" and "Resume Profile"
            # both end in "Profile", causing a silent collision.
            tab_btn = self.page.locator(
                '[data-testid="stTab"] button[role="tab"]'
            ).filter(has_text=tab_label)
            if tab_btn.count() == 0:
                log.warning("Settings tab not found: %s", tab_label)
                continue
            tab_btn.first.click()
            wait_for_streamlit(self.page)

            tab_elements = super().discover_interactables(skip_sidebar=skip_sidebar)
            # Exclude tab buttons (already handled by clicking)
            tab_elements = [
                e for e in tab_elements
                if 'role="tab"' not in e.selector
            ]
            all_elements.extend(tab_elements)

        return all_elements
