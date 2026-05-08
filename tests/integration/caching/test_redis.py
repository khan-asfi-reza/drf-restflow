import os

import pytest
from django.core.cache import cache, caches
from django.test import override_settings

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    cache_result,
)

pytestmark = pytest.mark.redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/15")


def _redis_reachable():
    try:
        import redis

        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        return client.ping()
    except Exception:
        return False


if not _redis_reachable():
    pytest.skip(
        f"Redis not reachable at {REDIS_URL}, skipping redis-marked tests.",
        allow_module_level=True,
    )


REDIS_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}


@pytest.fixture(autouse=True)
def _redis_cache_and_clean_registry():
    with override_settings(CACHES=REDIS_CACHE_SETTINGS):
        # cache is a ConnectionProxy that re-resolves under override_settings,
        # but caches['default'] may have stale state from a prior test.
        caches["default"].clear()
        CacheRegister.clear()
        yield
        caches["default"].clear()
        CacheRegister.clear()


def test_django_redis_backend_advertises_delete_pattern():
    assert hasattr(cache, "delete_pattern")


def test_delete_by_prefix_removes_matching_keys_in_redis():
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
    )
    def get_user_data(user_id: int):
        calls["n"] += 1
        return f"user-{user_id}-call-{calls['n']}"

    assert get_user_data(1) == "user-1-call-1"
    assert get_user_data(2) == "user-2-call-2"
    assert get_user_data(1) == "user-1-call-1"
    assert get_user_data(2) == "user-2-call-2"
    assert calls["n"] == 2

    get_user_data.delete_by_prefix(1)

    assert get_user_data(1) == "user-1-call-3"  # re-executed
    assert get_user_data(2) == "user-2-call-2"  # still cached
    assert calls["n"] == 3


def test_delete_by_prefix_with_no_args_invalidates_all_partitions():
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
    )
    def f():
        calls["n"] += 1
        return calls["n"]

    f()
    f()
    assert calls["n"] == 1

    f.delete_by_prefix()
    f()
    assert calls["n"] == 2


def test_invalidate_all_clears_every_key_for_wrapper():
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
    )
    def f(user_id: int):
        calls["n"] += 1
        return calls["n"]

    f(1)
    f(2)
    f(3)
    assert calls["n"] == 3

    # All cached.
    f(1)
    f(2)
    f(3)
    assert calls["n"] == 3

    f.invalidate_all()

    # Every partition must miss now.
    f(1)
    f(2)
    f(3)
    assert calls["n"] == 6


def test_invalidate_all_does_not_touch_other_wrappers():

    @cache_result({"fields": {"v": ConstantKeyField("v", "1")}}, ttl=60)
    def alpha():
        return "alpha-result"

    @cache_result({"fields": {"v": ConstantKeyField("v", "1")}}, ttl=60)
    def beta():
        return "beta-result"

    alpha()
    beta()
    assert alpha() == "alpha-result"
    assert beta() == "beta-result"

    alpha.invalidate_all()
    alpha_prefix = alpha._constructor.build_key_prefix(alpha._func, (), {})
    beta_prefix = beta._constructor.build_key_prefix(beta._func, (), {})

    assert not list(cache.iter_keys(f"{alpha_prefix}*"))
    assert list(cache.iter_keys(f"{beta_prefix}*"))


