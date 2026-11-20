"""Mission-alignment keywords must match whole words (peregrine#255).

detect_mission_alignment() used `signal in text`, so short signals fired inside longer, unrelated
words. A fitness-branch posting got an animal welfare paragraph because "cat" is inside
"communicate". The note it injects tells the model the candidate finds the organisation's mission
meaningful, which makes up an interest in a cause the employer has nothing to do with.
"""
import pytest

from scripts.generate_cover_letter import _MISSION_SIGNALS, detect_mission_alignment

# Each domain's note is its own name, so a result says which domain fired.
NOTES = {domain: domain for domain in _MISSION_SIGNALS}


def fired(company: str, description: str):
    return detect_mission_alignment(company, description, mission_notes=NOTES)


def test_the_reported_posting_does_not_get_an_animal_welfare_note():
    description = (
        "We are seeking staff for our fitness branch membership team. The ability to communicate "
        "clearly is key. Work at the branch location and take applications for new members."
    )

    assert fired("Albany Y", description) != "animal_welfare"
    assert fired("Albany Y", description) is None


@pytest.mark.parametrize("text,signal", [
    ("communicate with members", "cat"),
    ("our branch location", "cat"),
    ("review each application", "cat"),
    ("indicate your preference", "cat"),
    ("join us on Zoom for the call", "zoo"),
    ("this is an ongoing role", "ngo"),
    ("grow revenue and manage the budget", "venue"),
    ("upgrade the equipment", "grade"),
    ("respond effectively to members", "eff"),
    ("a dogmatic approach", "dog"),
    ("a competent team player", "pet "),
])
def test_signals_do_not_match_inside_longer_words(text, signal):
    assert fired("Acme Corp", text) is None, f"{signal!r} matched inside {text!r}"


@pytest.mark.parametrize("text,domain", [
    ("We rescue dogs and cats", "animal_welfare"),
    ("Volunteer with the ASPCA", "animal_welfare"),
    ("A busy vet clinic", "animal_welfare"),
    ("We care for pets", "animal_welfare"),
    ("Visit the zoo", "animal_welfare"),
    ("Teaching kids after school", "education"),
    ("A K-12 platform", "education"),
    ("GDPR and CCPA compliance", "privacy"),
    ("WCAG audits and a11y reviews", "accessibility"),
    ("Integrate with the EHR", "health"),
    ("HIPAA compliance", "health"),
])
def test_real_signals_still_match_including_plurals_and_case(text, domain):
    assert fired("Acme Corp", text) == domain


def test_a_signal_with_punctuation_inside_still_matches():
    assert fired("Acme Corp", "support for k-12 students") == "education"


def test_the_company_name_counts_as_text():
    assert fired("Humane Society of Springfield", "Join our team") == "animal_welfare"


def test_text_with_no_signal_still_returns_none():
    assert fired("Acme Corp", "We sell widgets to enterprises") is None
