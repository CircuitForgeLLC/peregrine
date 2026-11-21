import dataclasses
import sqlite3

import pytest

from scripts.db_migrate import migrate_db
from scripts.experience_facts import (
    ExperienceFact,
    add_fact,
    delete_fact,
    find_matching_fact,
    get_fact,
    is_usable_fact,
    list_facts,
    normalize_term,
    update_fact,
    usable_facts_for_prompt,
)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "staging.db"
    migrate_db(path)
    return path


def test_migration_creates_the_table_with_the_spec_columns(db_path):
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("pragma table_info(experience_facts)")]
    conn.close()
    assert cols == [
        "id", "kind", "requirement", "text", "visibility", "status",
        "source", "origin_job_id", "created_at", "updated_at",
    ]


def test_normalize_term():
    assert normalize_term("  Scheduling! ") == "scheduling"
    assert normalize_term("Fitness   Coaching") == "fitness coaching"


def test_add_and_get_round_trips_the_users_wording_exactly(db_path):
    text = 'I ran "weekly" stand-ups at Café Münch, 2019–2021.'
    fid = add_fact(db_path, kind="experience", requirement="Scheduling", text=text)
    fact = get_fact(db_path, fid)
    assert fact is not None
    assert fact.text == text
    assert fact.requirement == "Scheduling"
    assert fact.status == "active"
    assert fact.visibility == "document"
    assert fact.source == "card"
    assert fact.origin_job_id is None


def test_add_rejects_bad_input(db_path):
    with pytest.raises(ValueError):
        add_fact(db_path, kind="maybe", requirement="x", text="y")
    with pytest.raises(ValueError):
        add_fact(db_path, kind="experience", requirement="x", text="y", visibility="public")
    with pytest.raises(ValueError):
        add_fact(db_path, kind="experience", requirement="  ", text="y")
    with pytest.raises(ValueError):
        add_fact(db_path, kind="experience", requirement="x", text="")
    with pytest.raises(ValueError):
        add_fact(db_path, kind="experience", requirement="x", text="a" * 2001)
    assert add_fact(db_path, kind="none", requirement="x", text="") > 0


def test_list_filters_by_status_and_kind_newest_first(db_path):
    a = add_fact(db_path, kind="experience", requirement="a", text="1")
    b = add_fact(db_path, kind="adjacent", requirement="b", text="2")
    c = add_fact(db_path, kind="experience", requirement="c", text="3")
    assert [f.id for f in list_facts(db_path)] == [c, b, a]
    assert [f.id for f in list_facts(db_path, kind="experience")] == [c, a]
    update_fact(db_path, b, status="retired")
    assert [f.id for f in list_facts(db_path, status="retired")] == [b]


def test_update_changes_only_the_given_fields_and_stamps_updated_at(db_path):
    fid = add_fact(db_path, kind="experience", requirement="r", text="old")
    conn = sqlite3.connect(db_path)
    conn.execute("update experience_facts set updated_at='2000-01-01 00:00:00'")
    conn.commit()
    conn.close()
    assert update_fact(db_path, fid, text="new") is True
    fact = get_fact(db_path, fid)
    assert fact.text == "new"
    assert fact.visibility == "document"
    assert fact.status == "active"
    assert fact.updated_at != "2000-01-01 00:00:00"
    assert update_fact(db_path, 9999, text="x") is False


def test_retired_facts_are_not_listed_by_default(db_path):
    fid = add_fact(db_path, kind="experience", requirement="r", text="t")
    update_fact(db_path, fid, status="retired")
    assert list_facts(db_path) == []
    assert [f.id for f in list_facts(db_path, status=None)] == [fid]


def test_delete_removes_the_row(db_path):
    fid = add_fact(db_path, kind="experience", requirement="r", text="t")
    assert delete_fact(db_path, fid) is True
    assert get_fact(db_path, fid) is None
    assert delete_fact(db_path, fid) is False


def test_find_matching_prefers_exact_then_overlap(db_path):
    fid = add_fact(db_path, kind="experience", requirement="customer support", text="t")
    assert find_matching_fact(db_path, "Customer Support").id == fid
    assert find_matching_fact(db_path, "support for customers").id == fid
    assert find_matching_fact(db_path, "fitness coaching") is None


def test_find_matching_handles_case_and_plural_variants(db_path):
    s = add_fact(db_path, kind="experience", requirement="schedule", text="t")
    p = add_fact(db_path, kind="experience", requirement="appointments", text="t")
    assert find_matching_fact(db_path, "Scheduling").id == s
    assert find_matching_fact(db_path, "appointment").id == p


