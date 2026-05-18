import asyncio
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache as default_cache
from django.test import override_settings

from restflow.throttling import BaseThrottle, SimpleRateThrottle


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    default_cache.clear()
    yield
    default_cache.clear()


class _FixedRateThrottle(SimpleRateThrottle):
    rate = "3/min"
    scope = "test"

    def get_cache_key(self, request, view):
        return "throttle_test_fixed"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-test",
        }
    }
)
def test_simple_rate_throttle_aallow_request_allows_under_limit():
    throttle = _FixedRateThrottle()
    request = MagicMock()
    for _ in range(3):
        assert _run(throttle.aallow_request(request, None)) is True


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-test",
        }
    }
)
def test_simple_rate_throttle_aallow_request_blocks_over_limit():
    throttle = _FixedRateThrottle()
    request = MagicMock()
    for _ in range(3):
        _run(throttle.aallow_request(request, None))
    assert _run(throttle.aallow_request(request, None)) is False


def test_simple_rate_throttle_aallow_returns_true_when_no_key():
    class _NoKey(SimpleRateThrottle):
        rate = "3/min"
        scope = "test"

        def get_cache_key(self, request, view):
            return None

    assert _run(_NoKey().aallow_request(MagicMock(), None)) is True


def test_base_throttle_aallow_falls_back_to_sync():
    class CustomSync(BaseThrottle):
        def allow_request(self, request, view):
            return True

    assert _run(CustomSync().aallow_request(MagicMock(), None)) is True


def test_simple_rate_throttle_aallow_returns_true_when_rate_is_none():
    throttle = _FixedRateThrottle()
    throttle.rate = None
    assert _run(throttle.aallow_request(MagicMock(), None)) is True


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "throttle-evict",
        }
    }
)
def test_simple_rate_throttle_evicts_old_history_entries():
    class _Throttle(SimpleRateThrottle):
        rate = "3/min"
        scope = "evict"

        def get_cache_key(self, request, view):
            return "throttle_test_evict"

    throttle = _Throttle()
    request = MagicMock()
    very_old = throttle.timer() - 9999
    _run(throttle.cache.aset("throttle_test_evict", [very_old, very_old]))

    assert _run(throttle.aallow_request(request, None)) is True
    assert throttle.history[-1] > very_old
