import asyncio
from unittest.mock import Mock

import pytest
from django.core.cache import cache

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    cache_result,
)
from restflow.caching.constants import CACHE_MISSING
from tests.models import SampleModel


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    CacheRegister._disconnect_all_signals()
    CacheRegister._connected_models.clear()
    yield
    cache.clear()


def test_async_wrapper_caches_and_returns_value():
    calls = []

    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        calls.append(x)
        return x * 2

    first = _run(get_x(5))
    second = _run(get_x(5))
    assert first == 10
    assert second == 10
    assert calls == [5]


def test_async_wrapper_cache_hit_returns_value_not_coroutine():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x

    _run(get_x(7))
    result = _run(get_x(7))
    assert result == 7
    assert not asyncio.iscoroutine(result)


def test_aget_with_metadata_marks_miss_then_hit():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x

    val1, meta1 = _run(get_x.aget_with_metadata(1))
    val2, meta2 = _run(get_x.aget_with_metadata(1))
    assert val1 == val2 == 1
    assert meta1["cache_status"] == "MISS"
    assert meta2["cache_status"] == "HIT"


def test_arefresh_overwrites_cache():
    counter = {"n": 0}

    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        counter["n"] += 1
        return counter["n"]

    first = _run(get_x(1))
    refreshed = _run(get_x.arefresh(1))
    assert first == 1
    assert refreshed == 2
    assert _run(get_x(1)) == 2


def test_aget_cache_only_returns_missing_then_value():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x * 10

    miss = _run(get_x.aget_cache_only(3))
    assert miss is CACHE_MISSING
    _run(get_x(3))
    hit = _run(get_x.aget_cache_only(3))
    assert hit == 30


def test_aget_cached_metadata_returns_none_then_dict():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x

    assert _run(get_x.aget_cached_metadata(2)) is None
    _run(get_x(2))
    meta = _run(get_x.aget_cached_metadata(2))
    assert meta is not None
    assert "cached_at" in meta


def test_adelete_cache_evicts_one_entry():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x

    _run(get_x(1))
    _run(get_x(2))
    _run(get_x.adelete_cache(1))
    assert _run(get_x.aget_cache_only(1)) is CACHE_MISSING
    assert _run(get_x.aget_cache_only(2)) == 2


def test_abypass_cache_runs_function_without_caching():
    counter = {"n": 0}

    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        counter["n"] += 1
        return counter["n"]

    out = _run(get_x.abypass_cache(1))
    assert out == 1
    assert _run(get_x.aget_cache_only(1)) is CACHE_MISSING


def test_sync_methods_raise_on_async_wrapped():
    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    async def get_x(x: int) -> int:
        return x

    with pytest.raises(TypeError, match="arefresh"):
        get_x.refresh(1)
    with pytest.raises(TypeError, match="aget_with_metadata"):
        get_x.get_with_metadata(1)
    with pytest.raises(TypeError, match="aget_cache_only"):
        get_x.get_cache_only(1)
    with pytest.raises(TypeError, match="aget_cached_metadata"):
        get_x.get_cached_metadata(1)
    with pytest.raises(TypeError, match="adelete_cache"):
        get_x.delete_cache(1)
    with pytest.raises(TypeError, match="adelete_by_prefix"):
        get_x.delete_by_prefix(1)
    with pytest.raises(TypeError, match="ainvalidate_all"):
        get_x.invalidate_all()
    with pytest.raises(TypeError, match="abypass_cache"):
        get_x.bypass_cache(1)


def test_async_cache_if_predicate_is_awaited():
    async def only_positive(value):
        return value > 0

    @cache_result(
        {"fields": {"x": ArgsKeyField("x")}}, ttl=60, cache_if=only_positive
    )
    async def maybe_cache(x: int) -> int:
        return x

    _run(maybe_cache(5))
    _run(maybe_cache(-3))
    assert _run(maybe_cache.aget_cache_only(5)) == 5
    assert _run(maybe_cache.aget_cache_only(-3)) is CACHE_MISSING


def test_async_cache_unless_predicate_is_awaited():
    async def is_zero(value):
        return value == 0

    @cache_result(
        {"fields": {"x": ArgsKeyField("x")}}, ttl=60, cache_unless=is_zero
    )
    async def maybe_cache(x: int) -> int:
        return x

    _run(maybe_cache(7))
    _run(maybe_cache(0))
    assert _run(maybe_cache.aget_cache_only(7)) == 7
    assert _run(maybe_cache.aget_cache_only(0)) is CACHE_MISSING


def test_async_predicate_on_sync_wrapped_raises():
    async def predicate(_):
        return True

    @cache_result(
        {"fields": {"x": ArgsKeyField("x")}}, ttl=60, cache_if=predicate
    )
    def sync_func(x: int) -> int:
        return x

    with pytest.raises(TypeError, match="async predicate"):
        sync_func(1)


def test_sync_wrapper_unchanged():
    calls = []

    @cache_result({"fields": {"x": ArgsKeyField("x")}}, ttl=60)
    def get_x(x: int) -> int:
        calls.append(x)
        return x * 3

    assert get_x(2) == 6
    assert get_x(2) == 6
    assert calls == [2]
    assert get_x.refresh(2) == 6
    assert calls == [2, 2]


