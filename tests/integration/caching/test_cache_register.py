import os
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    ConstantKeyField,
    InvalidationRule,
    KeyConstructor,
    cache_result,
)
from tests.models import SampleModel

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
DJANGO_REDIS_CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}


def _make_user(**kwargs):
    kwargs.pop("name", None)
    kwargs.setdefault("email", f"{kwargs.get('username', 'user')}@example.com")
    return get_user_model().objects.create(**kwargs)


@pytest.fixture(autouse=True)
def _clear_cache_and_registry():
    cache.clear()
    CacheRegister.clear()
    yield
    cache.clear()
    CacheRegister.clear()


@pytest.mark.redis
@pytest.mark.django_db(transaction=True)
class TestCacheRegistrySignals:

    @pytest.fixture(autouse=True)
    def _use_django_redis(self):
        with override_settings(CACHES=DJANGO_REDIS_CACHES):
            yield

    def test_post_save_invalidates_cached_value_and_post_delete_re_caches(self):
        User = get_user_model()
        user = _make_user(username="u1")
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
                    model=User, field_mapping={"user_id": "id"}, rewarm=False
                )
            ],
        )
        def get_user_value(user_id: int):
            calls["n"] += 1
            return f"val-{calls['n']}"

        assert get_user_value(user.id) == "val-1"
        assert get_user_value(user.id) == "val-1"
        assert calls["n"] == 1

        CacheRegister.auto_discover()

        user.username = "u1x"
        user.save()
        assert get_user_value(user.id) == "val-2"
        assert calls["n"] == 2

        uid = user.id
        user.delete()
        assert get_user_value(uid) == "val-3"

    def test_invalidation_works_against_a_non_user_model(self):
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
                    rewarm=False,
                )
            ],
        )
        def get_sample_value(sample_id: int):
            calls["n"] += 1
            return f"sample-{sample_id}-val-{calls['n']}"

        first = get_sample_value(instance.id)
        assert first == f"sample-{instance.id}-val-1"
        assert get_sample_value(instance.id) == first
        assert calls["n"] == 1

        CacheRegister.auto_discover()

        instance.string_field = "updated"
        instance.save()
        assert get_sample_value(instance.id) != first
        assert calls["n"] == 2

        bid = instance.id
        instance.delete()
        assert get_sample_value(bid).startswith(f"sample-{bid}-val-")

    def test_add_raises_when_passed_non_decorated_function(self):
        with pytest.raises(AttributeError, match="decorated function"):
            CacheRegister.add(
                model=get_user_model(),
                func=lambda x: x,
                invalidation_rule=InvalidationRule(
                    model=get_user_model(), field_mapping={"x": "id"}
                ),
            )

    def test_get_status_flips_discovered_flag_after_auto_discover(self):
        status = CacheRegister.get_status()
        assert status["discovered"] is False
        assert status["pending"] == 0
        assert isinstance(status["models"], dict)

        CacheRegister.auto_discover()
        status2 = CacheRegister.get_status()
        assert status2["discovered"] is True


