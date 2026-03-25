from __future__ import annotations

import abc
import importlib
from collections.abc import Callable
from typing import Any

from restflow.settings import restflow_settings

#: Default worker entry point used by broker-backed dispatchers
#: (`django-q`, `django-rq`) when no per-rule or per-settings
#: `function_path` is supplied. Resolves to
#: :func:`restflow.caching.tasks.run_cache_rules`.
DEFAULT_FUNCTION_PATH = "restflow.caching.tasks.run_cache_rules"


def get_dispatcher_settings(name: str) -> dict[str, Any]:
    blocks = restflow_settings.CACHE_SETTINGS.DISPATCHER_SETTINGS
    if hasattr(blocks, name):
        return getattr(blocks, name).to_dict()
    return blocks.to_dict().get(name, {})


def import_dotted(path: str) -> Callable:
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        msg = f"Invalid dotted path: {path!r}"
        raise ImportError(msg)
    module = importlib.import_module(module_name)
    return getattr(module, attr)


class Dispatcher(abc.ABC):
    """
    Abstract base for cache invalidation backends.

    A Dispatcher decides where the invalidation work runs: synchronously
    on the request thread, on a thread pool, on an asyncio event loop,
    or handed off to a task broker. Subclasses set a stable `name` and
    implement `dispatch`.
    """

    name: str
    supports_batching: bool = True

    def __init__(self, **config: Any):
        self.config = config
        self.validate_config()

    def validate_config(self) -> None:  # noqa: B027
        """Hook for subclasses to validate config or import optional dependencies, no-op by default."""

    @abc.abstractmethod
    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **context: Any,
    ) -> None:
        """Run one group of invalidation rules."""

    def batch_key(self) -> tuple:
        """Return a hashable identity that groups rules into a single dispatch call."""
        return (self.__class__, tuple(sorted(self.config.items())))

    @classmethod
    def settings(cls) -> dict[str, Any]:
        """Return the merged settings block for this dispatcher."""
        return get_dispatcher_settings(cls.name)
