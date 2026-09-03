"""Token gate for the sync endpoints.

Defence in depth, not the only defence: nginx refuses ``/api/admin/sync/`` from
the internet and the client reaches uvicorn through an SSH tunnel. The token
means SSH access alone is still not enough.

Fails closed — an unset ``RESEARCH_API_TOKEN`` rejects everything, so a deploy
that forgot the secret is unusable rather than wide open.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_sync_token(x_sync_token: str = Header(default="")) -> None:
    expected = os.environ.get("RESEARCH_API_TOKEN")
    if not expected or not secrets.compare_digest(x_sync_token, expected):
        raise HTTPException(status_code=403, detail="forbidden")