@pytest.mark.django_db(transaction=True)
class TestCacheRegistryRegistration:

    def test_add_after_auto_discover_registers_immediately(self):
        User = get_user_model()

        @cache_result(
            {
                "fields": {
                    "v": ConstantKeyField("v", "1"),
                    "user": ArgsKeyField("user_id", partition=True),
                }
            },
            ttl=60,
        )
        def fn(user_id: int):
            return user_id

        CacheRegister.auto_discover()

        CacheRegister.add(
            model=User,
            func=fn,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "id"}
            ),
        )
        CacheRegister.add(
            model=User,
            func=fn,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "id"}
            ),
        )

    def test_register_supports_multiple_rules_for_one_model(self):
        User = get_user_model()

        @cache_result({"fields": {"arg": ArgsKeyField("user_id")}}, ttl=30)
        def f(user_id: int):
            return user_id

        @cache_result({"fields": {"arg": ArgsKeyField("user_id")}}, ttl=30)
        def g(user_id: int):
            return user_id

        CacheRegister.register(
            model=User,
            func=f,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "id"}
            ),
        )
        CacheRegister.register(
            model=User,
            func=g,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "id"}, rewarm=True
            ),
        )

    def test_save_with_unresolvable_field_mapping_skips_invalidation(self):
        User = get_user_model()

        @cache_result(
            {
                "fields": {
                    "user": ArgsKeyField("user_id", partition=True),
                    "v": ConstantKeyField("v", "1"),
                }
            },
            ttl=30,
        )
        def f(user_id: int):
            return user_id

        CacheRegister.register(
            model=User,
            func=f,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "nope"}
            ),
        )
        CacheRegister.auto_discover()

        user = _make_user(username="abc")
        user.save()  # no exception, no invalidation

    def test_save_swallows_exceptions_raised_by_delete_by_prefix(self):
        User = get_user_model()

        @cache_result(
            {
                "fields": {
                    "user": ArgsKeyField("user_id", partition=True),
                }
            },
            ttl=30,
        )
        def g(user_id: int):
            return user_id

        def raiser(**kwargs):
            raise RuntimeError("boom")

        g.delete_by_prefix = raiser

        CacheRegister.register(
            model=User,
            func=g,
            invalidation_rule=InvalidationRule(
                model=User, field_mapping={"user_id": "id"}
            ),
        )
        CacheRegister.auto_discover()

        user = _make_user(username="abc")
        user.save()


@pytest.mark.django_db(transaction=True)
class TestTriggerOnCreate:

    def test_creation_skips_invalidation_when_trigger_on_create_is_false(self):
        User = get_user_model()

        @cache_result(
            {
                "fields": {
                    "user": ArgsKeyField("user_id", partition=True),
                    "v": ConstantKeyField("v", "1"),
                }
            },
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def get_user_value(user_id: int):
            return f"val-{user_id}"

        CacheRegister.auto_discover()

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            _make_user(username="trigger_test")
            mock_apply.assert_not_called()

    def test_creation_triggers_invalidation_when_trigger_on_create_is_true(self):
        User = get_user_model()

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
                    model=User, field_mapping={"user_id": "id"}, trigger_on_create=True
                )
            ],
        )
        def get_user_value(user_id: int):
            return f"val-{user_id}"

        CacheRegister.auto_discover()

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            _make_user(username="trigger_create")
            mock_apply.assert_called_once()

    def test_create_then_save_with_trigger_on_create_false_only_rewarms_on_save(self):
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
                    trigger_on_create=False,
                )
            ],
        )
        def get_user_label(user_id: int):
            calls["n"] += 1
            return f"label-{calls['n']}"

        CacheRegister.auto_discover()
        user = _make_user(username="trigger-real")
        assert get_user_label(user.id) == "label-1"
        assert calls["n"] == 1

        assert get_user_label(user.id) == "label-1"
        assert calls["n"] == 1

        user.username = "trigger-real-x"
        user.save()
        assert get_user_label(user.id) == "label-2"
        assert calls["n"] == 2


class TestCacheRegistrySingleton:

    def test_construction_returns_same_instance_every_call(self):
        from restflow.caching.registry import CacheRegistry

        registry = CacheRegistry()
        _ = registry.is_discovered
        registry_again = CacheRegistry()
        assert registry is registry_again

    def test_auto_discover_is_idempotent(self):
        CacheRegister.auto_discover()
        assert CacheRegister.is_discovered is True
        CacheRegister.auto_discover()
        assert CacheRegister.is_discovered is True

    def test_get_field_value_returns_none_for_missing_attribute_path(self):
        from restflow.caching.registry import CacheRegistry

        class Obj:
            a = None

        assert CacheRegistry._get_field_value(Obj(), "a.b") is None

    def test_pending_count_and_model_count_match_status(self):
        class MyKC(KeyConstructor):
            const = ConstantKeyField("v", "1")

        @cache_result(MyKC, ttl=5)
        def f(a):
            return a

        status = CacheRegister.get_status()
        assert CacheRegister.pending_count == status["pending"]
        assert CacheRegister.model_count >= 0


