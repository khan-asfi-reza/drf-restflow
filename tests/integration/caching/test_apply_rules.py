import asyncio
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    cache_result,
)
from restflow.caching.tasks import (
    _resolve_raise_errors,
    arun_cache_rules,
    run_cache_rules,
)
from tests.models import SampleModel


def test_run_cache_rules_swallows_registry_errors_by_default():
    with patch.object(CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")):
        run_cache_rules([], {}, dispatcher_name="test")


def test_run_cache_rules_propagates_when_global_flag_set():
    with override_settings(
        RESTFLOW_SETTINGS={"CACHE_SETTINGS": {"DISPATCHER_RAISE_EXCEPTION": True}}
    ):
        with patch.object(
            CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError):
                run_cache_rules([], {})


def test_run_cache_rules_propagates_when_per_dispatcher_flag_set():
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {"celery": {"RAISE_EXCEPTION": True}}
            }
        }
    ), patch.object(
        CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")
    ), pytest.raises(RuntimeError):
        run_cache_rules([], {}, dispatcher_name="celery")


def test_run_cache_rules_per_dispatcher_false_overrides_global_true():
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_RAISE_EXCEPTION": True,
                "DISPATCHER_SETTINGS": {"celery": {"RAISE_EXCEPTION": False}},
            }
        }
    ), patch.object(
        CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")
    ):
        run_cache_rules([], {}, dispatcher_name="celery")


def test_resolve_raise_errors_falls_back_to_global_when_no_dispatcher_setting():
    assert _resolve_raise_errors(None) is False
    with override_settings(
        RESTFLOW_SETTINGS={"CACHE_SETTINGS": {"DISPATCHER_RAISE_EXCEPTION": True}}
    ):
        assert _resolve_raise_errors(None) is True


def test_process_rule_propagates_when_per_rule_raise_exception_true():
    class _Model:
        pass

    rule = {
        "func": Mock(__name__="get_x"),
        "invalidation_rule": InvalidationRule(
            model=_Model, raise_exception=True,
        ),
    }
    rule["func"]._is_async = False
    rule["func"].refresh.side_effect = RuntimeError("boom")
    rule["invalidation_rule"].rewarm = True

    with pytest.raises(RuntimeError):
        CacheRegister.process_rule(rule, func_kwargs={"x": 1})


def test_process_rule_swallows_when_per_rule_raise_exception_unset(caplog):
    import logging

    class _Model:
        pass

    rule = {
        "func": Mock(__name__="get_x"),
        "invalidation_rule": InvalidationRule(model=_Model),
    }
    rule["func"]._is_async = False
    rule["func"].refresh.side_effect = RuntimeError("boom")
    rule["invalidation_rule"].rewarm = True

    with caplog.at_level(logging.WARNING):
        CacheRegister.process_rule(rule, func_kwargs={"x": 1})

    assert any("Re-warm failed" in record.message for record in caplog.records)


