from __future__ import annotations

from typing import Any

from restflow.caching.dispatchers.asyncio import AsyncIODispatcher
from restflow.caching.dispatchers.base import Dispatcher
from restflow.caching.dispatchers.celery import CeleryDispatcher
from restflow.caching.dispatchers.django_q import DjangoQDispatcher
from restflow.caching.dispatchers.django_rq import DjangoRqDispatcher
from restflow.caching.dispatchers.dramatiq import DramatiqDispatcher
from restflow.caching.dispatchers.inline import InlineDispatcher
from restflow.caching.dispatchers.threadpool import ThreadPoolDispatcher

_REGISTRY: dict[str, type[Dispatcher]] = {}


def register(cls: type[Dispatcher]) -> type[Dispatcher]:
    """
    Register a Dispatcher subclass under its `name` so rules can select it by string.

    Usable as a class decorator. Registering a name that already exists
    overwrites the previous entry.

    Example::

        @register
        class MyDispatcher(Dispatcher):
            name = "my-dispatcher"
            ...
    """
    if not isinstance(cls, type) or not issubclass(cls, Dispatcher):
        msg = (
            f"register() expects a Dispatcher subclass, got {cls!r}."
        )
        raise TypeError(msg)
    if not getattr(cls, "name", None):
        msg = (
            f"Dispatcher {cls.__name__} must set a non-empty `name` "
            f"attribute to be registered."
        )
        raise ValueError(msg)
    _REGISTRY[cls.name] = cls
    return cls


def resolve(
    spec: str | type[Dispatcher],
    config: dict[str, Any] | None = None,
) -> Dispatcher:
    """Build a dispatcher from a registered name or a dispatcher class."""
    cfg = config or {}
    if isinstance(spec, str):
        cls = _REGISTRY.get(spec)
        if cls is None:
            available = ", ".join(sorted(_REGISTRY)) or "(none)"
            msg = (
                f"Unknown dispatcher name {spec!r}. "
                f"Registered dispatchers: {available}. "
                f"Either pass a Dispatcher subclass directly or call "
                f"`restflow.caching.dispatchers.register(YourDispatcher)` "
                f"before using its name."
            )
            raise KeyError(msg)
        return cls(**cfg)

    if isinstance(spec, type) and issubclass(spec, Dispatcher):
        return spec(**cfg)

    msg = (
        f"InvalidationRule.dispatcher must be a name string or a "
        f"Dispatcher subclass, got {spec!r}."
    )
    raise TypeError(msg)


def registered_names() -> list[str]:
    """Return a sorted list of every dispatcher name currently registered."""
    return sorted(_REGISTRY)


register(InlineDispatcher)
register(CeleryDispatcher)
register(ThreadPoolDispatcher)
register(AsyncIODispatcher)
register(DjangoRqDispatcher)
register(DramatiqDispatcher)
register(DjangoQDispatcher)


# Public-API aliases used at the top-level `restflow.caching`
# namespace, where the bare names would be ambiguous.
register_dispatcher = register
registered_dispatcher_names = registered_names


__all__ = [
    "AsyncIODispatcher",
    "CeleryDispatcher",
    "Dispatcher",
    "DjangoQDispatcher",
    "DjangoRqDispatcher",
    "DramatiqDispatcher",
    "InlineDispatcher",
    "ThreadPoolDispatcher",
    "register",
    "register_dispatcher",
    "registered_dispatcher_names",
    "registered_names",
    "resolve",
]
