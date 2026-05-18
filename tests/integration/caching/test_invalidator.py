from unittest.mock import Mock, patch

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


def _make_user(**kwargs):
    kwargs.setdefault("email", f"{kwargs.get('username', 'user')}@example.com")
    return get_user_model().objects.create(**kwargs)


@pytest.fixture(autouse=True)
def _clear_cache_and_registry():
    cache.clear()
    CacheRegister.clear()
    yield
    cache.clear()
    CacheRegister.clear()


# Module-level invalidator used by the dotted-path resolution test.
_string_path_calls: list[tuple] = []


def string_path_invalidator(wrapper, instance, **_):
    _string_path_calls.append((wrapper, instance))


class TestInvalidationRuleConstruction:

    def test_rejects_invalidator_combined_with_field_mapping(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            InvalidationRule(
                model=get_user_model(),
                field_mapping={"user_id": "id"},
                invalidator=lambda wrapper, instance, **_: None,
            )

    def test_rejects_non_callable_non_string_invalidator(self):
        with pytest.raises(TypeError, match="callable or a dotted-path string"):
            InvalidationRule(
                model=get_user_model(),
                invalidator=42,  # type: ignore[arg-type]
            )

    def test_accepts_callable_invalidator(self):
        rule = InvalidationRule(
            model=get_user_model(),
            invalidator=lambda wrapper, instance, **_: None,
        )
        assert callable(rule.invalidator)

    def test_accepts_dotted_path_string_invalidator(self):
        rule = InvalidationRule(
            model=get_user_model(),
            invalidator="tests.integration.caching.test_invalidator.string_path_invalidator",
        )
        assert isinstance(rule.invalidator, str)


class TestResolveInvalidator:

    def test_returns_callable_unchanged(self):
        def fn(wrapper, instance, **_):
            pass

        rule = InvalidationRule(model=get_user_model(), invalidator=fn)
        assert rule.resolve_invalidator() is fn

    def test_imports_dotted_path_lazily(self):
        rule = InvalidationRule(
            model=get_user_model(),
            invalidator="tests.integration.caching.test_invalidator.string_path_invalidator",
        )
        resolved = rule.resolve_invalidator()
        assert resolved is string_path_invalidator
        # Cached - second call returns the same object without re-importing.
        assert rule.resolve_invalidator() is resolved

    def test_raises_on_string_without_dot(self):
        rule = InvalidationRule(model=get_user_model(), invalidator="foo")
        with pytest.raises(ValueError, match="dotted import path"):
            rule.resolve_invalidator()


@pytest.mark.django_db(transaction=True)
class TestInvalidatorDispatch:

    def test_invalidator_receives_wrapper_and_instance(self):
        User = get_user_model()
        captured: dict = {}

        def my_invalidator(wrapper, instance, **_):
            captured["wrapper"] = wrapper
            captured["instance_id"] = instance.id

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, invalidator=my_invalidator)
            ],
        )
        def get_user_value(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv1")
        user.username = "iv1x"
        user.save()

        assert captured["wrapper"] is get_user_value
        assert captured["instance_id"] == user.id

    def test_invalidator_with_named_kwargs_receives_them(self):
        User = get_user_model()
        captured: dict = {}

        def my_invalidator(
            wrapper, instance, *, signal_type, instance_created, update_fields
        ):
            captured["signal_type"] = signal_type
            captured["instance_created"] = instance_created
            captured["update_fields"] = update_fields

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, invalidator=my_invalidator)
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv2")
        user.email = "new@example.com"
        user.save(update_fields=["email"])

        assert captured["signal_type"] == CacheRegister.SignalTypes.POST_SAVE
        assert captured["instance_created"] is False
        assert captured["update_fields"] == frozenset(["email"])

    def test_invalidator_with_var_kwargs_receives_all_extras(self):
        User = get_user_model()
        captured: list[dict] = []

        def my_invalidator(wrapper, instance, **kwargs):
            captured.append(kwargs)

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, invalidator=my_invalidator)
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv3")
        user.username = "iv3x"
        user.save()

        assert captured
        assert "signal_type" in captured[0]
        assert "instance_created" in captured[0]
        assert "update_fields" in captured[0]

    def test_invalidator_with_minimal_signature_skips_extras(self):
        User = get_user_model()
        called = []

        def my_invalidator(wrapper, instance):
            called.append(instance.id)

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, invalidator=my_invalidator)
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv4")
        user.username = "iv4x"
        user.save()

        assert called == [user.id]

    def test_invalidator_short_circuitsprocess_rule_and_celery(self):
        User = get_user_model()

        def my_invalidator(wrapper, instance, **_):
            return None

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    invalidator=my_invalidator,
                    dispatcher="celery",
                    dispatcher_config={"task_name": "should.not.dispatch"},
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        from restflow.caching import CeleryDispatcher
        with (
            patch.object(CacheRegister, "process_rule") as mock_apply,
            patch.object(CeleryDispatcher, "dispatch") as mock_celery,
        ):
            user = _make_user(username="iv5")
            user.username = "iv5x"
            user.save()

            mock_apply.assert_not_called()
            mock_celery.assert_not_called()

    def test_invalidator_respects_trigger_on_create_gate(self):
        User = get_user_model()
        called = []

        def my_invalidator(wrapper, instance, **_):
            called.append(instance.id)

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    invalidator=my_invalidator,
                    trigger_on_create=False,
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv6")
        assert called == []
        user.username = "iv6x"
        user.save()
        assert called == [user.id]

    def test_invalidator_exception_is_logged_not_re_raised(self):
        User = get_user_model()

        def my_invalidator(wrapper, instance, **_):
            raise RuntimeError("boom")

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, invalidator=my_invalidator)
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv7")
        # save() must succeed even though the invalidator raises.
        user.username = "iv7x"
        user.save()

    def test_invalidator_via_dotted_path_string(self):
        User = get_user_model()
        _string_path_calls.clear()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    invalidator=(
                        "tests.integration.caching.test_invalidator.string_path_invalidator"
                    ),
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="iv8")
        user.username = "iv8x"
        user.save()

        assert len(_string_path_calls) == 1
        wrapper, instance = _string_path_calls[0]
        assert wrapper is f
        assert instance.id == user.id

    def test_invalidator_can_call_multiple_wrapper_methods(self):
        User = get_user_model()
        invocations: list[str] = []

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
        )
        def f(user_id: int):
            return user_id

        def my_invalidator(wrapper, instance, **_):
            with (
                patch.object(wrapper, "delete_cache") as dc,
                patch.object(wrapper, "delete_by_prefix") as dp,
            ):
                wrapper.delete_cache(user_id=instance.id)
                wrapper.delete_by_prefix(user_id=instance.id + 1000)
                invocations.append("delete_cache" if dc.called else "")
                invocations.append("delete_by_prefix" if dp.called else "")

        CacheRegister.register(
            model=User,
            func=f,
            invalidation_rule=InvalidationRule(
                model=User, invalidator=my_invalidator
            ),
        )
        CacheRegister.auto_discover()

        user = _make_user(username="iv9")
        user.username = "iv9x"
        user.save()

        assert "delete_cache" in invocations
        assert "delete_by_prefix" in invocations


