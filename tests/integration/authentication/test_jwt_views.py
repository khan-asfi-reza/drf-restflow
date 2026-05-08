import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from django.test import RequestFactory, override_settings

from restflow.authentication import (
    AccessToken,
    RefreshToken,
    TokenBlacklistView,
    TokenObtainView,
    TokenRefreshView,
)
from restflow.authentication.jwt import ATokenBlacklist


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _jwt_settings():
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345-test",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": True,
                "BLACKLIST_ALLOW_LOCMEM": True,
            },
        }
    ):
        yield


def _post(view, body):
    factory = RequestFactory()
    raw = factory.post(
        "/", data=json.dumps(body), content_type="application/json"
    )
    return _run(view(raw))


def _user(pk=42, active=True):
    user = MagicMock()
    user.id = pk
    user.is_active = active
    return user


def test_obtain_view_returns_access_and_refresh_for_valid_credentials(monkeypatch):
    user = _user(pk=1)
    monkeypatch.setattr(
        "restflow.authentication.jwt_views.django_aauthenticate",
        AsyncMock(return_value=user),
    )
    response = _post(
        TokenObtainView.as_view(),
        {"username": "alice", "password": "pw"},
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data

    access = AccessToken.verify(response.data["access"])
    assert access.payload["user_id"] == user.id


def test_obtain_view_rejects_bad_password(monkeypatch):
    monkeypatch.setattr(
        "restflow.authentication.jwt_views.django_aauthenticate",
        AsyncMock(return_value=None),
    )
    response = _post(
        TokenObtainView.as_view(),
        {"username": "bob", "password": "wrong"},
    )
    assert response.status_code == 401


def test_obtain_view_rejects_inactive_user(monkeypatch):
    monkeypatch.setattr(
        "restflow.authentication.jwt_views.django_aauthenticate",
        AsyncMock(return_value=_user(active=False)),
    )
    response = _post(
        TokenObtainView.as_view(),
        {"username": "carol", "password": "pw"},
    )
    assert response.status_code == 401


def test_refresh_view_mints_new_access():
    user = _user(pk=11)
    refresh = RefreshToken.for_user(user)
    response = _post(
        TokenRefreshView.as_view(),
        {"refresh": str(refresh)},
    )
    assert response.status_code == 200
    new_access = AccessToken.verify(response.data["access"])
    assert new_access.payload["user_id"] == user.id


def test_refresh_view_rotates_refresh_by_default():
    user = _user(pk=14)
    refresh = RefreshToken.for_user(user)
    response = _post(
        TokenRefreshView.as_view(),
        {"refresh": str(refresh)},
    )
    assert response.status_code == 200
    assert "refresh" in response.data
    new_refresh = RefreshToken.verify(response.data["refresh"])
    assert new_refresh.jti != refresh.jti
    assert _run(ATokenBlacklist.is_blacklisted(refresh.jti)) is True
    reuse = _post(
        TokenRefreshView.as_view(),
        {"refresh": str(refresh)},
    )
    assert reuse.status_code == 401


def test_refresh_view_does_not_rotate_when_disabled():
    user = _user(pk=15)
    refresh = RefreshToken.for_user(user)
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345-test",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": True,
                "BLACKLIST_ALLOW_LOCMEM": True,
                "ROTATE_REFRESH_TOKENS": False,
            },
        }
    ):
        response = _post(
            TokenRefreshView.as_view(),
            {"refresh": str(refresh)},
        )
    assert response.status_code == 200
    assert "refresh" not in response.data
    assert _run(ATokenBlacklist.is_blacklisted(refresh.jti)) is False


def test_refresh_view_rejects_invalid_token():
    response = _post(TokenRefreshView.as_view(), {"refresh": "not.a.token"})
    assert response.status_code == 401


def test_refresh_view_rejects_blacklisted_token():
    user = _user(pk=12)
    refresh = RefreshToken.for_user(user)
    _run(ATokenBlacklist.add(refresh.jti, expires_at=refresh.exp))
    response = _post(
        TokenRefreshView.as_view(),
        {"refresh": str(refresh)},
    )
    assert response.status_code == 401


def test_blacklist_view_revokes_refresh_token():
    user = _user(pk=13)
    refresh = RefreshToken.for_user(user)
    response = _post(
        TokenBlacklistView.as_view(),
        {"refresh": str(refresh)},
    )
    assert response.status_code == 204
    assert _run(ATokenBlacklist.is_blacklisted(refresh.jti)) is True

    refresh_response = _post(
        TokenRefreshView.as_view(),
        {"refresh": str(refresh)},
    )
    assert refresh_response.status_code == 401


def test_blacklist_view_rejects_invalid_token():
    response = _post(TokenBlacklistView.as_view(), {"refresh": "garbage"})
    assert response.status_code == 401
