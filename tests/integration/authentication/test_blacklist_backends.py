import asyncio
import os
from datetime import timedelta

import pytest
from django.test import override_settings

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

from restflow.authentication import (
    BlacklistBackend,
    CacheBlacklistBackend,
    ModelBlacklistBackend,
    RefreshToken,
)
from restflow.authentication.jwt import (
    ATokenBlacklist,
    resolve_token_blacklist_backend,
)


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
                "BLACKLIST_BACKEND": (
                    "restflow.authentication.jwt.CacheBlacklistBackend"
                ),
                "BLACKLIST_ALLOW_LOCMEM": True,
            },
        }
    ):
        yield


def testresolve_token_blacklist_backend_accepts_string():
    backend = resolve_token_blacklist_backend(
        "restflow.authentication.jwt.CacheBlacklistBackend"
    )
    assert isinstance(backend, CacheBlacklistBackend)


def testresolve_token_blacklist_backend_accepts_class():
    backend = resolve_token_blacklist_backend(CacheBlacklistBackend)
    assert isinstance(backend, CacheBlacklistBackend)


def testresolve_token_blacklist_backend_accepts_instance():
    instance = CacheBlacklistBackend()
    assert resolve_token_blacklist_backend(instance) is instance


def test_cache_backend_round_trip():
    backend = CacheBlacklistBackend()
    _run(backend.add("jti-cache-1", expires_at=(2**31 - 1)))
    assert _run(backend.is_blacklisted("jti-cache-1")) is True
    assert _run(backend.is_blacklisted("never-added")) is False


def test_facade_uses_configured_cache_backend_by_default():
    _run(ATokenBlacklist.add("jti-default", expires_at=(2**31 - 1)))
    assert _run(ATokenBlacklist.is_blacklisted("jti-default")) is True


@pytest.mark.django_db(transaction=True)
def test_model_backend_persists_row_on_add():
    from restflow.authentication.models import BlacklistedToken

    backend = ModelBlacklistBackend()
    _run(backend.add("jti-db-1", expires_at=(2**31 - 1)))

    row = BlacklistedToken.objects.get(jti="jti-db-1")
    assert row.expires_at is not None


@pytest.mark.django_db(transaction=True)
def test_model_backend_returns_true_for_existing_row():
    from datetime import datetime, timezone

    from restflow.authentication.models import BlacklistedToken

    BlacklistedToken.objects.create(
        jti="jti-db-1",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )

    backend = ModelBlacklistBackend()
    assert _run(backend.is_blacklisted("jti-db-1")) is True
    assert _run(backend.is_blacklisted("never-added")) is False


@pytest.mark.django_db(transaction=True)
def test_facade_switches_to_model_backend_when_configured():
    from restflow.authentication.models import BlacklistedToken

    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345-test",
                "BLACKLIST_BACKEND": (
                    "restflow.authentication.jwt.ModelBlacklistBackend"
                ),
            },
        }
    ):
        _run(ATokenBlacklist.add("jti-switched", expires_at=(2**31 - 1)))

    assert BlacklistedToken.objects.filter(jti="jti-switched").exists()


@pytest.mark.django_db(transaction=True)
def test_model_cleanup_expired_removes_only_past_rows():
    from datetime import datetime, timezone

    from restflow.authentication.models import BlacklistedToken

    BlacklistedToken.objects.create(
        jti="future",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    BlacklistedToken.objects.create(
        jti="past",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    deleted = BlacklistedToken.cleanup_expired()
    assert deleted == 1
    assert BlacklistedToken.objects.filter(jti="future").exists()
    assert not BlacklistedToken.objects.filter(jti="past").exists()


@pytest.mark.django_db(transaction=True)
def test_model_acleanup_expired_filters_and_deletes():
    from datetime import datetime, timezone

    from restflow.authentication.models import BlacklistedToken

    BlacklistedToken.objects.create(
        jti="acleanup-future",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    BlacklistedToken.objects.create(
        jti="acleanup-past-1",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
    )
    BlacklistedToken.objects.create(
        jti="acleanup-past-2",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(minutes=30),
    )

    deleted = _run(BlacklistedToken.acleanup_expired())
    assert deleted == 2
    assert BlacklistedToken.objects.filter(jti="acleanup-future").exists()
    assert not BlacklistedToken.objects.filter(jti="acleanup-past-1").exists()
    assert not BlacklistedToken.objects.filter(jti="acleanup-past-2").exists()


@pytest.mark.django_db(transaction=True)
def test_model_str_includes_jti_and_expires_at():
    from datetime import datetime, timezone

    from restflow.authentication.models import BlacklistedToken

    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    row = BlacklistedToken.objects.create(jti="rendered", expires_at=expires_at)
    text = str(row)
    assert "rendered" in text
    assert "BlacklistedToken" in text


def test_refresh_token_ablacklist_uses_facade():
    user_pk = 99
    user = type("U", (), {"id": user_pk, "is_active": True})()
    refresh = RefreshToken.for_user(user)
    _run(refresh.ablacklist())
    assert _run(ATokenBlacklist.is_blacklisted(refresh.jti)) is True


def test_blacklist_backend_subclass_protocol():
    class CustomBackend(BlacklistBackend):
        store: set[str] = set()

        async def add(self, jti, *, expires_at):
            self.store.add(jti)

        async def is_blacklisted(self, jti):
            return jti in self.store

    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345-test",
                "BLACKLIST_BACKEND": CustomBackend,
            },
        }
    ):
        _run(ATokenBlacklist.add("custom-1", expires_at=99999))
        assert _run(ATokenBlacklist.is_blacklisted("custom-1")) is True
