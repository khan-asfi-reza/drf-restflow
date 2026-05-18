from unittest.mock import patch

import pytest

from restflow.caching import CacheRegister


def test_dramatiq_dispatcher_validates_optional_dep_at_construction():
    from restflow.caching.dispatchers import dramatiq as drm_mod

    with patch.object(drm_mod, "_dramatiq", None):
        with pytest.raises(ImportError, match="dramatiq"):
            drm_mod.DramatiqDispatcher()


def test_dramatiq_dispatcher_batch_key_groups_by_queue_and_actor_name():
    from restflow.caching.dispatchers import dramatiq as drm_mod

    with patch.object(drm_mod, "_dramatiq", object()):
        a = drm_mod.DramatiqDispatcher(queue="q1", actor_name="x")
        b = drm_mod.DramatiqDispatcher(queue="q1", actor_name="x")
        c = drm_mod.DramatiqDispatcher(queue="q2", actor_name="x")
        assert a.batch_key() == b.batch_key()
        assert a.batch_key() != c.batch_key()


def test_register_actor_creates_real_dramatiq_actor():
    pytest.importorskip("dramatiq")

    import dramatiq
    from dramatiq.brokers.stub import StubBroker

    from restflow.caching.dispatchers.dramatiq import register_actor

    broker = StubBroker()
    dramatiq.set_broker(broker)
    try:
        actor = register_actor(actor_name="test.restflow.actor")
        assert actor.actor_name == "test.restflow.actor"
        assert "test.restflow.actor" in broker.actors

        with patch("restflow.caching.dispatchers.dramatiq.run_cache_rules") as mock_apply:
            actor.fn([42], {"42": {"user_id": 1}})
            mock_apply.assert_called_once_with(
                [42],
                {"42": {"user_id": 1}},
                dispatcher_name="dramatiq",
            )
    finally:
        broker.close()


def test_dramatiq_dispatcher_sends_to_actor_with_resolved_queue():
    from restflow.caching.dispatchers import dramatiq as drm_mod

    sent = []

    class FakeActor:
        def send_with_options(self, *, args, queue_name):
            sent.append((args, queue_name))

    fake_dramatiq = type("FakeDramatiq", (), {})()

    def fake_register_actor(actor_name):
        return FakeActor()

    drm_mod.DramatiqDispatcher._actor = None
    with patch.object(drm_mod, "_dramatiq", fake_dramatiq), patch.object(
        drm_mod, "register_actor", side_effect=fake_register_actor
    ):
        drm_mod.DramatiqDispatcher(queue="invalidation").dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )
    drm_mod.DramatiqDispatcher._actor = None

    assert sent == [
        (([42], {"42": {"user_id": 1}}), "invalidation"),
    ]


@pytest.mark.django_db(transaction=True)
def test_dramatiq_dispatcher_round_trip_through_stub_broker_rewarms_cache():
    pytest.importorskip("dramatiq")

    import dramatiq
    from django.core.cache import cache
    from dramatiq.brokers.stub import StubBroker
    from dramatiq.worker import Worker

    from restflow.caching import (
        ArgsKeyField,
        ConstantKeyField,
        InvalidationRule,
        cache_result,
    )
    from restflow.caching.dispatchers import dramatiq as drm_mod
    from tests.models import SampleModel

    actor_name = f"test.dramatiq.actor.roundtrip.{id(object())}"
    cache.clear()
    drm_mod.DramatiqDispatcher._actor = None

    broker = StubBroker()
    broker.emit_after("process_boot")
    dramatiq.set_broker(broker)
    worker = Worker(broker, worker_threads=1)
    worker.start()

    instance = SampleModel.objects.create(string_field="initial", integer_field=1)
    calls = {"n": 0}

    try:
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
                    dispatcher="dramatiq",
                    dispatcher_config={
                        "queue": "default",
                        "actor_name": actor_name,
                    },
                )
            ],
        )
        def get_value(sample_id: int):
            calls["n"] += 1
            return f"v{calls['n']}"

        CacheRegister.auto_discover()

        assert get_value(instance.id) == "v1"
        assert calls["n"] == 1

        instance.string_field = "updated"
        instance.save()

        broker.join("default", timeout=5_000)
        worker.join()

        assert get_value(instance.id) == "v2"
        assert calls["n"] == 2
    finally:
        worker.stop()
        broker.close()
        drm_mod.DramatiqDispatcher._actor = None