class TestResolveRuleKwargs:

    def test_returns_none_when_required_arg_resolves_to_none(self):
        User = get_user_model()
        invalidation_rule = InvalidationRule(
            model=User,
            field_mapping={"user_id": "id"},
            require_args=["user_id"],
        )
        with patch.object(
            CacheRegister, "_extract_kwargs", return_value={"user_id": None}
        ):
            result = CacheRegister._resolve_rule_kwargs(Mock(), invalidation_rule)
            assert result is None

    def test_passes_none_through_when_require_args_is_false(self):
        User = get_user_model()
        invalidation_rule = InvalidationRule(
            model=User,
            field_mapping={"team_id": "team.id"},
            require_args=False,
        )
        with patch.object(
            CacheRegister, "_extract_kwargs", return_value={"team_id": None}
        ):
            result = CacheRegister._resolve_rule_kwargs(Mock(), invalidation_rule)
            assert result == {"team_id": None}

    def test_partial_require_args_lets_others_be_none(self):
        User = get_user_model()
        invalidation_rule = InvalidationRule(
            model=User,
            field_mapping={"user_id": "id", "team_id": "team.id"},
            require_args=["user_id"],
        )
        with patch.object(
            CacheRegister,
            "_extract_kwargs",
            return_value={"user_id": 7, "team_id": None},
        ):
            result = CacheRegister._resolve_rule_kwargs(Mock(), invalidation_rule)
            assert result == {"user_id": 7, "team_id": None}

    def test_returns_empty_dict_when_field_mapping_is_empty(self):
        invalidation_rule = InvalidationRule(model=get_user_model())
        result = CacheRegister._resolve_rule_kwargs(Mock(), invalidation_rule)
        assert result == {}

    def test_returns_none_when_instance_is_none_and_mapping_is_set(self):
        invalidation_rule = InvalidationRule(
            model=get_user_model(),
            field_mapping={"user_id": "id"},
        )
        result = CacheRegister._resolve_rule_kwargs(None, invalidation_rule)
        assert result is None

    def test_returns_none_when_field_path_does_not_resolve(self):
        invalidation_rule = InvalidationRule(
            model=get_user_model(),
            field_mapping={"user_id": "nope"},
        )
        mock_instance = Mock(spec=[])
        result = CacheRegister._resolve_rule_kwargs(mock_instance, invalidation_rule)
        assert result is None


