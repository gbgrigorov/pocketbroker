"""Authentication + the central access seam.

Login (email/password **and** Google) is provided by the **fastapi-users** library
against an async SQLAlchemy session — the rest of the app stays sync. The only
project-specific logic in this module is :func:`can_view` / :func:`scrub`, which
decide what builder/entity fields each viewer may see.

Why a second (async) engine: fastapi-users' SQLAlchemy adapter requires an
``AsyncSession``; psycopg3 speaks both sync and async over the same ``DATABASE_URL``,
so we open an async engine here just for the auth tables and leave every existing
data route on the sync ``get_session``.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import (AuthenticationBackend, BearerTransport,
                                          JWTStrategy)
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from app.db import DATABASE_URL
from app.models import OAuthAccount, User

# --- secrets / config (env-driven; safe insecure fallbacks for local dev) ----
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-change-me")
RESET_SECRET = os.environ.get("RESET_SECRET", JWT_SECRET)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
# Where the SPA lives — the Google callback redirects back here with the token.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
# Optional explicit callback URL (must match Google console); else derived from request.
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
TOKEN_LIFETIME_S = 60 * 60 * 24 * 30  # 30 days

# --- async DB plumbing, used ONLY by fastapi-users ---------------------------
_async_engine = create_async_engine(DATABASE_URL)
_async_session_maker = async_sessionmaker(_async_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with _async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = RESET_SECRET
    verification_token_secret = RESET_SECRET


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=JWT_SECRET, lifetime_seconds=TOKEN_LIFETIME_S)


auth_backend = AuthenticationBackend(
    name="jwt", transport=bearer_transport, get_strategy=get_jwt_strategy
)

fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend])

# Single dependency objects — imported by routes.py AND overridden in tests, so they
# must be created exactly once (each fastapi_users.current_user() call is a new fn).
current_user = fastapi_users.current_user(active=True)
current_user_optional = fastapi_users.current_user(active=True, optional=True)
# Admin gate: 401 for anonymous, 403 for a logged-in non-superuser.
current_superuser = fastapi_users.current_user(active=True, superuser=True)

google_oauth_client = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)


# --- Google OAuth: SPA-friendly redirect flow --------------------------------
# fastapi-users' stock OAuth router returns the JWT as raw JSON, which dumps the user
# on a JSON page. These two thin routes use the library's own building blocks
# (user_manager.oauth_callback + the JWT strategy) but finish with a RedirectResponse
# back into the SPA with the token in the URL hash, so the frontend can pick it up.
google_router = APIRouter()
_google_callback = OAuth2AuthorizeCallback(
    google_oauth_client, route_name="google_oauth_callback"
)


def _callback_url(request: Request) -> str:
    return GOOGLE_REDIRECT_URI or str(request.url_for("google_oauth_callback"))


@google_router.get("/authorize")
async def google_authorize(request: Request) -> dict:
    """Return the Google consent URL; the SPA redirects the browser to it."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        # Fail clearly here instead of bouncing the user to Google's "missing
        # client_id" error page. The frontend shows this as a friendly notice.
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on the server yet.",
        )
    url = await google_oauth_client.get_authorization_url(
        _callback_url(request), scope=["openid", "email", "profile"]
    )
    return {"authorization_url": url}


@google_router.get("/callback", name="google_oauth_callback")
async def google_callback(
    request: Request,
    access_token_state=Depends(_google_callback),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Handle Google's redirect: upsert the user, mint our JWT, bounce to the SPA."""
    token, _state = access_token_state
    account_id, account_email = await google_oauth_client.get_id_email(
        token["access_token"]
    )
    if account_email is None:
        raise HTTPException(status_code=400, detail="Google account has no email")
    user = await user_manager.oauth_callback(
        "google",
        token["access_token"],
        account_id,
        account_email,
        token.get("expires_at"),
        token.get("refresh_token"),
        request,
        associate_by_email=True,
        is_verified_by_default=True,
    )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    jwt = await get_jwt_strategy().write_token(user)
    return RedirectResponse(f"{FRONTEND_URL}/auth?token={jwt}")


# --- access seam: what each viewer may see -----------------------------------
# Locked field groups, removed from a payload for viewers who can't see them. Future
# tiers / per-builder paid reports change ONLY can_view() — every endpoint already
# routes through scrub(), so nothing else moves.
FIELD_GROUPS = {
    "people": ["owners", "managers", "owns", "manages"],
    "research": ["signals", "signal_counts", "insolvency_flag", "tax_debt_bgn",
                 "has_seizure", "seizure_count", "seizure_last_at", "seizure_source_url"],
    # future: "premium": [...]
}


def can_view(user: Optional[User], group: str, resource: Optional[str] = None) -> bool:
    """Today: any logged-in member sees people + research. Later: branch on
    ``user.tier`` or look up an entitlement for ``resource`` (a builder ЕИК)."""
    return user is not None


def scrub(payload: dict, user: Optional[User], resource: Optional[str] = None) -> dict:
    """Drop the field groups ``user`` may not see, tagging them under ``locked`` so the
    frontend knows to show a sign-in CTA. Mutates and returns ``payload``."""
    for group, keys in FIELD_GROUPS.items():
        if not can_view(user, group, resource):
            for key in keys:
                payload.pop(key, None)
            payload.setdefault("locked", []).append(group)
    return payload
