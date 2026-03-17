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
                pg.navigate()
                before = pg.get_errors()

                try:
                    all_matches = page.query_selector_all(element.selector)
                    content_matches = [
                        el for el in all_matches
                        if not el.evaluate(
                            "el => el.closest('[data-testid=\"stSidebar\"]') !== null"
                        )
                    ]
                    if element.index < len(content_matches):
                        content_matches[element.index].click()
                    else:
                        continue
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

    if xpasses or failures:
        pytest.fail(
            f"{len(failures)} unexpected error(s), {len(xpasses)} xpass regression(s). "
            "See report above."
        )
