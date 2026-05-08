import asyncio
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from restflow.authentication.jwt import (
    AccessToken,
    CacheBlacklistBackend,
    RefreshToken,
    TokenError,
    decode_token,
    encode_token,
)


def _run(coro):
    return asyncio.run(coro)


def get_jwt_settings(**overrides):
    base = {
        "SIGNING_KEY": "test-signing-key-1234567890abcdef",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "BLACKLIST_ENABLED": True,
        "BLACKLIST_ALLOW_LOCMEM": True,
    }
    base.update(overrides)
    return override_settings(RESTFLOW_SETTINGS={"JWT": base})


def test_encode_token_refuses_alg_none():
    with get_jwt_settings(ALGORITHM="none"), pytest.raises(TokenError, match="'none'"):
        encode_token({"foo": "bar"})


def test_decode_token_refuses_alg_none():
    with get_jwt_settings(ALGORITHM="none"), pytest.raises(TokenError, match="'none'"):
        decode_token("a.b.c")


def test_encode_token_refuses_unknown_algorithm():
    with get_jwt_settings(ALGORITHM="HS999"), pytest.raises(TokenError, match="not supported"):
        encode_token({"foo": "bar"})


def test_encode_token_refuses_pem_under_hmac():
    pem = "-----BEGIN PRIVATE KEY-----\nbase64...\n-----END PRIVATE KEY-----"
    with get_jwt_settings(SIGNING_KEY=pem, ALGORITHM="HS256"), pytest.raises(
        TokenError, match="PEM-encoded"
    ):
        encode_token({"foo": "bar"})


def test_decode_token_refuses_pem_under_hmac():
    pem = "-----BEGIN PUBLIC KEY-----\nbase64...\n-----END PUBLIC KEY-----"
    with get_jwt_settings(SIGNING_KEY=pem, ALGORITHM="HS256"), pytest.raises(
        TokenError, match="PEM-encoded"
    ):
        decode_token("a.b.c")


def test_user_id_field_allowlist_default_rejects_password():
    user = type("U", (), {"id": 1, "password": "secret", "is_active": True})()
    with get_jwt_settings(USER_ID_FIELD="password"), pytest.raises(
        TokenError, match="USER_ID_FIELD"
    ):
        AccessToken.for_user(user)


def test_user_id_field_allowlist_can_be_overridden():
    user = type("U", (), {"id": 1, "custom_id": "abc-1", "is_active": True})()
    with get_jwt_settings(
        USER_ID_FIELD="custom_id",
        USER_ID_FIELD_ALLOWLIST=("id", "custom_id"),
    ):
        token = AccessToken.for_user(user)
        assert token.payload["user_id"] == "abc-1"


def test_cache_blacklist_backend_rejects_locmem_by_default():
    backend = CacheBlacklistBackend()
    with get_jwt_settings(BLACKLIST_ALLOW_LOCMEM=False), pytest.raises(
        ImproperlyConfigured, match="LocMemCache"
    ):
        _run(backend.add("jti-x", expires_at=2**31 - 1))


def test_cache_blacklist_backend_accepts_locmem_when_opted_in():
    backend = CacheBlacklistBackend()
    with get_jwt_settings(BLACKLIST_ALLOW_LOCMEM=True):
        _run(backend.add("jti-y", expires_at=2**31 - 1))
        assert _run(backend.is_blacklisted("jti-y")) is True


def test_refresh_token_rotate_returns_new_refresh_with_fresh_jti():
    user = type("U", (), {"id": 1, "is_active": True})()
    with get_jwt_settings():
        original = RefreshToken.for_user(user)
        rotated = original.rotate()
        assert rotated.token_type == "refresh"
        assert rotated.jti != original.jti
        assert rotated.payload["user_id"] == 1


def test_refresh_token_access_token_uses_user_claim():
    user = type("U", (), {"id": 7, "is_active": True})()
    with get_jwt_settings():
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        assert access.token_type == "access"
        assert access.payload["user_id"] == 7
