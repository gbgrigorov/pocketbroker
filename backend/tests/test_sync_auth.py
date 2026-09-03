"""The sync token gate. Fails closed: no env var configured means no access,
so a half-configured deploy can never leave the write endpoints open."""

import pytest
from fastapi import HTTPException

from app.sync.auth import require_sync_token


def test_rejects_when_env_var_is_unset(monkeypatch):
    monkeypatch.delenv("RESEARCH_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_sync_token("anything")
    assert exc.value.status_code == 403


def test_rejects_an_empty_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_sync_token("")
    assert exc.value.status_code == 403


def test_rejects_a_wrong_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException):
        require_sync_token("wrong")


def test_accepts_the_right_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    assert require_sync_token("s3cret") is None