def test_usable_facts_excludes_private_none_and_retired(db_path):
    add_fact(db_path, kind="experience", requirement="scheduling", text="t", visibility="private")
    add_fact(db_path, kind="none", requirement="scheduling", text="")
    gone = add_fact(db_path, kind="experience", requirement="scheduling", text="t")
    update_fact(db_path, gone, status="retired")
    assert usable_facts_for_prompt(db_path, ["scheduling"]) == {}
    ok = add_fact(db_path, kind="experience", requirement="scheduling", text="t")
    result = usable_facts_for_prompt(db_path, ["Scheduling"])
    assert list(result) == ["Scheduling"]
    assert result["Scheduling"].id == ok


def test_c_sharp_c_plus_plus_and_c_are_different_terms(db_path):
    sharp = add_fact(db_path, kind="experience", requirement="C#", text="t")
    plus = add_fact(db_path, kind="experience", requirement="C++", text="t")
    plain = add_fact(db_path, kind="experience", requirement="C", text="t")
    assert find_matching_fact(db_path, "c#").id == sharp
    assert find_matching_fact(db_path, "C++").id == plus
    assert find_matching_fact(db_path, "c").id == plain
    assert len({normalize_term("C++"), normalize_term("C#"), normalize_term("C")}) == 3
    update_fact(db_path, plus, status="retired")
    update_fact(db_path, plain, status="retired")
    assert find_matching_fact(db_path, "C++") is None
    assert find_matching_fact(db_path, "C") is None


def test_dot_net_is_not_net(db_path):
    dot = add_fact(db_path, kind="experience", requirement=".NET", text="t")
    assert find_matching_fact(db_path, ".net").id == dot
    assert find_matching_fact(db_path, "net") is None
    net = add_fact(db_path, kind="experience", requirement="net", text="t")
    assert find_matching_fact(db_path, "NET").id == net
    assert find_matching_fact(db_path, ".NET").id == dot


def test_usable_facts_does_not_back_cplusplus_with_a_csharp_fact(db_path):
    add_fact(db_path, kind="experience", requirement="C#", text="I wrote C# services")
    assert usable_facts_for_prompt(db_path, ["C++", "C"]) == {}
    assert "C#" in usable_facts_for_prompt(db_path, ["C#"])


def test_update_rejects_blanking_an_experience_fact(db_path):
    fid = add_fact(db_path, kind="experience", requirement="r", text="orig")
    for blank in ("", "   "):
        with pytest.raises(ValueError):
            update_fact(db_path, fid, text=blank)
    adj = add_fact(db_path, kind="adjacent", requirement="r2", text="orig")
    with pytest.raises(ValueError):
        update_fact(db_path, adj, text=" ")
    assert get_fact(db_path, fid).text == "orig"


def test_update_rejects_oversized_text(db_path):
    fid = add_fact(db_path, kind="experience", requirement="r", text="orig")
    with pytest.raises(ValueError):
        update_fact(db_path, fid, text="a" * 2001)
    assert update_fact(db_path, 9999, text="") is False


def test_update_allows_empty_text_on_a_none_fact(db_path):
    fid = add_fact(db_path, kind="none", requirement="r", text="")
    assert update_fact(db_path, fid, text="") is True


def test_blanked_fact_never_reaches_usable_facts(db_path):
    fid = add_fact(db_path, kind="experience", requirement="scheduling", text="orig")
    with pytest.raises(ValueError):
        update_fact(db_path, fid, text="  ")
    assert usable_facts_for_prompt(db_path, ["scheduling"])["scheduling"].text == "orig"


def test_is_usable_fact_requires_active_document_experience_or_adjacent_with_text():
    base = ExperienceFact(
        id=1, kind="experience", requirement="scheduling", text="I built the rota.",
        visibility="document", status="active", source="card", origin_job_id=None,
        created_at="", updated_at="",
    )
    assert is_usable_fact(base)
    assert is_usable_fact(dataclasses.replace(base, kind="adjacent"))
    assert not is_usable_fact(dataclasses.replace(base, visibility="private"))
    assert not is_usable_fact(dataclasses.replace(base, kind="none"))
    assert not is_usable_fact(dataclasses.replace(base, status="retired"))
    assert not is_usable_fact(dataclasses.replace(base, text=""))
    assert not is_usable_fact(dataclasses.replace(base, text="  \n "))


