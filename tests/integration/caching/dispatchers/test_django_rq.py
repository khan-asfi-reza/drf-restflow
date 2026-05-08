from unittest.mock import patch

import pytest
from django.core.cache import cache

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    cache_result,
)
from tests.models import SampleModel


def test_django_rq_dispatcher_validates_optional_dep_at_construction():
    from restflow.caching.dispatchers import django_rq as drq_mod

    with patch.object(drq_mod, "django_rq", None):
        with pytest.raises(ImportError, match="django-rq"):
            drq_mod.DjangoRqDispatcher()


def test_django_rq_dispatcher_batch_key_groups_by_queue_and_path():
    from restflow.caching.dispatchers import django_rq as drq_mod

    fake_django_rq = object()
    with patch.object(drq_mod, "django_rq", fake_django_rq):
        a = drq_mod.DjangoRqDispatcher(queue="q1")
        b = drq_mod.DjangoRqDispatcher(queue="q1")
        c = drq_mod.DjangoRqDispatcher(queue="q2")
        assert a.batch_key() == b.batch_key()
        assert a.batch_key() != c.batch_key()


def test_django_rq_dispatcher_enqueues_run_cache_rules():
    from restflow.caching.dispatchers import django_rq as drq_mod
    from restflow.caching.tasks import run_cache_rules as public_run_cache_rules

    fake_django_rq = type(
        "FakeRq",
        (),
        {"get_queue": lambda name: fake_django_rq.queues.setdefault(name, MockQueue())},
    )
    fake_django_rq.queues = {}

    class MockQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, func, *args, **kwargs):
            self.enqueued.append((func, args, kwargs))

    with patch.object(drq_mod, "django_rq", fake_django_rq):
        drq_mod.DjangoRqDispatcher(queue="invalidation").dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )

    queue = fake_django_rq.queues["invalidation"]
    assert len(queue.enqueued) == 1
    func, args, kwargs = queue.enqueued[0]
    assert func is public_run_cache_rules
    assert args == ([42], {"42": {"user_id": 1}})
    assert kwargs == {"dispatcher_name": "django_rq"}


@pytest.mark.django_db(transaction=True)
def test_django_rq_dispatcher_executes_worker_function_and_rewarms_cache():
    from restflow.caching.dispatchers import django_rq as drq_mod

    cache.clear()

    class _SyncQueue:
        def enqueue(self, func, *args, **kwargs):
            kwargs.pop("job_timeout", None)
            kwargs.pop("description", None)
            return func(*args, **kwargs)

    sync_queue = _SyncQueue()

    class _SyncRq:
        @staticmethod
        def get_queue(name):  # noqa: ARG004
            return sync_queue

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
                dispatcher="django_rq",
                dispatcher_config={"queue": "default"},
            )
        ],
    )
    def get_value(sample_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()

    assert get_value(instance.id) == "v1"
    assert calls["n"] == 1

    with patch.object(drq_mod, "django_rq", _SyncRq):
        instance.string_field = "updated"
        instance.save()

    assert get_value(instance.id) == "v2"
    assert calls["n"] == 2