class TestApplyRule:

    def test_falls_back_to_delete_by_prefix_when_rewarm_raises(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
        )
        def f(user_id: int):
            return user_id

        rule = {
            "id": 999,
            "func": f,
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                rewarm=True,
            ),
        }

        with patch.object(f, "refresh", side_effect=RuntimeError("boom")):
            with patch.object(f, "delete_by_prefix") as mock_delete:
                CacheRegister.process_rule(rule=rule, func_kwargs={"user_id": 1})
                mock_delete.assert_called_once_with(user_id=1)

    @pytest.mark.django_db(transaction=True)
    def test_post_save_clears_partition_only_cache_on_locmem_backend(self):
        instance = SampleModel.objects.create(string_field="initial", integer_field=1)
        calls = {"n": 0}

        @cache_result(
            {"fields": {"sample": ArgsKeyField("sample_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=SampleModel,
                    field_mapping={"sample_id": "id"},
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

    def test_does_not_delete_when_rewarm_succeeds(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
        )
        def f(user_id: int):
            return user_id

        rule = {
            "id": 999,
            "func": f,
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                rewarm=True,
            ),
        }

        with patch.object(f, "refresh", return_value="refreshed") as mock_refresh:
            with patch.object(f, "delete_by_prefix") as mock_delete:
                CacheRegister.process_rule(rule=rule, func_kwargs={"user_id": 1})
                mock_refresh.assert_called_once_with(user_id=1)
                mock_delete.assert_not_called()

    def test_decorator_rejects_invalidation_rule_without_field_mapping_or_invalidator(self):
        User = get_user_model()

        with pytest.raises(
            ValueError, match="must declare either"
        ):

            @cache_result(
                {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
                ttl=60,
                invalidates_on=[InvalidationRule(model=User)],
            )
            def f(user_id: int):
                return user_id

    def test_cached_wrapper_exposes_key_constructor_property(self):
        @cache_result(
            {"fields": {"v": ConstantKeyField("v", "1")}},
            ttl=60,
        )
        def f(x: int):
            return x

        assert f.key_constructor is not None

    def test_cached_wrapper_class_attribute_returns_self_unwrapped(self):
        class MyClass:
            @cache_result({"fields": {"c": ConstantKeyField("v", "1")}}, ttl=60)
            def method(self, x):
                return x

        raw_wrapper = MyClass.__dict__["method"]
        from_class = MyClass.method
        assert from_class is raw_wrapper


@pytest.mark.celery
class TestDispatchCeleryTask:

    def test_send_task_called_without_queue_when_unset(self):
        from restflow.caching import CeleryDispatcher
        with patch("restflow.caching.dispatchers.celery._celery_current_app") as mock_app:
            CeleryDispatcher(task_name="test.task").dispatch(
                model_label="auth.User",
                pk=1,
                rule_ids=[1, 2],
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
                rule_kwargs={"1": {"user_id": 1}},
            )
            mock_app.send_task.assert_called_once_with(
                "test.task",
                kwargs={
                    "model_label": "auth.User",
                    "pk": 1,
                    "rule_ids": [1, 2],
                    "signal_type": "POST_SAVE",
                    "rule_kwargs": {"1": {"user_id": 1}},
                },
            )

    def test_send_task_called_with_queue_when_set(self):
        from restflow.caching import CeleryDispatcher
        with patch("restflow.caching.dispatchers.celery._celery_current_app") as mock_app:
            CeleryDispatcher(
                task_name="test.task", queue="my.queue"
            ).dispatch(
                model_label="auth.User",
                pk=1,
                rule_ids=[1],
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
                rule_kwargs={"1": {"user_id": 1}},
            )
            mock_app.send_task.assert_called_once_with(
                "test.task",
                kwargs={
                    "model_label": "auth.User",
                    "pk": 1,
                    "rule_ids": [1],
                    "signal_type": "POST_SAVE",
                    "rule_kwargs": {"1": {"user_id": 1}},
                },
                queue="my.queue",
            )

    def test_batch_false_dispatches_one_task_per_rule(self):
        from restflow.caching import CeleryDispatcher
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    dispatcher="celery",
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        rule_ids = CacheRegister._model_rule_ids.get(User, [])

        mock_instance = Mock()
        mock_instance.pk = 1
        mock_instance.id = 1
        mock_instance._meta = User._meta

        with patch.object(CeleryDispatcher, "dispatch") as mock_dispatch:
            CacheRegister._invalidate_via_dispatchers(
                mock_instance,
                rule_ids,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            mock_dispatch.assert_called_once()
            call_kwargs = mock_dispatch.call_args.kwargs
            assert call_kwargs["rule_ids"] == [rule_ids[0]]
            assert call_kwargs["rule_kwargs"] == {str(rule_ids[0]): {"user_id": 1}}

    def test_dispatcher_config_queue_threads_through_to_celery(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    dispatcher="celery",
                    dispatcher_config={"queue": "my.queue"},
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        rule_ids = CacheRegister._model_rule_ids.get(User, [])

        mock_instance = Mock()
        mock_instance.pk = 1
        mock_instance.id = 1
        mock_instance._meta = User._meta

        with patch("restflow.caching.dispatchers.celery._celery_current_app") as mock_app:
            CacheRegister._invalidate_via_dispatchers(
                mock_instance,
                rule_ids,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            mock_app.send_task.assert_called_once()
            assert mock_app.send_task.call_args.kwargs["queue"] == "my.queue"

    def test_batch_true_merges_rules_sharing_a_batch_key(self):
        from restflow.caching import CeleryDispatcher
        User = get_user_model()

        @cache_result(
            {
                "fields": {
                    "user": ArgsKeyField("user_id", partition=True),
                    "c": ConstantKeyField("c", "1"),
                }
            },
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    dispatcher="celery",
                    batch=True,
                )
            ],
        )
        def f(user_id: int):
            return user_id

        @cache_result(
            {
                "fields": {
                    "user": ArgsKeyField("user_id", partition=True),
                    "c": ConstantKeyField("c", "2"),
                }
            },
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    dispatcher="celery",
                    batch=True,
                )
            ],
        )
        def g(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        # The singleton registry accumulates rules across tests in this
        # module, so filter to just our two.
        rule_ids = [
            rid
            for rid in CacheRegister._model_rule_ids.get(User, [])
            if CacheRegister.get_rule(rid)["func"].__name__ in ("f", "g")
        ]
        assert len(rule_ids) == 2

        mock_instance = Mock()
        mock_instance.pk = 1
        mock_instance.id = 1
        mock_instance._meta = User._meta

        with patch.object(CeleryDispatcher, "dispatch") as mock_dispatch:
            CacheRegister._invalidate_via_dispatchers(
                mock_instance,
                rule_ids,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            mock_dispatch.assert_called_once()
            call_kwargs = mock_dispatch.call_args.kwargs
            assert len(call_kwargs["rule_ids"]) == 2
            assert len(call_kwargs["rule_kwargs"]) == 2

    def test_unknown_rule_id_is_silently_skipped(self):
        mock_instance = Mock()
        mock_instance.pk = 1
        CacheRegister._invalidate_via_dispatchers(
            mock_instance,
            [99999],
            instance_created=False,
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
        )

    @pytest.mark.django_db(transaction=True)
    def test_post_save_dispatches_celery_when_dispatcher_is_celery(self):
        User = get_user_model()
        with patch("restflow.caching.dispatchers.celery._celery_current_app") as current_celery_app:

            @cache_result(
                invalidates_on=[
                    InvalidationRule(
                        model=User,
                        field_mapping={"user_id": "id"},
                        dispatcher="celery",
                        rewarm=True,
                    )
                ]
            )
            def get_user(user_id):
                return User.objects.get(id=user_id)

            CacheRegister.auto_discover()
            user = _make_user(username="celery_test")
            current_celery_app.send_task.assert_not_called()
            user.email = "name2@mail.com"
            user.save()
            current_celery_app.send_task.assert_called_once()

    @pytest.mark.celery
    @pytest.mark.django_db(transaction=True)
    def test_celery_dispatcher_with_rewarm_recomputes_after_save(self):
        User = get_user_model()

        @cache_result(
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    dispatcher="celery",
                    rewarm=True,
                )
            ]
        )
        def get_user(user_id):
            return User.objects.get(id=user_id)

        CacheRegister.auto_discover()
        user = _make_user(username="celery_test", email="name1@mail.com")
        cached_user = get_user(user_id=user.id)
        user.email = "name2@mail.com"
        user.save()
        cached_user_2 = get_user(user_id=user.id)
        assert cached_user.email != cached_user_2.email


class TestInvalidateAll:

    def test_invokes_delete_pattern_with_function_level_prefix(self):
        @cache_result(
            {"fields": {"v": ConstantKeyField("v", "1")}},
            ttl=60,
        )
        def f(x: int):
            return x

        with patch.object(cache, "delete_pattern", create=True) as dp:
            f.invalidate_all()
            dp.assert_called_once()
            (pattern,) = dp.call_args.args
            assert pattern.endswith("*")

    def test_raises_not_implemented_on_unsupported_backend(self):
        @cache_result(
            {"fields": {"v": ConstantKeyField("v", "1")}},
            ttl=60,
        )
        def f(x: int):
            return x

        with pytest.raises(NotImplementedError, match="delete_pattern"):
            f.invalidate_all()


class TestShouldRunRule:

    def test_post_delete_signal_runs_regardless_of_trigger_on_create(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User, field_mapping={"user_id": "id"}, trigger_on_create=False
            ),
        }
        result = CacheRegister._should_run_rule(
            instance=Mock(),
            rule=rule,
            instance_created=True,
            signal_type=CacheRegister.SignalTypes.POST_DELETE,
        )
        assert result is True

    def test_runs_when_invalidate_when_value_matches(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                trigger_on_create=False,
                invalidate_when={"username": "user"},
            ),
        }
        instance = Mock()
        instance.username = "user"
        result = CacheRegister._should_run_rule(
            instance=instance,
            rule=rule,
            instance_created=True,
            signal_type=CacheRegister.SignalTypes.POST_DELETE,
        )
        assert result is True

    def test_runs_when_field_is_none_and_invalidate_when_expects_none(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                invalidate_when={"email": None},
            ),
        }
        instance = Mock()
        instance.email = None
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is True
        )

        instance.email = "has@email.com"
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is False
        )

    def test_runs_when_negated_field_does_not_match(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                invalidate_when={"!username": "admin"},
            ),
        }
        instance = Mock()
        instance.username = "regular_user"
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is True
        )

        instance.username = "admin"
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is False
        )

    def test_runs_when_field_is_not_none_under_negated_none_match(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                invalidate_when={"!email": None},
            ),
        }
        instance = Mock()
        instance.email = "has@email.com"
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is True
        )

        instance.email = None
        assert (
            CacheRegister._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=False,
                signal_type=CacheRegister.SignalTypes.POST_SAVE,
            )
            is False
        )

    def test_skips_when_invalidate_when_value_does_not_match(self):
        User = get_user_model()
        rule = {
            "id": 1,
            "func": Mock(is_cached_function=True),
            "invalidation_rule": InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                trigger_on_create=False,
                invalidate_when={"username": "user"},
            ),
        }
        instance = Mock()
        instance.username = "user1"
        result = CacheRegister._should_run_rule(
            instance=instance,
            rule=rule,
            instance_created=True,
            signal_type=CacheRegister.SignalTypes.POST_DELETE,
        )
        assert result is False


