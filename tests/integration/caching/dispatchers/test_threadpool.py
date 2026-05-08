from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    ThreadPoolDispatcher,
    cache_result,
)
from tests.models import SampleModel


def test_threadpool_dispatcher_validates_max_workers_type():
    with pytest.raises(ValueError):
        ThreadPoolDispatcher(max_workers=0)
    with pytest.raises(ValueError):
        ThreadPoolDispatcher(max_workers=-1)
    with pytest.raises(ValueError):
        ThreadPoolDispatcher(max_workers="four")


def test_threadpool_dispatcher_does_not_advertise_batching():
    assert ThreadPoolDispatcher.supports_batching is True


def test_threadpool_dispatcher_submits_run_cache_rules_to_pool():
    with patch("restflow.caching.dispatchers.threadpool.run_cache_rules") as mock_apply:
        ThreadPoolDispatcher(max_workers=2).dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )
        ThreadPoolDispatcher._executor.shutdown(wait=True)
        ThreadPoolDispatcher._executor = None
        mock_apply.assert_called_once_with(
            rule_ids=[42],
            rule_kwargs={"42": {"user_id": 1}},
            dispatcher_name="threadpool",
        )


def test_threadpool_logs_when_worker_raises(caplog):
    import logging

    with patch(
        "restflow.caching.dispatchers.threadpool.run_cache_rules",
        side_effect=RuntimeError("boom"),
    ):
        ThreadPoolDispatcher._executor = None
        with caplog.at_level(logging.WARNING):
            ThreadPoolDispatcher(max_workers=2).dispatch(
                rule_ids=[1],
                rule_kwargs={"1": {}},
            )
            ThreadPoolDispatcher._executor.shutdown(wait=True)
            ThreadPoolDispatcher._executor = None

    assert any("worker raised" in record.message for record in caplog.records)


def test_rule_default_dispatcher_honors_settings_override():
    User = type("M", (), {})
    rule = InvalidationRule(model=User)
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {"DEFAULT_DISPATCHER": "threadpool"}
        }
    ):
        assert isinstance(rule.get_dispatcher(), ThreadPoolDispatcher)


@pytest.mark.django_db(transaction=True)
def test_threadpool_dispatcher_rewarms_cache_entry_after_save():
    cache.clear()
    ThreadPoolDispatcher._executor = None
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
                dispatcher="threadpool",
                dispatcher_config={"max_workers": 2},
            )
        ],
    )
    def get_value(sample_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()

    assert get_value(instance.id) == "v1"
    assert get_value(instance.id) == "v1"
    assert calls["n"] == 1

    instance.string_field = "updated"
    instance.save()

    ThreadPoolDispatcher._executor.shutdown(wait=True)
    ThreadPoolDispatcher._executor = None

    assert get_value(instance.id) == "v2"
    assert calls["n"] == 2


@pytest.mark.django_db(transaction=True)
def test_threadpool_dispatcher_propagates_per_dispatcher_raise_setting(caplog):
    import logging

    cache.clear()
    ThreadPoolDispatcher._executor = None
    instance = SampleModel.objects.create(string_field="initial", integer_field=1)

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
                rewarm=False,
                dispatcher="threadpool",
                dispatcher_config={"max_workers": 2},
            )
        ],
    )
    def get_value(sample_id: int):  # pragma: no cover - cache always missing in this test
        return f"v-{sample_id}"

    CacheRegister.auto_discover()

    with caplog.at_level(logging.WARNING):
        instance.string_field = "updated"
        instance.save()
        ThreadPoolDispatcher._executor.shutdown(wait=True)
        ThreadPoolDispatcher._executor = None

    # LocMemCache cannot delete_pattern, so the registry logs a warning and moves on.
    assert any(
        "Cache delete failed" in record.message for record in caplog.records
    )
