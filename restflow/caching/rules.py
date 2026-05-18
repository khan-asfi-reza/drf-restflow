from __future__ import annotations

import dataclasses
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from django.db import models

from restflow.settings import restflow_settings

if TYPE_CHECKING:  # pragma: no cover
    from restflow.caching.dispatchers.base import Dispatcher


@dataclasses.dataclass(slots=True)
class InvalidationRule:
    """
    Declarative rule that connects a Django model's signals to cache invalidation.

    A rule invalidates in one of two ways: a field_mapping that maps
    cache-key argument names onto attributes of the saving instance,
    or a custom invalidator callable that takes over the work.
    """

    model: type[models.Model]
    rewarm: bool = False
    field_mapping: dict[str, str] = dataclasses.field(default_factory=dict)
    require_args: bool | list[str] = True
    trigger_on_create: bool = False
    watch_fields: list[str] | None = None
    invalidate_when: dict[str, Any] = dataclasses.field(default_factory=dict)
    invalidator: Callable[..., None] | str | None = None

    dispatcher: str | type[Dispatcher] | None = None
    dispatcher_config: dict[str, Any] = dataclasses.field(
        default_factory=dict
    )
    batch: bool = False

    raise_exception: bool | None = None

    _resolved_invalidator: Callable[..., None] | None = dataclasses.field(
        default=None, init=False, repr=False, compare=False
    )
    _dispatcher_instance: Dispatcher | None = dataclasses.field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self):
        if self.invalidator is not None:
            if self.field_mapping:
                msg = (
                    "InvalidationRule.invalidator and "
                    "InvalidationRule.field_mapping are mutually exclusive, "
                    "the invalidator owns the work and bypasses field_mapping."
                )
                raise ValueError(msg)
            if not (
                callable(self.invalidator)
                or isinstance(self.invalidator, str)
            ):
                msg = (
                    f"InvalidationRule.invalidator must be a callable or a "
                    f"dotted-path string, got "
                    f"{type(self.invalidator).__name__}."
                )
                raise TypeError(msg)

    def resolve_invalidator(self) -> Callable[..., None]:
        """Return the invalidator as a callable, importing dotted-path strings on first use."""
        if self._resolved_invalidator is not None:
            return self._resolved_invalidator
        target = self.invalidator
        if isinstance(target, str):
            module_path, _, attr = target.rpartition(".")
            if not module_path:
                msg = (
                    f"InvalidationRule.invalidator string must be a dotted "
                    f"import path (e.g. 'myapp.invalidators.foo'), got "
                    f"{target!r}."
                )
                raise ValueError(msg)
            module = importlib.import_module(module_path)
            target = getattr(module, attr)
        self._resolved_invalidator = target
        return target

    def get_dispatcher(self) -> Dispatcher:
        """Return the Dispatcher instance for this rule, building it on the first call and caching it."""
        if self._dispatcher_instance is None:
            # Inline import: `restflow.caching.dispatchers` depends on
            # `restflow.caching.registry`, which depends on this
            # module. Hoisting this would form a cycle.
            from restflow.caching.dispatchers import resolve  # noqa: PLC0415

            spec = self.dispatcher
            if spec is None:
                spec = restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER
            self._dispatcher_instance = resolve(
                spec, self.dispatcher_config
            )
        return self._dispatcher_instance