@pytest.mark.django_db
def test_arun_cache_rules_drives_async_wrapper_natively():
    @cache_result(
        {"fields": {"user_id": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"user_id": "id"},
                rewarm=True,
            ),
        ],
    )
    async def get_user_data(user_id: int) -> dict:
        return {"user_id": user_id, "n": 42}

    CacheRegister.auto_discover()
    rule_ids = CacheRegister._model_rule_ids.get(SampleModel, [])
    assert rule_ids

    _run(get_user_data(1))
    assert _run(get_user_data.aget_cache_only(1)) == {"user_id": 1, "n": 42}

    from restflow.caching.tasks import arun_cache_rules

    _run(
        arun_cache_rules(
            rule_ids=rule_ids,
            rule_kwargs={str(rule_ids[0]): {"user_id": 1}},
        )
    )
    assert _run(get_user_data.aget_cache_only(1)) == {"user_id": 1, "n": 42}


@pytest.mark.django_db
def test_run_cache_rules_bridges_async_wrapper_from_sync():
    @cache_result(
        {"fields": {"user_id": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"user_id": "id"},
                rewarm=True,
            ),
        ],
    )
    async def get_user_data(user_id: int) -> dict:
        return {"user_id": user_id, "n": 99}

    CacheRegister.auto_discover()
    rule_ids = CacheRegister._model_rule_ids.get(SampleModel, [])
    assert rule_ids

    _run(get_user_data(2))

    from restflow.caching.tasks import run_cache_rules

    run_cache_rules(
        rule_ids=rule_ids,
        rule_kwargs={str(rule_ids[0]): {"user_id": 2}},
    )
    assert _run(get_user_data.aget_cache_only(2)) == {"user_id": 2, "n": 99}


def test_adelete_by_prefix_uses_adelete_pattern_when_available():
    from unittest.mock import patch

    @cache_result(
        {"fields": {"c": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
    )
    async def get_x(user_id: int) -> int:
        return user_id

    captured = {}

    async def fake_adelete_pattern(pattern):
        captured["pattern"] = pattern
        return 1

    with patch.object(
        cache, "adelete_pattern", fake_adelete_pattern, create=True
    ), patch.object(cache, "delete_pattern", Mock(), create=True):
        result = _run(get_x.adelete_by_prefix(7))
    assert result == 1
    assert captured["pattern"].endswith("*")


def test_adelete_by_prefix_falls_back_to_sync_delete_pattern():
    from unittest.mock import patch

    @cache_result(
        {"fields": {"c": ConstantKeyField("v", "1")}},
        ttl=60,
    )
    async def get_x(user_id: int) -> int:
        return user_id

    sync_dp = Mock(return_value=2)
    with patch.object(cache, "delete_pattern", sync_dp, create=True):
        if hasattr(cache, "adelete_pattern"):
            with patch.object(
                cache.__class__, "adelete_pattern", None, create=True
            ):
                result = _run(get_x.adelete_by_prefix(5))
        else:
            result = _run(get_x.adelete_by_prefix(5))
    assert result == 2
    sync_dp.assert_called_once()
    (pattern,) = sync_dp.call_args.args
    assert pattern.endswith("*")


def test_adelete_by_prefix_partition_only_falls_back_to_adelete_cache():
    calls = {"n": 0}

    @cache_result(
        {"fields": {"u": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
    )
    async def get_x(user_id: int) -> str:
        calls["n"] += 1
        return f"v{calls['n']}"

    assert _run(get_x(3)) == "v1"
    assert _run(get_x(3)) == "v1"
    assert calls["n"] == 1
    _run(get_x.adelete_by_prefix(3))
    assert _run(get_x(3)) == "v2"
    assert calls["n"] == 2


def test_adelete_by_prefix_raises_not_implemented_when_no_pattern_support():
    @cache_result(
        {"fields": {"v": ConstantKeyField("v", "1")}},
        ttl=60,
    )
    async def get_x(user_id: int) -> int:
        return user_id

    with pytest.raises(NotImplementedError, match="delete_pattern"):
        _run(get_x.adelete_by_prefix(1))


def test_ainvalidate_all_calls_delete_prefix():
    from unittest.mock import patch

    @cache_result(
        {"fields": {"v": ConstantKeyField("v", "1")}},
        ttl=60,
    )
    async def get_x(user_id: int) -> int:
        return user_id

    sync_dp = Mock(return_value=4)
    with patch.object(cache, "delete_pattern", sync_dp, create=True):
        result = _run(get_x.ainvalidate_all())
    assert result == 4
    sync_dp.assert_called_once()


def test_async_invalidator_is_awaited_via_run_sync():
    from unittest.mock import Mock

    seen = []

    async def my_invalidator(func, instance, **_extras):
        seen.append((func.__name__, instance.id))

    fake_wrapper = Mock(__name__="get_user_data")
    rule = {
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(
            model=SampleModel, invalidator=my_invalidator,
        ),
    }
    instance = Mock()
    instance.id = 7

    from restflow.helpers import run_sync

    run_sync(
        CacheRegister._run_invalidator(
            rule=rule,
            instance=instance,
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            instance_created=False,
            update_fields=None,
        )
    )

    assert seen == [("get_user_data", 7)]
