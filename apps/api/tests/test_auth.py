import pytest
from fastapi import HTTPException

from app.api.auth import require_admin_token
from app.core.config import settings


def test_require_admin_token_is_noop_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", None)
    require_admin_token(authorization=None)
    require_admin_token(authorization="Bearer anything")


def test_require_admin_token_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(authorization=None)
    assert exc_info.value.status_code == 401


def test_require_admin_token_rejects_wrong_scheme(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(authorization="Basic abc")
    assert exc_info.value.status_code == 401


def test_require_admin_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(authorization="Bearer wrong")
    assert exc_info.value.status_code == 401


def test_require_admin_token_accepts_correct_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret")
    require_admin_token(authorization="Bearer secret")
