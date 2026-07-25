"""Shared pytest fixtures for the Peregrine test suite."""
import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi state before each test.

    Each importlib.reload(dev_api) re-applies @limiter.limit() decorators,
    accumulating stale registrations in _route_limits on the shared limiter
    singleton. One real request then triggers N limit-checks (N = reload count),
    exhausting per-hour budgets prematurely. Clearing both _storage and
    _route_limits before each test gives each test a clean slate.
    """
    from scripts.rate_limit import limiter
    limiter._storage.reset()
    limiter._route_limits.clear()
    yield