@pytest.mark.django_db(transaction=True)
def test_run_cache_rules_rewarms_registered_wrapper_through_real_registry():
    cache.clear()
    instance = SampleModel.objects.create(string_field="initial", integer_field=1)
    calls = {"n": 0}

    @cache_result(
        {
            "fields": {
                "sample": ArgsKeyField("sample_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"sample_id": "id"},
                rewarm=True,
            )
        ],
    )
    def get_value(sample_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()
    assert get_value(instance.id) == "v1"

    rule_id = CacheRegister._model_rule_ids[SampleModel][-1]
    run_cache_rules(
        rule_ids=[rule_id],
        rule_kwargs={str(rule_id): {"sample_id": instance.id}},
        dispatcher_name="inline",
    )

    assert get_value(instance.id) == "v2"
    assert calls["n"] == 2


@pytest.mark.django_db(transaction=True)
def test_run_cache_rules_skips_rules_without_kwargs_entry():
    cache.clear()
    instance = SampleModel.objects.create(string_field="initial", integer_field=1)
    calls = {"n": 0}

    @cache_result(
        {"fields": {"sample": ArgsKeyField("sample_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"sample_id": "id"},
                rewarm=True,
            )
        ],
    )
    def get_value(sample_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()
    assert get_value(instance.id) == "v1"

    rule_id = CacheRegister._model_rule_ids[SampleModel][-1]
    run_cache_rules(rule_ids=[rule_id], rule_kwargs={})

    assert get_value(instance.id) == "v1"
    assert calls["n"] == 1


def test_arun_cache_rules_swallows_registry_errors_by_default():
    with patch.object(
        CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")
    ):
        asyncio.run(arun_cache_rules([], {}, dispatcher_name="test"))


def test_arun_cache_rules_propagates_when_global_flag_set():
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {"DISPATCHER_RAISE_EXCEPTION": True}
        }
    ), patch.object(
        CacheRegister, "run_cache_rules", side_effect=RuntimeError("boom")
    ), pytest.raises(RuntimeError):
        asyncio.run(arun_cache_rules([], {}))


def test_process_rule_propagates_when_delete_by_prefix_raises_with_raise_exception():
    class _Model:
        pass

    rule = {
        "func": Mock(__name__="get_x"),
        "invalidation_rule": InvalidationRule(
            model=_Model, raise_exception=True,
        ),
    }
    rule["func"]._is_async = False
    rule["func"].delete_by_prefix.side_effect = RuntimeError("boom")
    rule["invalidation_rule"].rewarm = False

    with pytest.raises(RuntimeError):
        CacheRegister.process_rule(rule, func_kwargs={"x": 1})


def test_async_process_rule_rewarm_success():
    class _Model:
        pass

    func = Mock(__name__="get_x")
    func._is_async = True

    async def arefresh(**_):
        return None

    func.arefresh = arefresh
    rule = {
        "func": func,
        "invalidation_rule": InvalidationRule(model=_Model, rewarm=True),
    }
    rule["invalidation_rule"].rewarm = True

    coro = CacheRegister.process_rule(rule, func_kwargs={"x": 1})
    asyncio.run(coro)


def test_async_process_rule_rewarm_failure_swallowed_logs(caplog):
    import logging

    class _Model:
        pass

    func = Mock(__name__="get_x")
    func._is_async = True

    async def arefresh(**_):
        msg = "rewarm-boom"
        raise RuntimeError(msg)

    async def adelete(**_):
        return None

    func.arefresh = arefresh
    func.adelete_by_prefix = adelete
    rule = {
        "func": func,
        "invalidation_rule": InvalidationRule(model=_Model, rewarm=True),
    }
    rule["invalidation_rule"].rewarm = True

    with caplog.at_level(logging.WARNING):
        coro = CacheRegister.process_rule(rule, func_kwargs={"x": 1})
        asyncio.run(coro)
    assert any(
        "Re-warm failed" in record.message for record in caplog.records
    )


def test_async_process_rule_rewarm_failure_raised_when_flag_true():
    class _Model:
        pass

    func = Mock(__name__="get_x")
    func._is_async = True

    async def arefresh(**_):
        msg = "rewarm-boom"
        raise RuntimeError(msg)

    async def adelete(**_):
        return None

    func.arefresh = arefresh
    func.adelete_by_prefix = adelete
    rule = {
        "func": func,
        "invalidation_rule": InvalidationRule(
            model=_Model, rewarm=True, raise_exception=True,
        ),
    }
    rule["invalidation_rule"].rewarm = True

    with pytest.raises(RuntimeError):
        coro = CacheRegister.process_rule(rule, func_kwargs={"x": 1})
        asyncio.run(coro)


def test_async_process_rule_delete_failure_swallowed_logs(caplog):
    import logging

    class _Model:
        pass

    func = Mock(__name__="get_x")
    func._is_async = True

    async def adelete(**_):
        msg = "delete-boom"
        raise RuntimeError(msg)

    func.adelete_by_prefix = adelete
    rule = {
        "func": func,
        "invalidation_rule": InvalidationRule(model=_Model, rewarm=False),
    }
    rule["invalidation_rule"].rewarm = False

    with caplog.at_level(logging.WARNING):
        coro = CacheRegister.process_rule(rule, func_kwargs={"x": 1})
        asyncio.run(coro)
    assert any(
        "Cache delete failed" in record.message for record in caplog.records
    )


def test_async_process_rule_delete_failure_raised_when_flag_true():
    class _Model:
        pass

    func = Mock(__name__="get_x")
    func._is_async = True

    async def adelete(**_):
        msg = "delete-boom"
        raise RuntimeError(msg)

    func.adelete_by_prefix = adelete
    rule = {
        "func": func,
        "invalidation_rule": InvalidationRule(
            model=_Model, rewarm=False, raise_exception=True,
        ),
    }
    rule["invalidation_rule"].rewarm = False

    with pytest.raises(RuntimeError):
        coro = CacheRegister.process_rule(rule, func_kwargs={"x": 1})
        asyncio.run(coro)


def test_run_invalidator_propagates_sync_exception_when_flag_true():
    class _Model:
        pass

    fake_wrapper = Mock(__name__="get_x")

    def boom(wrapper, instance, **_):
        msg = "inv-boom"
        raise RuntimeError(msg)

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(
            model=_Model, invalidator=boom, raise_exception=True,
        ),
    }

    with pytest.raises(RuntimeError):
        CacheRegister._run_invalidator(
            rule=rule,
            instance="x",
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            instance_created=False,
            update_fields=None,
        )


def test_async_invalidator_swallows_exception_and_logs(caplog):
    import logging

    from restflow.helpers import run_sync

    class _Model:
        pass

    fake_wrapper = Mock(__name__="get_x")

    async def boom(wrapper, instance, **_):
        msg = "async-inv-boom"
        raise RuntimeError(msg)

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(model=_Model, invalidator=boom),
    }

    with caplog.at_level(logging.WARNING):
        run_sync(
            CacheRegister._run_invalidator(
                rule=rule,
                instance="x",
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
                instance_created=False,
                update_fields=None,
            )
        )
    assert any(
        "Custom invalidator failed" in record.message
        for record in caplog.records
    )


def test_async_invalidator_propagates_when_raise_exception_true():
    from restflow.helpers import run_sync

    class _Model:
        pass

    fake_wrapper = Mock(__name__="get_x")

    async def boom(wrapper, instance, **_):
        msg = "async-inv-boom"
        raise RuntimeError(msg)

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(
            model=_Model, invalidator=boom, raise_exception=True,
        ),
    }

    with pytest.raises(RuntimeError):
        run_sync(
            CacheRegister._run_invalidator(
                rule=rule,
                instance="x",
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
                instance_created=False,
                update_fields=None,
            )
        )
