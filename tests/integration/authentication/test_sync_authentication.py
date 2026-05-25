import time
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from restflow.authentication import (
    AccessToken,
    JWTAuthentication,
)
from restflow.authentication.jwt import (
    ATokenBlacklist,
    encode_token,
)


@pytest.fixture(autouse=True)
def _jwt_settings():
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": True,
                "BLACKLIST_ALLOW_LOCMEM": True,
            },
        }
    ):
        yield


def _make_user(pk=42, active=True):
    user = MagicMock()
    user.id = pk
    user.is_active = active
    return user


def _make_request(token=None):
    factory = RequestFactory()
    extra = {}
    if token is not None:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return Request(factory.get("/", **extra))


def test_sync_authenticate_returns_none_without_header():
    auth = JWTAuthentication()
    assert auth.authenticate(_make_request()) is None


def test_sync_authenticate_returns_none_for_non_bearer_header():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz"))
    auth = JWTAuthentication()
    assert auth.authenticate(request) is None


def test_sync_authenticate_rejects_malformed_header():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer too many parts"))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="Bearer"):
        auth.authenticate(request)


def test_sync_authenticate_rejects_invalid_unicode_token():
    factory = RequestFactory()
    raw = factory.get("/")
    raw.META["HTTP_AUTHORIZATION"] = b"Bearer \xff\xfe"
    request = Request(raw)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="invalid characters"):
        auth.authenticate(request)


def test_sync_authenticate_rejects_expired_token():
    payload = {
        "token_type": "access",
        "user_id": 1,
        "iat": 0,
        "exp": 1,
        "jti": "expired",
    }
    raw = encode_token(payload)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="expired"):
        auth.authenticate(_make_request(token=raw))


def test_sync_authenticate_rejects_refresh_token_as_access():
    from restflow.authentication import RefreshToken

    user = _make_user()
    refresh = RefreshToken.for_user(user)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="Wrong token type"):
        auth.authenticate(_make_request(token=str(refresh)))


def test_sync_authenticate_rejects_blacklisted_token():
    user = _make_user()
    token = AccessToken.for_user(user)
    ATokenBlacklist.blacklist(token.jti, expires_at=token.exp)

    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="blacklisted"):
        auth.authenticate(_make_request(token=str(token)))


@pytest.mark.django_db(transaction=True)
def test_sync_authenticate_returns_user_for_valid_token():
    User = get_user_model()
    user = User.objects.create_user(
        username="sync-valid", password="x", is_active=True
    )
    token = AccessToken.for_user(user)
    auth = JWTAuthentication()
    result = auth.authenticate(_make_request(token=str(token)))
    assert result is not None
    assert result[0].pk == user.pk
    assert result[1].payload["user_id"] == user.pk


@pytest.mark.django_db(transaction=True)
def test_sync_authenticate_rejects_inactive_user():
    User = get_user_model()
    user = User.objects.create_user(
        username="sync-inactive", password="x", is_active=False
    )
    token = AccessToken.for_user(user)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="inactive"):
        auth.authenticate(_make_request(token=str(token)))


@pytest.mark.django_db(transaction=True)
def test_sync_authenticate_rejects_missing_user():
    token = AccessToken.for_user(_make_user(pk=999999))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="not found"):
        auth.authenticate(_make_request(token=str(token)))


def test_sync_authenticate_rejects_token_without_user_claim():
    payload = {
        "token_type": "access",
        "iat": 0,
        "exp": int(time.time()) + 60,
        "jti": "no-user",
    }
    raw = encode_token(payload)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="user identification"):
        auth.authenticate(_make_request(token=raw))


@pytest.mark.django_db(transaction=True)
def test_sync_authenticate_rejects_password_changed():
    User = get_user_model()
    user = User.objects.create_user(
        username="sync-pwd", password="orig", is_active=True
    )
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": True,
                "BLACKLIST_ALLOW_LOCMEM": True,
                "CHECK_REVOKE_TOKEN": True,
            },
        }
    ):
        token = AccessToken.for_user(user)
        user.set_password("changed")
        user.save()

        auth = JWTAuthentication()
        with pytest.raises(AuthenticationFailed, match="password"):
            auth.authenticate(_make_request(token=str(token)))
