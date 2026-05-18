import sys
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


def test_django_q_dispatcher_validates_optional_dep_at_construction():
    from restflow.caching.dispatchers import django_q as dq_mod

    with patch.object(dq_mod, "_django_q_available", False):
        with pytest.raises(ImportError, match="django-q2"):
            dq_mod.DjangoQDispatcher()


def test_django_q_dispatcher_batch_key_groups_by_cluster_group_and_path():
    from restflow.caching.dispatchers import django_q as dq_mod

    with patch.object(dq_mod, "_django_q_available", True):
        a = dq_mod.DjangoQDispatcher(cluster="c1", group="g1")
        b = dq_mod.DjangoQDispatcher(cluster="c1", group="g1")
        c = dq_mod.DjangoQDispatcher(cluster="c2", group="g1")
        assert a.batch_key() == b.batch_key()
        assert a.batch_key() != c.batch_key()


def test_django_q_dispatcher_passes_cluster_when_set():
    from restflow.caching.dispatchers import django_q as dq_mod

    sent = []

    def fake_async_task(path, *args, **kwargs):
        sent.append((path, args, kwargs))

    fake_tasks = type("FakeTasks", (), {"async_task": fake_async_task})

    import sys

    with patch.object(dq_mod, "_django_q_available", True), patch.dict(
        sys.modules, {"django_q.tasks": fake_tasks}
    ):
        dq_mod.DjangoQDispatcher(cluster="hot").dispatch(
            rule_ids=[1],
            rule_kwargs={"1": {}},
        )

    assert sent[0][2]["cluster"] == "hot"


def test_django_q_dispatcher_calls_async_task_with_dotted_path():
    from restflow.caching.dispatchers import django_q as dq_mod

    sent = []

    def fake_async_task(path, *args, **kwargs):
        sent.append((path, args, kwargs))

    fake_tasks = type("FakeTasks", (), {"async_task": fake_async_task})

    with patch.object(dq_mod, "_django_q_available", True), patch.dict(
        sys.modules,
        {"django_q.tasks": fake_tasks},
    ):
        dq_mod.DjangoQDispatcher(group="cache").dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )

    assert len(sent) == 1
    path, args, kwargs = sent[0]
    assert path == "restflow.caching.tasks.run_cache_rules"
    assert args == ([42], {"42": {"user_id": 1}})
    assert kwargs == {"dispatcher_name": "django_q", "group": "cache"}


@pytest.mark.django_db(transaction=True)
def test_django_q_dispatcher_resolves_dotted_path_and_rewarms_cache():
    from restflow.caching.dispatchers import base as dispatchers_base
    from restflow.caching.dispatchers import django_q as dq_mod

    cache.clear()

    def sync_async_task(path, *args, **kwargs):
        kwargs.pop("group", None)
        kwargs.pop("cluster", None)
        worker = dispatchers_base.import_dotted(path)
        return worker(*args, **kwargs)

    fake_tasks = type("DjangoQTasks", (), {"async_task": sync_async_task})

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
                dispatcher="django_q",
            )
        ],
    )
    def get_value(sample_id: int):
        calls["n"] += 1
        return f"v{calls['n']}"

    CacheRegister.auto_discover()
    assert get_value(instance.id) == "v1"

    with patch.object(dq_mod, "_django_q_available", True), patch.dict(
        sys.modules, {"django_q.tasks": fake_tasks}
    ):
        instance.string_field = "updated"
        instance.save()

    assert get_value(instance.id) == "v2"
    assert calls["n"] == 2
