from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    CeleryDispatcher,
    ConstantKeyField,
    InvalidationRule,
    cache_result,
)
from tests.models import SampleModel

pytestmark = pytest.mark.celery


def test_celery_dispatcher_validates_celery_at_construction():
    CeleryDispatcher()


def test_celery_dispatcher_calls_celery_app_directly():
    with patch(
        "restflow.caching.dispatchers.celery._celery_current_app"
    ) as mock_app:
        CeleryDispatcher(
            task_name="myapp.tasks.bust", queue="low"
        ).dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[1],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"1": {"user_id": 1}},
        )
        mock_app.send_task.assert_called_once()
        args, kwargs = mock_app.send_task.call_args
        assert args == ("myapp.tasks.bust",)
        assert kwargs["queue"] == "low"
        assert kwargs["kwargs"]["rule_ids"] == [1]


def test_registry_has_no_celery_specific_api():
    assert hasattr(CacheRegister, "run_cache_rules")
    assert not hasattr(CacheRegister, "_dispatch_celery_task")


def test_celery_dispatcher_batch_key_groups_by_task_name_and_queue():
    a = CeleryDispatcher(task_name="t1", queue="q1")
    b = CeleryDispatcher(task_name="t1", queue="q1")
    c = CeleryDispatcher(task_name="t1", queue="q2")
    assert a.batch_key() == b.batch_key()
    assert a.batch_key() != c.batch_key()


def test_rule_with_explicit_dispatcher_string():
    User = type("M", (), {})
    rule = InvalidationRule(
        model=User,
        dispatcher="celery",
        dispatcher_config={"task_name": "x.y", "queue": "q"},
    )
    inst = rule.get_dispatcher()
    assert isinstance(inst, CeleryDispatcher)
    assert inst.config == {"task_name": "x.y", "queue": "q"}


def test_registry_groups_rules_by_dispatcher_batch_key():
    User = get_user_model()

    @cache_result(
        {"fields": {
            "u": ArgsKeyField("user_id", partition=True),
            "k": ArgsKeyField("k1"),
        }},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                dispatcher="celery",
                dispatcher_config={"task_name": "shared", "queue": "q"},
                batch=True,
            )
        ],
    )
    def a(user_id: int, k1: int = 0):  # pragma: no cover
        return (user_id, k1)

    @cache_result(
        {"fields": {
            "u": ArgsKeyField("user_id", partition=True),
            "k": ArgsKeyField("k2"),
        }},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                dispatcher="celery",
                dispatcher_config={"task_name": "shared", "queue": "q"},
                batch=True,
            )
        ],
    )
    def b(user_id: int, k2: int = 0):  # pragma: no cover
        return (user_id, k2)

    CacheRegister.auto_discover()
    rule_ids = CacheRegister._model_rule_ids.get(User, [])

    class _MockInstance:
        def __init__(self):
            self.id = 1
            self.pk = 1
            self._meta = User._meta

    with patch.object(CeleryDispatcher, "dispatch") as mock:
        CacheRegister._invalidate_via_dispatchers(
            instance=_MockInstance(),
            rule_ids=rule_ids,
            instance_created=False,
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
        )
        assert mock.call_count == 1
        sent_ids = mock.call_args.kwargs["rule_ids"]
        assert len(sent_ids) >= 2


def test_registry_with_default_batch_false_dispatches_per_rule():
    User = get_user_model()

    @cache_result(
        {"fields": {
            "u": ArgsKeyField("user_id", partition=True),
            "k": ArgsKeyField("k1"),
        }},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                dispatcher="celery",
                dispatcher_config={"task_name": "shared", "queue": "q"},
            )
        ],
    )
    def c(user_id: int, k1: int = 0):  # pragma: no cover
        return (user_id, k1)

    @cache_result(
        {"fields": {
            "u": ArgsKeyField("user_id", partition=True),
            "k": ArgsKeyField("k2"),
        }},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                dispatcher="celery",
                dispatcher_config={"task_name": "shared", "queue": "q"},
            )
        ],
    )
    def d(user_id: int, k2: int = 0):  # pragma: no cover
        return (user_id, k2)

    CacheRegister.auto_discover()
    all_rule_ids = CacheRegister._model_rule_ids.get(User, [])
    our_rule_ids = [
        rid
        for rid in all_rule_ids
        if CacheRegister.get_rule(rid)["func"].__name__ in ("c", "d")
    ]
    assert len(our_rule_ids) == 2

    class _MockInstance:
        def __init__(self):
            self.id = 2
            self.pk = 2
            self._meta = User._meta

    with patch.object(CeleryDispatcher, "dispatch") as mock:
        CacheRegister._invalidate_via_dispatchers(
            instance=_MockInstance(),
            rule_ids=our_rule_ids,
            instance_created=False,
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
        )
        assert mock.call_count == 2
        for call in mock.call_args_list:
            assert len(call.kwargs["rule_ids"]) == 1


@pytest.mark.django_db(transaction=True)
def test_celery_dispatcher_rewarms_cache_through_eager_task():
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
                dispatcher="celery",
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

    assert get_value(instance.id) == "v2"
    assert calls["n"] == 2


@pytest.mark.django_db(transaction=True)
def test_celery_dispatcher_routes_unknown_task_through_send_task():
    from celery import current_app

    cache.clear()
    captured: list[tuple] = []

    original_send_task = current_app.send_task

    def fake_send_task(name, *args, **kwargs):
        captured.append((name, args, kwargs))
        return original_send_task(name, *args, **kwargs) if False else None

    instance = SampleModel.objects.create(string_field="initial", integer_field=1)

    @cache_result(
        {"fields": {"sample": ArgsKeyField("sample_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"sample_id": "id"},
                rewarm=True,
                dispatcher="celery",
                dispatcher_config={"task_name": "not.registered.somewhere"},
            )
        ],
    )
    def get_value(sample_id: int):  # pragma: no cover
        return sample_id

    CacheRegister.auto_discover()

    with patch.object(current_app, "send_task", side_effect=fake_send_task):
        instance.string_field = "updated"
        instance.save()

    assert captured, "expected send_task to be invoked for an unknown task name"
    name, _args, kwargs = captured[0]
    assert name == "not.registered.somewhere"
    assert kwargs["kwargs"]["model_label"] == "tests.SampleModel"
    assert kwargs["kwargs"]["pk"] == instance.pk
