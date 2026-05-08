from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InlineDispatcher,
    InvalidationRule,
    cache_result,
)
from tests.models import SampleModel


def test_inline_dispatcher_runs_cache_rules_synchronously():
    with patch("restflow.caching.dispatchers.inline.run_cache_rules") as mock_apply:
        InlineDispatcher().dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[42],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"42": {"user_id": 1}},
        )
        mock_apply.assert_called_once_with(
            rule_ids=[42],
            rule_kwargs={"42": {"user_id": 1}},
            dispatcher_name="inline",
        )


@pytest.mark.django_db(transaction=True)
def test_inline_dispatcher_rewarms_cache_entry_after_save():
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
                dispatcher="inline",
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
def test_inline_dispatcher_does_not_rewarm_when_rule_filters_out_creation():
    cache.clear()
    User = get_user_model()
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
                dispatcher="inline",
                trigger_on_create=False,
            )
        ],
    )
    def get_user_label(user_id: int):
        calls["n"] += 1
        return f"label-{calls['n']}"

    CacheRegister.auto_discover()
    user = User.objects.create(username="u-inline", email="u@example.com")
    assert get_user_label(user.id) == "label-1"
    assert calls["n"] == 1


def test_inline_dispatcher_does_not_advertise_batching():
    assert InlineDispatcher.supports_batching is False


def test_rule_default_dispatcher_resolves_to_inline_via_settings():
    User = type("M", (), {})
    rule = InvalidationRule(model=User)
    assert rule.dispatcher is None
    assert isinstance(rule.get_dispatcher(), InlineDispatcher)


def test_registry_invalidation_uses_inline_dispatcher_by_default():
    User = get_user_model()

    @cache_result(
        {"fields": {"u": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(model=User, field_mapping={"user_id": "id"})
        ],
    )
    def f(user_id: int):  # pragma: no cover
        return user_id

    CacheRegister.auto_discover()

    class _MockInstance:
        def __init__(self):
            self.id = 1
            self.pk = 1
            self._meta = User._meta

    rule_ids = CacheRegister._model_rule_ids.get(User, [])

    with patch("restflow.caching.dispatchers.inline.run_cache_rules") as mock_apply:
        CacheRegister._invalidate_via_dispatchers(
            instance=_MockInstance(),
            rule_ids=rule_ids,
            instance_created=False,
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
        )
        assert mock_apply.call_count >= 1
