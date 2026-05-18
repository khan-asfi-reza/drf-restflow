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


def run_coro(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clear_cache():
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
    class TestThrottle(AnonRateThrottle):
        rate = "2/min"

    throttle = TestThrottle()
    request = MagicMock()
    request.user.is_authenticated = False
    request.META = {"REMOTE_ADDR": "1.2.3.4"}
    assert run_coro(throttle.aallow_request(request, None)) is True
    assert run_coro(throttle.aallow_request(request, None)) is True
    assert run_coro(throttle.aallow_request(request, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-user",
        }
    }
)
def test_user_rate_throttle_segregates_users():
    class TestThrottle(UserRateThrottle):
        rate = "1/min"

    throttle = TestThrottle()
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

    assert run_coro(throttle.aallow_request(req_a, None)) is True
    assert run_coro(throttle.aallow_request(req_b, None)) is True
    assert run_coro(throttle.aallow_request(req_a, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-scoped",
        }
    }
)
def test_scoped_rate_throttle_sync_path():
    class CustomS(ScopedRateThrottle):
        THROTTLE_RATES = {"specific-scope": "1/min"}

    throttle = CustomS()
    request = MagicMock()
    request.user.is_authenticated = True
    request.user.pk = 1
    request.META = {"REMOTE_ADDR": "1.2.3.4"}

    view = MagicMock()
    view.throttle_scope = "specific-scope"

    assert throttle.allow_request(request, view) is True
    assert throttle.allow_request(request, view) is False


def test_simple_rate_throttle_full_class_lifecycle():
    class TestThrottle(SimpleRateThrottle):
        rate = "5/min"
        scope = "x"

        def get_cache_key(self, request, view):
            return "k"

    throttle = TestThrottle()
    request = MagicMock()
    for _ in range(5):
        assert run_coro(throttle.aallow_request(request, None)) is True
    assert run_coro(throttle.aallow_request(request, None)) is False


def test_base_throttle_returns_false_via_sync_fallback():
    class CustomDeny(BaseThrottle):
        def allow_request(self, request, view):
            return False

    assert run_coro(CustomDeny().aallow_request(MagicMock(), None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-multi",
        }
    }
)
def test_multiple_throttles_evaluated_independently():
    class ThrottleA(SimpleRateThrottle):
        rate = "1/min"
        scope = "a"

        def get_cache_key(self, request, view):
            return "a"

    class ThrottleB(SimpleRateThrottle):
        rate = "2/min"
        scope = "b"

        def get_cache_key(self, request, view):
            return "b"

    a = ThrottleA()
    b = ThrottleB()
    request = MagicMock()
    assert run_coro(a.aallow_request(request, None)) is True
    assert run_coro(a.aallow_request(request, None)) is False
    assert run_coro(b.aallow_request(request, None)) is True
    assert run_coro(b.aallow_request(request, None)) is True
    assert run_coro(b.aallow_request(request, None)) is False


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-allow-then-deny",
        }
    }
)
def test_throttle_failure_returns_false_after_history_full():
    class TestThrottle(SimpleRateThrottle):
        rate = "1/min"
        scope = "deny"

        def get_cache_key(self, request, view):
            return "z"

    throttle = TestThrottle()
    request = MagicMock()
    run_coro(throttle.aallow_request(request, None))
    assert run_coro(throttle.aallow_request(request, None)) is False
    assert throttle.wait() is None or throttle.wait() > 0
