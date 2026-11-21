"""LinkedIn description backfill (peregrine#272): pacing, throttles, cooldown, lock and stop rules."""
import threading

import pytest

from scripts import linkedin_backfill as lb
from tests.linkedin_backfill_helpers import (
    Clock,
    Pauses,
    Resp,
    ScriptedFetch,
    get_row,
    make_db,
    run,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    lb.reset_state()
    yield
    lb.reset_state()


# ── pacing ──────────────────────────────────────────────────────────────────────────────────────

def test_the_pause_is_between_requests_in_the_pause_range_and_not_before_the_first(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {})
    pauses = Pauses(value=3.0)

    run(db, ScriptedFetch(Resp()), pauses)

    assert pauses.bounds == [lb.PAUSE_RANGE, lb.PAUSE_RANGE]
    assert pauses.sleeps == [3.0, 3.0]


@pytest.mark.parametrize("first", [
    Resp(200, text="<html></html>"),
    Resp(404),
    ConnectionError("boom"),
    Resp(500),
], ids=["empty-parse", "404", "network-error", "500"])
def test_the_pause_also_follows_a_skip_a_404_and_an_error(tmp_path, first):
    db, _ = make_db(tmp_path, {}, {})
    pauses = Pauses(value=2.5)

    run(db, ScriptedFetch(first, Resp()), pauses)

    assert pauses.sleeps == [2.5]


# ── Retry-After ─────────────────────────────────────────────────────────────────────────────────

def test_a_single_429_honours_retry_after_clamped_and_the_batch_continues(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {})
    pauses = Pauses()
    fetch = ScriptedFetch(Resp(429, headers={"Retry-After": "9999"}), Resp(), Resp())

    res = run(db, fetch, pauses)

    assert pauses.sleeps[0] == lb.RETRY_AFTER_CAP
    assert (res.throttled, res.filled, res.stopped_early) == (1, 2, False)
    assert len(fetch.urls) == 3


def test_a_retry_after_of_zero_still_sleeps_at_least_the_minimum_pause(tmp_path):
    db, _ = make_db(tmp_path, {}, {})
    pauses = Pauses(value=lb.PAUSE_RANGE[0])

    run(db, ScriptedFetch(Resp(429, headers={"Retry-After": "0"}), Resp()), pauses)

    assert pauses.sleeps == [lb.PAUSE_RANGE[0]]
    assert pauses.sleeps[0] >= min(lb.PAUSE_RANGE)


def test_a_huge_numeric_retry_after_clamps_to_the_cap_instead_of_falling_back(tmp_path):
    db, _ = make_db(tmp_path, {}, {})
    pauses = Pauses()

    run(db, ScriptedFetch(Resp(429, headers={"Retry-After": "9" * 12}), Resp()), pauses)

    assert pauses.sleeps == [lb.RETRY_AFTER_CAP]


@pytest.mark.parametrize("value", ["Wed, 21 Oct 2026 07:28:00 GMT", "-5", "1.5", "", "abc", "²"])
def test_retry_after_that_is_not_digits_is_ignored_and_the_default_pause_is_used(tmp_path, value):
    db, _ = make_db(tmp_path, {}, {})
    pauses = Pauses(value=2.0)

    run(db, ScriptedFetch(Resp(429, headers={"Retry-After": value}), Resp()), pauses)

    assert pauses.sleeps == [2.0 * 3]


# ── what counts as a throttle ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [429, 999, 403])
def test_bot_block_statuses_are_throttles_that_stop_the_batch_and_set_the_cooldown(tmp_path, status):
    db, _ = make_db(tmp_path, {}, {}, {}, {}, {})
    clock = Clock(500.0)
    fetch = ScriptedFetch(Resp(status))

    res = run(db, fetch, clock=clock)

    assert len(fetch.urls) == lb.MAX_CONSECUTIVE_THROTTLES
    assert (res.throttled, res.errors, res.stopped_early) == (3, 0, True)
    assert res.remaining == 5
    again = ScriptedFetch(Resp())
    clock.t = 500.0 + lb.COOLDOWN_SECONDS - 1
    assert run(db, again, clock=clock).skipped_cooling_down is True
    clock.t = 500.0 + lb.COOLDOWN_SECONDS + 1
    assert run(db, again, clock=clock).skipped_cooling_down is False
    assert again.urls


def test_a_403_alone_is_a_throttle_not_an_error(tmp_path):
    db, _ = make_db(tmp_path, {}, {})

    res = run(db, ScriptedFetch(Resp(403), Resp()))

    assert (res.throttled, res.errors, res.filled) == (1, 0, 1)


def test_a_success_resets_the_consecutive_throttle_counter(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {}, {}, {})
    fetch = ScriptedFetch(Resp(429), Resp(429), Resp(), Resp(429), Resp(429), Resp())

    res = run(db, fetch)

    assert len(fetch.urls) == 6
    assert (res.throttled, res.filled, res.stopped_early) == (4, 2, False)


def test_five_throttles_in_total_stop_the_batch_and_set_the_cooldown(tmp_path):
    db, _ = make_db(tmp_path, *({} for _ in range(10)))
    clock = Clock(500.0)
    fetch = ScriptedFetch(*([Resp(429), Resp(429), Resp()] * 4))

    res = run(db, fetch, clock=clock)

    assert len(fetch.urls) == 7  # 429 429 200 429 429 200 429: the fifth throttle
    assert (res.throttled, res.stopped_early) == (lb.MAX_TOTAL_THROTTLES, True)
    assert run(db, ScriptedFetch(Resp()), clock=clock).skipped_cooling_down is True


# ── errors ──────────────────────────────────────────────────────────────────────────────────────

def test_404_and_410_are_skipped_without_counting_as_a_throttle(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {})
    fetch = ScriptedFetch(Resp(404), Resp(410), Resp(404), Resp(410))

    res = run(db, fetch)

    assert (res.skipped, res.throttled, res.errors, res.stopped_early) == (4, 0, 0, False)
    assert len(fetch.urls) == 4


def test_network_errors_are_counted_and_three_in_a_row_stop_the_batch_and_never_raise(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {}, {})
    clock = Clock()
    fetch = ScriptedFetch(ConnectionError("boom"), Resp(500), TimeoutError("slow"))

    res = run(db, fetch, clock=clock)

    assert len(fetch.urls) == lb.MAX_CONSECUTIVE_ERRORS
    assert (res.errors, res.stopped_early) == (3, True)
    assert res.remaining == 5


def test_an_error_stop_does_not_set_the_cooldown(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {}, {})
    clock = Clock()
    run(db, ScriptedFetch(ConnectionError("boom")), clock=clock)

    again = ScriptedFetch(Resp())
    res = run(db, again, clock=clock)

    assert res.skipped_cooling_down is False
    assert again.urls


# ── run budget ──────────────────────────────────────────────────────────────────────────────────

def test_a_run_that_passes_its_time_budget_stops_without_the_cooldown(tmp_path):
    db, _ = make_db(tmp_path, {}, {}, {}, {})
    clock = Clock(0.0)
    fetch = ScriptedFetch(Resp(), on_call=lambda _u: setattr(clock, "t", clock.t + 100.0))

    res = run(db, fetch, clock=clock)

    assert len(fetch.urls) == 2  # after the second request 200s have passed, over the 180s budget
    assert res.stopped_early is True
    assert res.skipped_cooling_down is False
    follow_up = ScriptedFetch(Resp())
    clock.t = 0.0
    assert run(db, follow_up, clock=clock).skipped_cooling_down is False
    assert follow_up.urls


# ── cooldown and single flight ──────────────────────────────────────────────────────────────────

def test_a_backfill_during_the_cooldown_makes_no_requests_and_touches_no_rows(tmp_path, monkeypatch):
    db, (job_id,) = make_db(tmp_path, {})
    clock = Clock(10.0)
    monkeypatch.setattr(lb, "_cooldown_until", clock() + 100)
    fetch = ScriptedFetch(Resp())
    monkeypatch.setattr(lb, "find_pending", lambda *a, **k: pytest.fail("must not read the database"))

    res = run(db, fetch, clock=clock)

    assert res.skipped_cooling_down is True
    assert fetch.urls == []
    assert get_row(db, job_id)["description"] == ""


def test_a_second_concurrent_backfill_returns_immediately_without_requests(tmp_path):
    db, _ = make_db(tmp_path, {})
    fetch = ScriptedFetch(Resp())

    assert lb._run_lock.acquire(blocking=False)
    try:
        done = []
        t = threading.Thread(target=lambda: done.append(run(db, fetch)))
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "the second backfill must not block waiting for the lock"
    finally:
        lb._run_lock.release()

    assert done[0].skipped_cooling_down is True
    assert fetch.urls == []


def test_the_lock_is_released_after_an_exception_inside_the_batch(tmp_path, monkeypatch):
    db, _ = make_db(tmp_path, {})
    real_find = lb.find_pending
    monkeypatch.setattr(lb, "find_pending", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone")))
    with pytest.raises(RuntimeError):
        run(db, ScriptedFetch(Resp(), ConnectionError("boom")))
    monkeypatch.setattr(lb, "find_pending", real_find)

    again = ScriptedFetch(Resp())
    res = run(db, again)

    assert res.skipped_cooling_down is False
    assert res.filled == 1
