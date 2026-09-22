# tests/test_theladders.py
from scripts.custom_boards.theladders import _build_job_dict, _company_from_url


def make_card(is_remote=False, location="Chicago, IL", title="Customer Success Manager"):
    return {
        "title": title,
        "href": "/job/customer-success-manager-gainsight-chicago_85434789",
        "salary": None,
        "location": location,
        "is_remote": is_remote,
    }


def test_in_person_job_stays_in_person_even_under_a_remote_search():
    """The Ladders pads a remote-filtered search with onsite jobs. A card
    with no remote badge must not be relabeled remote just because the
    search itself was filtered to "Remote"."""
    job = make_card(is_remote=False, location="Chicago, IL")

    result = _build_job_dict(
        job,
        href=job["href"],
        full_url="https://www.theladders.com" + job["href"],
        title_slug="customer-success-manager",
        location="Remote",
    )

    assert result["is_remote"] is False
    assert result["location"] == "Chicago, IL"


def test_remote_job_is_still_remote():
    job = make_card(is_remote=True, location="US-Anywhere")

    result = _build_job_dict(
        job,
        href=job["href"],
        full_url="https://www.theladders.com" + job["href"],
        title_slug="customer-success-manager",
        location="Remote",
    )

    assert result["is_remote"] is True
    assert result["location"] == "Remote"


def test_remote_job_with_a_named_location_shows_both():
    job = make_card(is_remote=True, location="Austin, TX")

    result = _build_job_dict(
        job,
        href=job["href"],
        full_url="https://www.theladders.com" + job["href"],
        title_slug="customer-success-manager",
        location="Remote",
    )

    assert result["is_remote"] is True
    assert result["location"] == "Remote — Austin, TX"


def test_in_person_job_under_a_location_specific_search_uses_its_own_location():
    job = make_card(is_remote=False, location="Chicago, IL")

    result = _build_job_dict(
        job,
        href=job["href"],
        full_url="https://www.theladders.com" + job["href"],
        title_slug="customer-success-manager",
        location="Chicago, IL",
    )

    assert result["is_remote"] is False
    assert result["location"] == "Chicago, IL"


def test_company_from_url_extracts_and_title_cases():
    company = _company_from_url(
        "/job/customer-success-manager-gainsight-chicago_85434789",
        "customer-success-manager",
    )
    assert company == "Gainsight"
