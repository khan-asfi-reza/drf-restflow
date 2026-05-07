import pytest
from django.contrib.auth import get_user_model

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    Dispatcher,
    InvalidationRule,
    cache_result,
    register_dispatcher,
    registered_dispatcher_names,
)
from restflow.caching.dispatchers import resolve


def test_builtin_dispatchers_are_pre_registered():
    names = registered_dispatcher_names()
    assert "inline" in names
    assert "celery" in names


def test_resolve_by_name_returns_instance_of_class():
    from restflow.caching import InlineDispatcher

    inst = resolve("inline")
    assert isinstance(inst, InlineDispatcher)


def test_resolve_by_class_passes_config_to_init():
    class CustomDispatcher(Dispatcher):
        name = "test_resolve_by_class"

        def dispatch(self, **kwargs):  # pragma: no cover
            pass

    inst = resolve(CustomDispatcher, {"foo": 1, "bar": "x"})
    assert isinstance(inst, CustomDispatcher)
    assert inst.config == {"foo": 1, "bar": "x"}


def test_default_batch_key_groups_by_class_and_sorted_config():

    class _Plain(Dispatcher):
        name = "test_plain_batch_key"

        def dispatch(self, **kwargs):  # pragma: no cover
            pass

    a = _Plain(b=2, a=1)
    b = _Plain(a=1, b=2)
    c = _Plain(a=1, b=3)
    assert a.batch_key() == b.batch_key()
    assert a.batch_key() != c.batch_key()


def test_import_dotted_rejects_path_without_module_component():
    from restflow.caching.dispatchers.base import import_dotted

    with pytest.raises(ImportError, match="Invalid dotted path"):
        import_dotted("nodot")


def test_resolve_unknown_name_raises_keyerror_listing_available():
    with pytest.raises(KeyError) as exc:
        resolve("nope_not_real")
    assert "nope_not_real" in str(exc.value)
    assert "inline" in str(exc.value)


def test_resolve_rejects_non_dispatcher_argument():
    with pytest.raises(TypeError):
        resolve(123)


def test_register_decorator_adds_to_registry():
    @register_dispatcher
    class _RegMe(Dispatcher):
        name = "test_reg_me"

        def dispatch(self, **kwargs):  # pragma: no cover
            pass

    assert "test_reg_me" in registered_dispatcher_names()
    assert isinstance(resolve("test_reg_me"), _RegMe)


def test_register_rejects_non_dispatcher_class():
    with pytest.raises(TypeError):
        register_dispatcher(object)  # type: ignore[arg-type]


def test_register_rejects_dispatcher_with_no_name():
    class NoName(Dispatcher):
        def dispatch(self, **kwargs):  # pragma: no cover
            pass

    with pytest.raises(ValueError):
        register_dispatcher(NoName)


def test_optional_dispatchers_are_registered():
    names = registered_dispatcher_names()
    assert "django_rq" in names
    assert "dramatiq" in names
    assert "django_q" in names
    assert "asyncio" in names


def test_dispatcher_settings_blocks_are_seeded_for_each_builtin():
    from restflow.caching.dispatchers import (
        AsyncIODispatcher,
        CeleryDispatcher,
        DjangoQDispatcher,
        DjangoRqDispatcher,
        DramatiqDispatcher,
        InlineDispatcher,
        ThreadPoolDispatcher,
    )

    assert "RAISE_EXCEPTION" in InlineDispatcher.settings()
    assert "RAISE_EXCEPTION" in AsyncIODispatcher.settings()

    assert "TASK_NAME" in CeleryDispatcher.settings()
    assert "MAX_WORKERS" in ThreadPoolDispatcher.settings()
    assert "QUEUE" in DjangoRqDispatcher.settings()
    assert "FUNCTION_PATH" in DjangoRqDispatcher.settings()
    assert "QUEUE" in DramatiqDispatcher.settings()
    assert "ACTOR_NAME" in DramatiqDispatcher.settings()
    assert "CLUSTER" in DjangoQDispatcher.settings()
    assert "FUNCTION_PATH" in DjangoQDispatcher.settings()


def test_rule_get_dispatcher_caches_instance():
    User = type("M", (), {})
    rule = InvalidationRule(model=User)
    a = rule.get_dispatcher()
    b = rule.get_dispatcher()
    assert a is b


def test_rule_with_dispatcher_class_directly():
    captured = {}

    class Custom(Dispatcher):
        name = "test_rule_with_class"

        def dispatch(self, **kwargs):
            captured.update(kwargs)

    User = type("M", (), {})
    rule = InvalidationRule(
        model=User,
        dispatcher=Custom,
        dispatcher_config={"setting": "value"},
    )
    inst = rule.get_dispatcher()
    assert isinstance(inst, Custom)
    assert inst.config == {"setting": "value"}


def test_rule_default_batch_is_false():
    User = type("M", (), {})
    rule = InvalidationRule(
        model=User,
        dispatcher="celery",
        dispatcher_config={"task_name": "t", "queue": "q"},
    )
    assert rule.batch is False


def test_registry_dispatches_to_custom_dispatcher_class():
    User = get_user_model()

    captured: list[dict] = []

    class CapturingDispatcher(Dispatcher):
        name = "test_capturing"
        supports_batching = True

        def dispatch(self, **kwargs):
            captured.append(kwargs)

    @cache_result(
        {"fields": {"u": ArgsKeyField("user_id", partition=True)}},
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"user_id": "id"},
                dispatcher=CapturingDispatcher,
            )
        ],
    )
    def f(user_id: int):  # pragma: no cover
        return user_id

    CacheRegister.auto_discover()
    rule_ids = CacheRegister._model_rule_ids.get(User, [])

    class _MockInstance:
        def __init__(self):
            self.id = 7
            self.pk = 7
            self._meta = User._meta

    CacheRegister._invalidate_via_dispatchers(
        instance=_MockInstance(),
        rule_ids=rule_ids,
        instance_created=False,
        signal_type=CacheRegister.SignalTypes.POST_SAVE,
    )

    assert any(c.get("pk") == 7 for c in captured)
