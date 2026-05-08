import asyncio
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache as default_cache
from django.test import override_settings

from restflow.throttling import (
    AnonRateThrottle,
    BaseThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.clear()
    yield
    default_cache.clear()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-perm",
        }
    }
)
def test_anon_rate_throttle_with_anonymous_request():
    class _T(AnonRateThrottle):
        rate = "2/min"

    throttle = _T()
    request = MagicMock()
    request.user.is_authenticated = False
    request.META = {"REMOTE_ADDR": "1.2.3.4"}
    assert _run(throttle.aallow_request(request, None)) is True
    assert _run(throttle.aallow_request(request, None)) is True
    assert _run(throttle.aallow_request(request, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-user",
        }
    }
)
def test_user_rate_throttle_segregates_users():
    class _T(UserRateThrottle):
        rate = "1/min"

    throttle = _T()
    user_a = MagicMock()
    user_a.is_authenticated = True
    user_a.pk = 1

    user_b = MagicMock()
    user_b.is_authenticated = True
    user_b.pk = 2

    req_a = MagicMock()
    req_a.user = user_a
    req_a.META = {"REMOTE_ADDR": "1.1.1.1"}

    req_b = MagicMock()
    req_b.user = user_b
    req_b.META = {"REMOTE_ADDR": "1.1.1.1"}

    assert _run(throttle.aallow_request(req_a, None)) is True
    assert _run(throttle.aallow_request(req_b, None)) is True
    assert _run(throttle.aallow_request(req_a, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-scoped",
        }
    }
)
def test_scoped_rate_throttle_sync_path():
    class _S(ScopedRateThrottle):
        THROTTLE_RATES = {"specific-scope": "1/min"}

    throttle = _S()
    request = MagicMock()
    request.user.is_authenticated = True
    request.user.pk = 1
    request.META = {"REMOTE_ADDR": "1.2.3.4"}

    view = MagicMock()
    view.throttle_scope = "specific-scope"

    assert throttle.allow_request(request, view) is True
    assert throttle.allow_request(request, view) is False


def test_simple_rate_throttle_full_class_lifecycle():
    class _T(SimpleRateThrottle):
        rate = "5/min"
        scope = "x"

        def get_cache_key(self, request, view):
            return "k"

    throttle = _T()
    request = MagicMock()
    for _ in range(5):
        assert _run(throttle.aallow_request(request, None)) is True
    assert _run(throttle.aallow_request(request, None)) is False


def test_base_throttle_returns_false_via_sync_fallback():
    class CustomDeny(BaseThrottle):
        def allow_request(self, request, view):
            return False

    assert _run(CustomDeny().aallow_request(MagicMock(), None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-multi",
        }
    }
)
def test_multiple_throttles_evaluated_independently():
    class _A(SimpleRateThrottle):
        rate = "1/min"
        scope = "a"

        def get_cache_key(self, request, view):
            return "a"

    class _B(SimpleRateThrottle):
        rate = "2/min"
        scope = "b"

        def get_cache_key(self, request, view):
            return "b"

    a = _A()
    b = _B()
    request = MagicMock()
    assert _run(a.aallow_request(request, None)) is True
    assert _run(a.aallow_request(request, None)) is False
    assert _run(b.aallow_request(request, None)) is True
    assert _run(b.aallow_request(request, None)) is True
    assert _run(b.aallow_request(request, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-allow-then-deny",
        }
    }
)
def test_throttle_failure_returns_false_after_history_full():
    class _T(SimpleRateThrottle):
        rate = "1/min"
        scope = "deny"

        def get_cache_key(self, request, view):
            return "z"

    throttle = _T()
    request = MagicMock()
    _run(throttle.aallow_request(request, None))
    assert _run(throttle.aallow_request(request, None)) is False
    assert throttle.wait() is None or throttle.wait() > 0