def test_invalidator_skips_signature_introspection_for_uninspectable_callable():
    User = get_user_model()
    fake_wrapper = Mock(__name__="fake_wrapper")

    received = []

    def opaque(wrapper, instance):
        received.append((wrapper, instance))

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(model=User, invalidator=opaque),
    }
    CacheRegister._run_invalidator(
        rule=rule,
        instance="instance-sentinel",
        signal_type=CacheRegister.SignalTypes.POST_SAVE,
        instance_created=False,
        update_fields=None,
    )
    assert received == [(fake_wrapper, "instance-sentinel")]


def test_invalidator_falls_back_to_empty_extras_when_signature_raises():
    from unittest.mock import patch

    User = get_user_model()
    fake_wrapper = Mock(__name__="fake_wrapper")
    invoked: list[tuple] = []

    def my_invalidator(wrapper, instance):
        invoked.append((wrapper, instance))

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(
            model=User, invalidator=my_invalidator
        ),
    }
    with patch(
        "restflow.caching.registry.inspect.signature",
        side_effect=ValueError("no signature"),
    ):
        CacheRegister._run_invalidator(
            rule=rule,
            instance="x",
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            instance_created=False,
            update_fields=None,
        )
    assert invoked == [(fake_wrapper, "x")]


def test_invalidator_logs_and_swallows_exceptions_raised_inside():
    User = get_user_model()
    fake_wrapper = Mock(__name__="fake_wrapper")

    def boom(wrapper, instance):
        raise RuntimeError("boom inside invalidator")

    rule = {
        "id": 1,
        "func": fake_wrapper,
        "invalidation_rule": InvalidationRule(model=User, invalidator=boom),
    }
    # The call must not raise.
    CacheRegister._run_invalidator(
        rule=rule,
        instance="x",
        signal_type=CacheRegister.SignalTypes.POST_SAVE,
        instance_created=False,
        update_fields=None,
    )


@pytest.mark.django_db(transaction=True)
def test_invalidator_calling_delete_cache_evicts_cached_entry_on_save():
    User = get_user_model()
    calls = {"n": 0}

    def my_invalidator(wrapper, instance, **_):
        wrapper.delete_cache(user_id=instance.id)

    @cache_result(
        {
            "fields": {
                "user": ArgsKeyField("user_id", partition=True),
                "v": ConstantKeyField("v", "1"),
            }
        },
        ttl=60,
        invalidates_on=[
            InvalidationRule(model=User, invalidator=my_invalidator)
        ],
    )
    def get_user_label(user_id: int):
        calls["n"] += 1
        return f"label-{calls['n']}"

    CacheRegister.auto_discover()
    user = _make_user(username="iv-real")
    assert get_user_label(user.id) == "label-1"
    assert get_user_label(user.id) == "label-1"
    assert calls["n"] == 1

    user.username = "iv-real-x"
    user.save()

    assert get_user_label(user.id) == "label-2"
    assert calls["n"] == 2


@pytest.mark.django_db(transaction=True)
def test_invalidator_replaces_default_dispatcher_path_so_registry_does_not_rewarm():
    User = get_user_model()
    invocations: list[str] = []

    def my_invalidator(wrapper, instance, **_):
        invocations.append("invalidator")

    @cache_result(
        {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(model=User, invalidator=my_invalidator)
        ],
    )
    def f(user_id: int):
        invocations.append(f"compute-{user_id}")
        return user_id

    CacheRegister.auto_discover()

    user = _make_user(username="iv-replace")
    f(user.id)
    invocations.clear()

    user.username = "iv-replace-x"
    user.save()

    assert invocations == ["invalidator"]
