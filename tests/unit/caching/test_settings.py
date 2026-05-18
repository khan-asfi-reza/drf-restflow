from django.test import override_settings

from restflow.caching import InvalidationRule
from restflow.settings import DEFAULTS, RestflowSettings, restflow_settings


def test_defaults_are_returned_when_no_user_overrides():
    assert (
        DEFAULTS["CACHE_SETTINGS"]["DEFAULT_DISPATCHER"]
        == restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER
    )
    assert restflow_settings.CACHE_SETTINGS.MAX_KEY_SUFFIX_LENGTH == 250
    assert restflow_settings.CACHE_SETTINGS.HASH_SUFFIX_ON_OVERFLOW is False


def test_override_settings_replaces_only_named_keys():
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DEFAULT_DISPATCHER": "celery",
                "MAX_KEY_SUFFIX_LENGTH": 500,
            }
        }
    ):
        assert (
            restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER == "celery"
        )
        assert restflow_settings.CACHE_SETTINGS.MAX_KEY_SUFFIX_LENGTH == 500
        assert restflow_settings.CACHE_SETTINGS.HASH_SUFFIX_ON_OVERFLOW is False

    assert (
        restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER == "inline"
    )
    assert restflow_settings.CACHE_SETTINGS.MAX_KEY_SUFFIX_LENGTH == 250


def test_invalid_setting_name_raises_attribute_error():
    import pytest

    with pytest.raises(AttributeError, match="Invalid restflow setting"):
        _ = restflow_settings.NOT_A_REAL_SETTING

    with pytest.raises(AttributeError, match="Invalid restflow setting"):
        _ = restflow_settings.CACHE_SETTINGS.NOT_A_REAL_KEY


def test_celery_dispatcher_resolves_task_name_from_settings():
    from restflow.caching import CeleryDispatcher

    assert (
        CeleryDispatcher.settings()["TASK_NAME"]
        == "restflow.caching.tasks.task_run_cache_rules"
    )

    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {
                    "celery": {"TASK_NAME": "myproject.tasks.bust"}
                }
            }
        }
    ):
        assert (
            CeleryDispatcher.settings()["TASK_NAME"]
            == "myproject.tasks.bust"
        )


def test_celery_dispatcher_resolves_queue_from_settings():
    from restflow.caching import CeleryDispatcher

    # No queue configured -> None.
    assert CeleryDispatcher.settings().get("QUEUE") is None

    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {
                    "celery": {"QUEUE": "shared.queue"}
                }
            }
        }
    ):
        assert CeleryDispatcher.settings()["QUEUE"] == "shared.queue"


def test_per_rule_dispatcher_config_overrides_settings_default():
    from unittest.mock import patch

    from restflow.caching import CacheRegister, CeleryDispatcher

    User = type("M", (), {})
    rule = InvalidationRule(
        model=User,
        dispatcher="celery",
        dispatcher_config={"task_name": "per.rule.task", "queue": "per.rule.queue"},
    )
    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {
                    "celery": {
                        "TASK_NAME": "configured.task",
                        "QUEUE": "configured.queue",
                    }
                }
            }
        }
    ), patch("restflow.caching.dispatchers.celery._celery_current_app") as mock_app:
        rule.get_dispatcher().dispatch(
            model_label="auth.User",
            pk=1,
            rule_ids=[1],
            signal_type=CacheRegister.SignalTypes.POST_SAVE,
            rule_kwargs={"1": {"user_id": 1}},
        )
        assert isinstance(rule.get_dispatcher(), CeleryDispatcher)
        args, kwargs = mock_app.send_task.call_args
        assert args == ("per.rule.task",)
        assert kwargs["queue"] == "per.rule.queue"


def test_isolated_settings_instance_uses_its_own_defaults():
    custom = RestflowSettings(defaults={"CACHE_SETTINGS": {"FOO": "bar"}})
    assert custom.CACHE_SETTINGS.FOO == "bar"


def test_threadpool_dispatcher_resolves_max_workers_from_settings():
    from restflow.caching import ThreadPoolDispatcher

    assert ThreadPoolDispatcher.settings()["MAX_WORKERS"] == 4

    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {"threadpool": {"MAX_WORKERS": 16}}
            }
        }
    ):
        assert ThreadPoolDispatcher.settings()["MAX_WORKERS"] == 16


def test_user_dispatcher_settings_block_is_returned_as_dict():
    from restflow.caching import Dispatcher

    class _Custom(Dispatcher):
        name = "test_user_settings_block"

        def dispatch(self, **kwargs):  # pragma: no cover
            pass

    assert _Custom.settings() == {}

    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {
                "DISPATCHER_SETTINGS": {
                    "test_user_settings_block": {"FOO": "bar"}
                }
            }
        }
    ):
        assert _Custom.settings() == {"FOO": "bar"}


def test_root_user_settings_returns_empty_when_user_setting_is_non_dict():
    with override_settings(RESTFLOW_SETTINGS="not a dict"):
        assert restflow_settings.CACHE_SETTINGS.MAX_KEY_SUFFIX_LENGTH == 250


def test_user_section_replaced_with_empty_dict_when_not_a_dict():
    with override_settings(RESTFLOW_SETTINGS={"CACHE_SETTINGS": "oops"}):
        assert restflow_settings.CACHE_SETTINGS.MAX_KEY_SUFFIX_LENGTH == 250


def test_default_loader_returns_empty_when_django_settings_unconfigured():
    from unittest.mock import patch

    from django.core.exceptions import ImproperlyConfigured

    from restflow.settings import RestflowSettings

    class _Unconfigured:
        def __getattr__(self, name):
            raise ImproperlyConfigured("not configured")

    with patch("restflow.settings.django_settings", _Unconfigured()):
        assert RestflowSettings._read_django_settings() == {}


def test_hash_string_uses_sha256_by_default():
    import hashlib

    from restflow.caching.hashing import hash_string

    assert hash_string("hello") == hashlib.sha256(b"hello").hexdigest()


def test_hash_string_honors_configured_hashlib_name():
    import hashlib

    from restflow.caching.hashing import hash_string

    with override_settings(
        RESTFLOW_SETTINGS={"CACHE_SETTINGS": {"KEY_HASH_ALGORITHM": "blake2b"}}
    ):
        assert hash_string("hello") == hashlib.blake2b(b"hello").hexdigest()


def test_hash_string_accepts_callable():
    from restflow.caching.hashing import hash_string

    with override_settings(
        RESTFLOW_SETTINGS={
            "CACHE_SETTINGS": {"KEY_HASH_ALGORITHM": lambda s: f"H:{s}"}
        }
    ):
        assert hash_string("hello") == "H:hello"
