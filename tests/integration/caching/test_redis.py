import asyncio
import os

import pytest
from django.core.cache import cache, caches
from django.test import override_settings

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    KeyConstructor,
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




def test_delete_by_prefix_uses_constructor_version():
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            },
            "version": 3,
        },
        ttl=60,
    )
    def get_user_data(user_id: int):
        calls["n"] += 1
        return f"user-{user_id}-call-{calls['n']}"

    assert get_user_data(1) == "user-1-call-1"
    assert get_user_data(1) == "user-1-call-1"
    assert calls["n"] == 1

    get_user_data.delete_by_prefix(1)

    assert get_user_data(1) == "user-1-call-2"
    assert calls["n"] == 2


def test_invalidate_all_uses_constructor_version():
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            },
            "version": 3,
        },
        ttl=60,
    )
    def f(user_id: int):
        calls["n"] += 1
        return calls["n"]

    f(1)
    f(2)
    assert calls["n"] == 2
    f(1)
    f(2)
    assert calls["n"] == 2

    f.invalidate_all()

    f(1)
    f(2)
    assert calls["n"] == 4


def test_delete_by_prefix_removes_partition_only_key():
    calls = {"n": 0}

    @cache_result(
        {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
    )
    def get_user_data(user_id: int):
        calls["n"] += 1
        return f"user-{user_id}-call-{calls['n']}"

    assert get_user_data(1) == "user-1-call-1"
    assert get_user_data(1) == "user-1-call-1"
    assert calls["n"] == 1

    get_user_data.delete_by_prefix(1)

    assert get_user_data(1) == "user-1-call-2"
    assert calls["n"] == 2


def test_delete_by_prefix_partition_only_key_does_not_touch_sibling():
    calls = {"n": 0}

    @cache_result(
        {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
    )
    def get_user_data(user_id: int):
        calls["n"] += 1
        return f"user-{user_id}-call-{calls['n']}"

    assert get_user_data(1) == "user-1-call-1"
    assert get_user_data(10) == "user-10-call-2"
    assert calls["n"] == 2

    get_user_data.delete_by_prefix(1)

    assert get_user_data(10) == "user-10-call-2"
    assert get_user_data(1) == "user-1-call-3"
    assert calls["n"] == 3


def test_delete_by_prefix_targets_partition_field_passed_by_keyword():

    calls = {"n": 0}

    class K(KeyConstructor):
        c = ArgsKeyField("c", partition=True)

        class Meta:
            namespace = "keyword_partition"

    @cache_result(key_constructor=K, ttl=60)
    def ax(a, b, c, d):
        calls["n"] += 1
        return f"{a}-{b}-{c}-{d}-call-{calls['n']}"

    assert ax(1, 2, 3, 4) == "1-2-3-4-call-1"
    assert ax(9, 9, 7, 9) == "9-9-7-9-call-2"
    assert ax(1, 2, 3, 4) == "1-2-3-4-call-1"
    assert calls["n"] == 2

    ax.delete_by_prefix(c=3)

    assert ax(1, 2, 3, 4) == "1-2-3-4-call-3"
    assert ax(9, 9, 7, 9) == "9-9-7-9-call-2"
    assert calls["n"] == 3


def test_wipe_clears_one_partition_across_every_function():

    calls = {"a": 0, "b": 0}

    class SharedKC(KeyConstructor):
        user = ArgsKeyField("user_id", partition=True)
        v = ConstantKeyField("v", "1")

        class Meta:
            namespace = "wipe_shared"

    @cache_result(SharedKC, ttl=60)
    def fa(user_id):
        calls["a"] += 1
        return calls["a"]

    @cache_result(SharedKC, ttl=60)
    def fb(user_id):
        calls["b"] += 1
        return calls["b"]

    fa(1)
    fa(2)
    fb(1)
    fb(2)
    fa(1)
    fa(2)
    fb(1)
    fb(2)
    assert calls["a"] == 2
    assert calls["b"] == 2

    SharedKC.wipe(1)

    # Partition 1 missed on both functions, partition 2 still cached.
    fa(1)
    fb(1)
    assert calls["a"] == 3
    assert calls["b"] == 3
    fa(2)
    fb(2)
    assert calls["a"] == 3
    assert calls["b"] == 3


def test_wipe_without_args_clears_every_partition_across_every_function():

    calls = {"a": 0, "b": 0}

    class SharedKC(KeyConstructor):
        user = ArgsKeyField("user_id", partition=True)
        v = ConstantKeyField("v", "1")

        class Meta:
            namespace = "wipe_shared_all"

    @cache_result(SharedKC, ttl=60)
    def fa(user_id):
        calls["a"] += 1
        return calls["a"]

    @cache_result(SharedKC, ttl=60)
    def fb(user_id):
        calls["b"] += 1
        return calls["b"]

    fa(1)
    fa(2)
    fb(1)
    fb(2)
    assert calls["a"] == 2
    assert calls["b"] == 2

    SharedKC.wipe()

    fa(1)
    fa(2)
    fb(1)
    fb(2)
    assert calls["a"] == 4
    assert calls["b"] == 4


def test_delete_previous_versions_removes_only_versions_below_current():
    class KC(KeyConstructor):
        user = ArgsKeyField("user_id", partition=True)

        class Meta:
            namespace = "prev_versions"
            version = 3

    cache.set("prev_versions::k", "old-1", version=1)
    cache.set("prev_versions::k", "old-2", version=2)
    cache.set("prev_versions::k", "live", version=3)

    KC.delete_previous_versions()

    assert cache.get("prev_versions::k", version=1) is None
    assert cache.get("prev_versions::k", version=2) is None
    assert cache.get("prev_versions::k", version=3) == "live"


def test_adelete_previous_versions_removes_only_versions_below_current():
    class KC(KeyConstructor):
        user = ArgsKeyField("user_id", partition=True)

        class Meta:
            namespace = "prev_versions_async"
            version = 3

    cache.set("prev_versions_async::k", "old-1", version=1)
    cache.set("prev_versions_async::k", "old-2", version=2)
    cache.set("prev_versions_async::k", "live", version=3)

    asyncio.run(KC.adelete_previous_versions())

    assert cache.get("prev_versions_async::k", version=1) is None
    assert cache.get("prev_versions_async::k", version=2) is None
    assert cache.get("prev_versions_async::k", version=3) == "live"
