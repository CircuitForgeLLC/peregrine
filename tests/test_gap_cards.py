"""Tests for scripts/gap_cards.py: question cards and answer application."""

import pytest

from scripts.db_migrate import migrate_db
from scripts.experience_facts import add_fact, get_fact, list_facts, update_fact
from scripts.gap_cards import apply_answers, build_cards, jd_snippet


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "user.db"
    migrate_db(path)
    return path


def test_jd_snippet_finds_the_sentence_and_trims():
    desc = "We build things. You will use Kubernetes daily to ship. Other text."
    assert jd_snippet(desc, "kubernetes") == "You will use Kubernetes daily to ship."
    long = "Experience with Terraform " + "x" * 400 + "."
    assert len(jd_snippet(long, "Terraform")) == 240
    assert jd_snippet(desc, "Rust") == ""


def test_jd_snippet_is_whole_word():
    assert jd_snippet("We communicate clearly.", "cat") == ""
    assert jd_snippet("We love a cat here.", "cat") == "We love a cat here."


def test_build_cards_prefills_from_a_saved_fact(db):
    fid = add_fact(db, kind="experience", requirement="Kubernetes", text="Ran clusters")
    cards = build_cards(db, "You will use Kubernetes.", ["kubernetes", "Rust"])
    assert cards[0]["term"] == "kubernetes"
    assert cards[0]["snippet"] == "You will use Kubernetes."
    assert cards[0]["suggestion"] == {
        "id": fid, "kind": "experience", "text": "Ran clusters", "visibility": "document",
    }
    assert cards[1]["suggestion"] is None


def test_yes_similar_no_skip_save_the_right_kinds(db):
    result = apply_answers(db, 1, [
        {"term": "Go", "choice": "yes", "text": "Built services"},
        {"term": "Rust", "choice": "similar", "text": "Wrote C++"},
        {"term": "Cobol", "choice": "no"},
        {"term": "Perl", "choice": "skip"},
    ])
    assert result == {"approved_terms": ["Go", "Rust"], "saved": 3}
    kinds = {f.requirement: (f.kind, f.text) for f in list_facts(db)}
    assert kinds == {
        "Go": ("experience", "Built services"),
        "Rust": ("adjacent", "Wrote C++"),
        "Cobol": ("none", ""),
    }


def test_repeating_an_answer_replaces_it_instead_of_duplicating(db):
    apply_answers(db, 1, [{"term": "Go", "choice": "yes", "text": "first"}])
    apply_answers(db, 2, [{"term": " go ", "choice": "similar", "text": "second"}])
    active = list_facts(db, status="active")
    assert len(active) == 1
    assert (active[0].kind, active[0].text) == ("adjacent", "second")
    assert len(list_facts(db, status="retired")) == 1


def test_private_answers_are_saved_but_never_approved(db):
    result = apply_answers(db, 1, [
        {"term": "Go", "choice": "yes", "text": "secret", "private": True},
    ])
    assert result == {"approved_terms": [], "saved": 1}
    assert list_facts(db)[0].visibility == "private"


def test_use_saved_fact_id_approves_without_a_new_row(db):
    fid = add_fact(db, kind="experience", requirement="Go", text="Built")
    result = apply_answers(db, 1, [
        {"term": "Golang", "choice": "yes", "use_saved_fact_id": fid},
    ])
    assert result == {"approved_terms": ["Golang"], "saved": 0}
    assert len(list_facts(db, status=None)) == 1
    update_fact(db, fid, status="retired")
    with pytest.raises(ValueError):
        apply_answers(db, 1, [{"term": "Go", "choice": "yes", "use_saved_fact_id": fid}])
    with pytest.raises(ValueError):
        apply_answers(db, 1, [{"term": "Go", "choice": "yes", "use_saved_fact_id": 9999}])
    assert get_fact(db, fid).status == "retired"


def test_empty_whitespace_and_oversized_answers_are_refused(db):
    bad = [
        {"term": "Go", "choice": "yes", "text": ""},
        {"term": "Go", "choice": "similar", "text": "   \n"},
        {"term": "Go", "choice": "yes", "text": "x" * 2001},
        {"term": "", "choice": "yes", "text": "ok"},
        {"term": "   ", "choice": "no"},
        {"term": "x" * 121, "choice": "yes", "text": "ok"},
        {"term": "Go", "choice": "maybe", "text": "ok"},
    ]
    for answer in bad:
        with pytest.raises(ValueError):
            apply_answers(db, 1, [answer])
    assert list_facts(db, status=None) == []


def test_a_bad_answer_saves_nothing_from_the_batch(db):
    with pytest.raises(ValueError):
        apply_answers(db, 1, [
            {"term": "Go", "choice": "yes", "text": "fine"},
            {"term": "Rust", "choice": "yes", "text": ""},
        ])
    assert list_facts(db, status=None) == []
