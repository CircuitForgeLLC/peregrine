"""
Smoke pass — navigate each page, wait for Streamlit to settle, assert no errors on load.
Errors on page load are always real bugs (not mode-specific).

Run: pytest tests/e2e/test_smoke.py --mode=demo
"""
from __future__ import annotations
import pytest

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

        page.goto(mode.base_url)
        wait_for_streamlit(page)

        for PageClass in PAGE_CLASSES:
            pg = PageClass(page, mode, console_msgs)
            pg.navigate()
            console_msgs.clear()

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