def test_add_fact_refuses_a_requirement_that_normalises_to_empty(db_path):
    for bad in ("???", "...", "  --  ", "+"):
        with pytest.raises(ValueError):
            add_fact(db_path, kind="experience", requirement=bad, text="t")
    assert list_facts(db_path, status=None) == []


def test_replace_fact_deletes_the_superseded_exact_match_facts(db_path):
    from scripts.experience_facts import replace_fact

    same = add_fact(db_path, kind="experience", requirement="Go", text="old")
    other = add_fact(db_path, kind="experience", requirement="Go lang", text="o")
    retired = add_fact(db_path, kind="experience", requirement="go", text="r")
    update_fact(db_path, retired, status="retired")
    new_id = replace_fact(
        db_path, kind="adjacent", requirement=" GO ", text="new", origin_job_id=3
    )
    assert new_id not in (same, other, retired)
    assert get_fact(db_path, new_id).status == "active"
    assert get_fact(db_path, new_id).origin_job_id == 3
    assert get_fact(db_path, same) is None
    assert get_fact(db_path, retired) is None
    assert get_fact(db_path, other).status == "active"
    assert sorted(f.id for f in list_facts(db_path, status=None)) == sorted([other, new_id])
    with pytest.raises(ValueError):
        replace_fact(db_path, kind="experience", requirement="???", text="t")
    with pytest.raises(ValueError):
        replace_fact(db_path, kind="experience", requirement="Go", text=" ")
    assert get_fact(db_path, new_id).status == "active"


def test_replace_fact_rolls_back_if_the_insert_fails(db_path):
    from scripts.experience_facts import replace_fact

    old = add_fact(db_path, kind="experience", requirement="Go", text="old")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TRIGGER boom BEFORE DELETE ON experience_facts "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.Error):
        replace_fact(db_path, kind="experience", requirement="Go", text="new")
    facts = list_facts(db_path, status=None)
    assert [f.id for f in facts] == [old]
    assert facts[0].status == "active"


def test_normalize_term_is_linear_time_on_a_long_run_of_plus_signs():
    import time

    start = time.perf_counter()
    normalize_term("+" * 200000 + "x")
    normalize_term("x" + "+" * 200000 + " ")
    normalize_term("x" + "!" * 200000 + "+")
    assert time.perf_counter() - start < 1.0


def test_normalize_term_keeps_cplusplus_and_csharp_intact():
    assert normalize_term("C++") == "c++"
    assert normalize_term("C#") == "c#"
    assert normalize_term("C") == "c"


# Final review C1: the user's own answer for a term decides, even when it is not usable.


def test_a_newer_none_fact_beats_an_older_overlapping_usable_fact(db_path):
    add_fact(db_path, kind="adjacent", requirement="React Native", text="Built two apps")
    assert "React" in usable_facts_for_prompt(db_path, ["React"])
    add_fact(db_path, kind="none", requirement="React Hooks")
    assert usable_facts_for_prompt(db_path, ["React"]) == {}
    add_fact(db_path, kind="none", requirement="React")
    assert usable_facts_for_prompt(db_path, ["React"]) == {}


def test_a_private_fact_for_the_exact_term_beats_an_older_overlapping_usable_fact(db_path):
    add_fact(db_path, kind="experience", requirement="Kubernetes operators", text="Wrote two")
    add_fact(db_path, kind="experience", requirement="Kubernetes", text="secret",
             visibility="private")
    assert usable_facts_for_prompt(db_path, ["Kubernetes"]) == {}
    assert find_matching_fact(db_path, "Kubernetes").visibility == "private"


def test_a_retired_exact_fact_does_not_block_a_usable_overlap_match(db_path):
    native = add_fact(db_path, kind="adjacent", requirement="React Native", text="Built apps")
    gone = add_fact(db_path, kind="none", requirement="React")
    update_fact(db_path, gone, status="retired")
    assert usable_facts_for_prompt(db_path, ["React"])["React"].id == native


def test_an_exact_usable_fact_still_wins_over_a_newer_overlap_none_fact(db_path):
    exact = add_fact(db_path, kind="experience", requirement="React", text="Built a site")
    add_fact(db_path, kind="none", requirement="React Native")
    assert usable_facts_for_prompt(db_path, ["react"])["react"].id == exact
    assert normalize_term(" C++, ") == "c++"
    assert normalize_term(".NET") == ".net"
    assert normalize_term("Scheduling!") == "scheduling"
    assert normalize_term("???") == ""
    assert normalize_term("+") == ""
