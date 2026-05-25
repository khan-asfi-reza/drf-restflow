import asyncio
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
    RefreshToken,
    TokenError,
)
from restflow.authentication.jwt import (
    ATokenBlacklist,
    decode_token,
    encode_token,
)


def _run(coro):
    return asyncio.run(coro)


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


def test_access_token_for_user_round_trips():
    user = _make_user(pk=7)
    token = AccessToken.for_user(user)
    decoded = AccessToken.verify(str(token))
    assert decoded.payload["user_id"] == 7
    assert decoded.payload["token_type"] == "access"


def test_refresh_token_for_user_round_trips():
    user = _make_user(pk=11)
    token = RefreshToken.for_user(user)
    decoded = RefreshToken.verify(str(token))
    assert decoded.payload["user_id"] == 11
    assert decoded.payload["token_type"] == "refresh"


def test_access_token_rejects_refresh_payload():
    user = _make_user()
    refresh = RefreshToken.for_user(user)
    with pytest.raises(TokenError, match="Wrong token type"):
        AccessToken.verify(str(refresh))


def test_refresh_token_rejects_access_payload():
    user = _make_user()
    access = AccessToken.for_user(user)
    with pytest.raises(TokenError, match="Wrong token type"):
        RefreshToken.verify(str(access))


def test_refresh_token_mints_fresh_access():
    user = _make_user(pk=99)
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    assert access.payload["user_id"] == 99
    assert access.payload["token_type"] == "access"
    decoded = AccessToken.verify(str(access))
    assert decoded.payload["user_id"] == 99


def test_expired_token_raises_token_error():
    payload = {
        "token_type": "access",
        "user_id": 1,
        "iat": 0,
        "exp": 1,
        "jti": "x",
    }
    raw = encode_token(payload)
    with pytest.raises(TokenError, match="expired"):
        decode_token(raw)


def test_signature_mismatch_raises_token_error():
    user = _make_user()
    token = AccessToken.for_user(user)
    raw = str(token)
    tampered = raw[:-2] + ("ab" if raw[-2:] != "ab" else "ba")
    with pytest.raises(TokenError):
        AccessToken.verify(tampered)


def test_missing_signing_key_raises_token_error():
    with override_settings(
        RESTFLOW_SETTINGS={"JWT": {"SIGNING_KEY": None}}
    ), pytest.raises(TokenError, match="SIGNING_KEY"):
        AccessToken.for_user(_make_user())


def test_decode_with_wrong_algorithm_fails():
    user = _make_user()
    token = AccessToken.for_user(user)
    raw = str(token)
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {"SIGNING_KEY": "test-signing-key-test-signing-key-32", "ALGORITHM": "HS512"},
        },
    ), pytest.raises(TokenError):
        decode_token(raw)


def test_blacklist_add_and_check():
    _run(ATokenBlacklist.add("jti-1", expires_at=(2**31 - 1)))
    assert _run(ATokenBlacklist.is_blacklisted("jti-1")) is True
    assert _run(ATokenBlacklist.is_blacklisted("jti-other")) is False


def test_refresh_token_ablacklist():
    user = _make_user()
    refresh = RefreshToken.for_user(user)
    _run(refresh.ablacklist())
    assert _run(ATokenBlacklist.is_blacklisted(refresh.jti)) is True


@pytest.mark.django_db(transaction=True)
def test_jwt_authentication_returns_user_for_valid_token():
    User = get_user_model()
    user = User.objects.create_user(username="valid", password="x", is_active=True)
    token = AccessToken.for_user(user)
    request = _make_request(token=str(token))
    auth = JWTAuthentication()
    result = _run(auth.aauthenticate(request))
    assert result is not None
    assert result[0].pk == user.pk
    assert result[1].payload["user_id"] == user.pk


def test_jwt_authentication_returns_none_without_header():
    auth = JWTAuthentication()
    assert _run(auth.aauthenticate(_make_request())) is None


def test_jwt_authentication_rejects_malformed_header():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer too many parts"))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="Bearer"):
        _run(auth.aauthenticate(request))


def test_jwt_authentication_rejects_expired_token():
    payload = {
        "token_type": "access",
        "user_id": 1,
        "iat": 0,
        "exp": 1,
        "jti": "x",
    }
    raw = encode_token(payload)
    request = _make_request(token=raw)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="expired"):
        _run(auth.aauthenticate(request))


def test_jwt_authentication_rejects_blacklisted_token():
    user = _make_user()
    token = AccessToken.for_user(user)
    _run(ATokenBlacklist.add(token.jti, expires_at=token.exp))

    request = _make_request(token=str(token))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="blacklisted"):
        _run(auth.aauthenticate(request))


def test_authenticate_header():
    auth = JWTAuthentication()
    assert auth.authenticate_header(_make_request()).startswith("Bearer")


def test_token_with_issuer_and_audience_includes_claims():
    user = _make_user(pk=42)
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "ISSUER": "restflow",
                "AUDIENCE": "restflow-clients",
            },
        }
    ):
        access = AccessToken.for_user(user)
        assert access.payload["iss"] == "restflow"
        assert access.payload["aud"] == "restflow-clients"
        refresh = RefreshToken.for_user(user)
        minted = refresh.access_token
        assert minted.payload["iss"] == "restflow"
        assert minted.payload["aud"] == "restflow-clients"


def test_resolve_token_blacklist_backend_falls_back_to_cache_for_unknown_spec():
    from restflow.authentication.jwt import (
        CacheBlacklistBackend,
        resolve_token_blacklist_backend,
    )

    backend = resolve_token_blacklist_backend(12345)
    assert isinstance(backend, CacheBlacklistBackend)


def test_atoken_blacklist_is_blacklisted_returns_false_for_empty_jti():
    assert _run(ATokenBlacklist.is_blacklisted("")) is False


def test_jwt_authentication_rejects_invalid_unicode_token():
    factory = RequestFactory()
    raw = factory.get("/")
    raw.META["HTTP_AUTHORIZATION"] = b"Bearer \xff\xfe"
    request = Request(raw)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="invalid characters"):
        _run(auth.aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_jwt_authentication_resolves_user_via_orm():
    User = get_user_model()
    user = User.objects.create_user(username="resolved", password="x", is_active=True)
    token = AccessToken.for_user(user)
    request = _make_request(token=str(token))
    auth = JWTAuthentication()
    result = _run(auth.aauthenticate(request))
    assert result is not None
    assert result[0].pk == user.pk


@pytest.mark.django_db(transaction=True)
def test_jwt_authentication_rejects_inactive_user():
    User = get_user_model()
    user = User.objects.create_user(username="inactive", password="x", is_active=False)
    token = AccessToken.for_user(user)
    request = _make_request(token=str(token))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="inactive"):
        _run(auth.aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_jwt_authentication_rejects_missing_user():
    token = AccessToken.for_user(_make_user(pk=999999))
    request = _make_request(token=str(token))
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="not found"):
        _run(auth.aauthenticate(request))


def test_jwt_authentication_rejects_token_without_user_claim():
    import time

    payload = {
        "token_type": "access",
        "iat": 0,
        "exp": int(time.time()) + 60,
        "jti": "no-user",
    }
    raw = encode_token(payload)
    request = _make_request(token=raw)
    auth = JWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="user identification"):
        _run(auth.aauthenticate(request))