class TestRegistryStatus:

    def test_status_lists_each_model_with_its_function_and_rule_id(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        status = CacheRegister.get_status()

        assert status["discovered"] is True
        assert "User" in status["models"]
        assert len(status["models"]["User"]) >= 1
        rule_info = status["models"]["User"][0]
        assert "function" in rule_info
        assert "id" in rule_info


class TestApplyRules:

    def test_dispatches_process_rule_for_each_known_rule_id(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        rule_ids = CacheRegister._model_rule_ids.get(User, [])

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            CacheRegister.run_cache_rules(
                rule_ids=rule_ids,
                rule_kwargs={str(rule_ids[0]): {"user_id": 1}},
            )
            assert mock_apply.called

    def test_skips_rule_when_kwargs_for_id_are_missing(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(model=User, field_mapping={"user_id": "id"})
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        rule_ids = CacheRegister._model_rule_ids.get(User, [])

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            CacheRegister.run_cache_rules(rule_ids=rule_ids, rule_kwargs={})
            mock_apply.assert_not_called()

    def test_skips_rule_when_id_is_not_registered(self):
        with patch.object(CacheRegister, "process_rule") as mock_apply:
            CacheRegister.run_cache_rules(
                rule_ids=[99999],
                rule_kwargs={"99999": {"user_id": 1}},
            )
            mock_apply.assert_not_called()


@pytest.mark.django_db(transaction=True)
class TestWatchFields:

    def test_save_with_update_fields_disjoint_from_watch_fields_skips(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    watch_fields=["email"],
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="wf1")

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            user.username = "wf1_updated"
            user.save(update_fields=["username"])
            mock_apply.assert_not_called()

    def test_save_with_update_fields_overlapping_watch_fields_invalidates(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    watch_fields=["email"],
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="wf2")

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            user.email = "new@example.com"
            user.save(update_fields=["email"])
            mock_apply.assert_called_once()

    def test_save_without_update_fields_does_not_invalidate_a_watched_rule(self):
        User = get_user_model()

        @cache_result(
            {"fields": {"user": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=User,
                    field_mapping={"user_id": "id"},
                    watch_fields=["email"],
                )
            ],
        )
        def f(user_id: int):
            return user_id

        CacheRegister.auto_discover()
        user = _make_user(username="wf3", email="orig@x.com")

        with patch.object(CacheRegister, "process_rule") as mock_apply:
            user.email = "changed@x.com"
            user.save()
            mock_apply.assert_not_called()

    def test_has_watched_field_changed_returns_false_without_update_fields(self):
        assert CacheRegister._has_watched_field_changed(["email"]) is False

    def test_empty_or_none_watch_fields_means_always_invalidate(self):
        assert (
            CacheRegister._has_watched_field_changed(
                [], update_fields=frozenset(["email"])
            )
            is True
        )
        assert (
            CacheRegister._has_watched_field_changed(
                None, update_fields=frozenset(["email"])
            )
            is True
        )

    def test_watch_fields_gating_observed_through_cache_rewarm(self):
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
                    watch_fields=["email"],
                )
            ],
        )
        def get_user_label(user_id: int):
            calls["n"] += 1
            return f"label-{calls['n']}"

        CacheRegister.auto_discover()
        user = _make_user(username="wf-real")
        assert get_user_label(user.id) == "label-1"

        user.username = "wf-real-x"
        user.save(update_fields=["username"])
        assert get_user_label(user.id) == "label-1"
        assert calls["n"] == 1

        user.email = "new@example.com"
        user.save(update_fields=["email"])
        assert get_user_label(user.id) == "label-2"
        assert calls["n"] == 2

        user.email = "later@example.com"
        user.save()
        assert get_user_label(user.id) == "label-2"
        assert calls["n"] == 2


