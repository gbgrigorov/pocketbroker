"""Shared test fixtures.

The data API gates owner/research fields behind login (see ``app.auth.scrub``). The
pre-auth test suite was written against the full, authenticated view, so by default
every test runs as a logged-in member: we override the optional-auth dependency with a
stand-in user. Tests that exercise the *anonymous* (locked) behaviour override it back
to ``None`` themselves — see ``test_auth_gating.py``.

Overriding ``current_user_optional`` also keeps tests off the real async auth DB: the
override short-circuits fastapi-users' async session entirely.
"""

import pytest

from app.auth import current_user_optional
from app.main import app
from app.routes import clear_caches


class Member:
    """Minimal stand-in for a logged-in ``User`` — ``can_view`` only checks ``is not None``."""

    id = 1
    tier = "member"
    is_active = True


@pytest.fixture(autouse=True)
def default_authenticated():
    """Default every test to a logged-in member (matches pre-auth expectations)."""
    app.dependency_overrides[current_user_optional] = lambda: Member()
    yield
    app.dependency_overrides.pop(current_user_optional, None)


@pytest.fixture(autouse=True)
def isolate_caches():
    """The /map, /cities and /entities caches are module-level; clear them so
    each test sees its own DB fixture, not a previous test's cached payload."""
    clear_caches()
    yield
    clear_caches()
