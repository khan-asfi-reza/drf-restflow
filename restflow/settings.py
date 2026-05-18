from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.test.signals import setting_changed

DEFAULTS: dict[str, Any] = {
    "JWT": {
        "SIGNING_KEY": None,
        "VERIFYING_KEY": None,
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ISSUER": None,
        "AUDIENCE": None,
        "USER_ID_CLAIM": "user_id",
        "USER_ID_FIELD": "id",
        "USER_ID_FIELD_ALLOWLIST": ("id", "pk", "uuid", "username", "email"),
        "AUTH_HEADER_TYPES": ("Bearer",),
        "BLACKLIST_ENABLED": True,
        "BLACKLIST_BACKEND": "restflow.authentication.jwt.CacheBlacklistBackend",
        "BLACKLIST_CACHE_ALIAS": "default",
        "BLACKLIST_ALLOW_LOCMEM": False,
        "ROTATE_REFRESH_TOKENS": True,
        "LEEWAY": 0,
        "CHECK_USER_IS_ACTIVE": True,
        "CHECK_REVOKE_TOKEN": False,
        "REVOKE_TOKEN_CLAIM": "hash_password",
        "USER_AUTHENTICATION_RULE": "restflow.authentication.jwt.default_user_authentication_rule",
    },
    "CACHE_SETTINGS": {
        "MAX_KEY_SUFFIX_LENGTH": 250,
        "HASH_SUFFIX_ON_OVERFLOW": False,
        # Algorithm used by `hash_string` for cache-key hashing. Either
        # a hashlib name (`"sha256"`, `"blake2b"`, `"md5"`, ...) or
        # a callable `(str) -> str` returning the hex digest.
        "KEY_HASH_ALGORITHM": "sha256",
        # Name of the dispatcher used by an `InvalidationRule` that does
        # not pass `dispatcher=` itself.
        "DEFAULT_DISPATCHER": "inline",
        # Global default for whether the worker-side entry should re-raise
        # framework-level errors, Per Dispatcher settings ovverrides.
        "DISPATCHER_RAISE_EXCEPTION": False,
        # Per-dispatcher defaults, keyed by dispatcher `name`.
        "DISPATCHER_SETTINGS": {
            "celery": {
                "TASK_NAME": "restflow.caching.tasks.task_run_cache_rules",
                "QUEUE": None,
                "RAISE_EXCEPTION": None,
            },
            "threadpool": {
                "MAX_WORKERS": 4,
                "RAISE_EXCEPTION": None,
            },
            "django_rq": {
                "QUEUE": "default",
                "FUNCTION_PATH": "restflow.caching.tasks.run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "dramatiq": {
                "QUEUE": "default",
                "ACTOR_NAME": "restflow.task_run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "django_q": {
                "CLUSTER": None,
                "GROUP": None,
                "FUNCTION_PATH": "restflow.caching.tasks.run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "asyncio": {
                "RAISE_EXCEPTION": None,
            },
            "inline": {
                "RAISE_EXCEPTION": None,
            },
        },
    },
}


class RestflowSettings:

    def __init__(
        self,
        defaults: dict[str, Any],
        user_settings_loader: Callable[[], dict[str, Any]] | None = None,
    ):
        self._defaults = defaults
        self._user_settings_loader = (
            user_settings_loader
            if user_settings_loader is not None
            else self._read_django_settings
        )
        self._cached: dict[str, Any] = {}

    @staticmethod
    def _read_django_settings() -> dict[str, Any]:
        try:
            value = getattr(django_settings, "RESTFLOW_SETTINGS", {}) or {}
        except ImproperlyConfigured:  # pragma: no cover
            return {}
        if not isinstance(value, dict):
            return {}
        return value

    @property
    def user_settings(self) -> dict[str, Any]:
        return self._user_settings_loader() or {}

    def __getattr__(self, attr: str):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if attr not in self._defaults:
            msg = f"Invalid restflow setting: {attr!r}"
            raise AttributeError(msg)
        if attr in self._cached:
            return self._cached[attr]

        default = self._defaults[attr]
        user = self.user_settings if isinstance(self.user_settings, dict) else {}

        if isinstance(default, dict):
            user_section = user.get(attr, {}) if isinstance(user, dict) else {}
            if not isinstance(user_section, dict):
                user_section = {}
            value: Any = RestflowSettings(
                defaults=default,
                user_settings_loader=lambda section=user_section: section,
            )
        else:
            value = user.get(attr, default) if isinstance(user, dict) else default

        self._cached[attr] = value
        return value

    def reload(self) -> None:
        for child in self._cached.values():
            if isinstance(child, RestflowSettings):
                child.reload()
        self._cached.clear()

    def to_dict(self) -> dict[str, Any]:
        user = self.user_settings if isinstance(self.user_settings, dict) else {}
        result: dict[str, Any] = {}
        for key in self._defaults:
            value = getattr(self, key)
            if isinstance(value, RestflowSettings):
                value = value.to_dict()
            result[key] = value
        for key, value in user.items():
            if key not in result:
                result[key] = value
        return result


#: Process-wide :class:`RestflowSettings` instance. The canonical
#: import target instead of a fresh :class:`RestflowSettings` instance.
restflow_settings = RestflowSettings(defaults=DEFAULTS)


def reload_restflow_settings(*, setting, **_kwargs):
    if setting == "RESTFLOW_SETTINGS":
        restflow_settings.reload()


setting_changed.connect(reload_restflow_settings)