class TestImportCacheModules:

    def test_logs_warning_when_a_submodule_fails_to_import(self, caplog):
        import importlib
        import logging
        from unittest.mock import MagicMock

        from restflow.caching.registry import CacheRegistry

        fake_app = MagicMock()
        fake_app.name = "fake_pkg"
        fake_pkg = MagicMock()
        fake_pkg.__path__ = ["/nonexistent"]
        fake_pkg.__file__ = "/nonexistent/__init__.py"

        real_import = importlib.import_module

        def selective_import(name, *args, **kwargs):
            if name == "fake_pkg":
                return fake_pkg
            if name == "fake_pkg.broken":
                raise RuntimeError("boom")
            return real_import(name, *args, **kwargs)

        def fake_walk_packages(path, prefix):
            yield (None, f"{prefix}migrations.0001_initial", False)
            yield (None, f"{prefix}broken", False)

        with patch(
            "restflow.caching.registry.apps.get_app_configs",
            return_value=[fake_app],
        ), patch(
            "restflow.caching.registry.importlib.import_module",
            side_effect=selective_import,
        ), patch(
            "restflow.caching.registry.pkgutil.walk_packages",
            side_effect=fake_walk_packages,
        ), caplog.at_level(logging.WARNING):
            CacheRegistry._import_cache_modules()

        assert any(
            "failed to import" in record.message for record in caplog.records
        )

    def test_skips_apps_that_are_modules_not_packages(self):
        import types

        non_pkg_module = types.ModuleType("fake_single_module_app")
        mock_app_config = Mock()
        mock_app_config.name = "fake_single_module_app"

        with (
            patch("restflow.caching.registry.apps") as mock_apps,
            patch("restflow.caching.registry.importlib") as mock_importlib,
        ):
            mock_apps.get_app_configs.return_value = [mock_app_config]
            mock_importlib.import_module.return_value = non_pkg_module
            CacheRegister._import_cache_modules()
            mock_importlib.import_module.assert_called_once_with(
                "fake_single_module_app"
            )

    def test_optional_submodule_missing_dependency_is_silently_skipped(
        self, caplog
    ):
        import importlib
        import logging
        from unittest.mock import MagicMock

        from restflow.caching.registry import CacheRegistry

        fake_app = MagicMock()
        fake_app.name = "optional_dep_app"
        fake_pkg = MagicMock()
        fake_pkg.__path__ = ["/nonexistent"]
        fake_pkg.__file__ = "/nonexistent/__init__.py"

        real_import = importlib.import_module

        def selective_import(name, *args, **kwargs):
            if name == "optional_dep_app":
                return fake_pkg
            if name == "optional_dep_app.adapter":
                raise ImportError("missing optional dependency")
            return real_import(name, *args, **kwargs)

        def fake_walk_packages(path, prefix):
            yield (None, f"{prefix}adapter", False)

        with patch(
            "restflow.caching.registry.apps.get_app_configs",
            return_value=[fake_app],
        ), patch(
            "restflow.caching.registry.importlib.import_module",
            side_effect=selective_import,
        ), patch(
            "restflow.caching.registry.pkgutil.walk_packages",
            side_effect=fake_walk_packages,
        ), caplog.at_level(logging.WARNING):
            CacheRegistry._import_cache_modules()

        assert not any(
            "failed to import" in record.message for record in caplog.records
        )
