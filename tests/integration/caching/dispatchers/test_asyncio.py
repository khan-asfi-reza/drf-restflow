import asyncio as _asyncio
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    cache_result,
)
from restflow.caching.dispatchers.asyncio import AsyncIODispatcher


def test_asyncio_dispatcher_falls_back_to_inline_without_running_loop():
    with patch("restflow.caching.dispatchers.asyncio.run_cache_rules") as mock_apply:
        AsyncIODispatcher().dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )
        mock_apply.assert_called_once_with(
            rule_ids=[42],
            rule_kwargs={"42": {"user_id": 1}},
            dispatcher_name="asyncio",
        )


def test_asyncio_dispatcher_schedules_on_running_loop():
    captured = []

    async def fake_arun_cache_rules(rule_ids, rule_kwargs, **kwargs):
        captured.append((rule_ids, rule_kwargs))

    async def _run():
        with patch(
            "restflow.caching.dispatchers.asyncio.arun_cache_rules",
            fake_arun_cache_rules,
        ):
            AsyncIODispatcher().dispatch(
                model_label="auth.User",
                pk=1,
                rule_ids=[42],
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
                rule_kwargs={"42": {"user_id": 1}},
            )
            for _ in range(5):
                await _asyncio.sleep(0.01)

    _asyncio.run(_run())

    assert captured == [([42], {"42": {"user_id": 1}})]


@pytest.mark.django_db(transaction=True)
def test_asyncio_dispatcher_rewarms_cache_when_invoked_outside_a_running_loop():
    cache.clear()
    User = get_user_model()
    user = User.objects.create(username="async-1", email="a@example.com")
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                rewarm=True,
                dispatcher="asyncio",
            )
        ],
    )
    def get_value(user_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()

    assert get_value(user.id) == "v1"
    assert calls["n"] == 1

    rule_ids = CacheRegister._model_rule_ids.get(User, [])
    AsyncIODispatcher().dispatch(
        model_label=User._meta.label,
        pk=user.pk,
        rule_ids=rule_ids,
        signal_type=CacheRegister.SignalTypes.POST_SAVE,
        rule_kwargs={str(rule_ids[0]): {"user_id": user.id}},
    )

    assert get_value(user.id) == "v2"
    assert calls["n"] == 2


def test_asyncio_dispatcher_runs_async_wrapper_natively_on_loop():
    User = get_user_model()
    cache.clear()
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                rewarm=True,
                dispatcher="asyncio",
            )
        ],
    )
    async def get_value(user_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()
    rule_ids = CacheRegister._model_rule_ids.get(User, [])
    rule_id = rule_ids[-1]

    async def _scenario():
        first = await get_value(99)
        assert first == "v1"
        AsyncIODispatcher().dispatch(
            model_label="auth.User",
            pk=99,
            rule_ids=[rule_id],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={str(rule_id): {"user_id": 99}},
        )
        for _ in range(20):
            await _asyncio.sleep(0.01)
            if calls["n"] >= 2:
                break
        second = await get_value(99)
        return second

    second = _asyncio.run(_scenario())
    assert second == "v2"
    assert calls["n"] == 2
