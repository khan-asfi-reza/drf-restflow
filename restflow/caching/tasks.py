from __future__ import annotations

import logging
from typing import Any

from restflow.caching.dispatchers.base import get_dispatcher_settings
from restflow.caching.registry import CacheRegister
from restflow.helpers import maybe_await, run_sync
from restflow.settings import restflow_settings

try:
    from celery import shared_task
except ImportError:  # pragma: no cover
    shared_task = None

logger = logging.getLogger(__name__)


def _resolve_raise_errors(dispatcher_name: str | None) -> bool:
    if dispatcher_name:
        per = get_dispatcher_settings(dispatcher_name).get("RAISE_EXCEPTION")
        if per is not None:
            return bool(per)

    return bool(restflow_settings.CACHE_SETTINGS.DISPATCHER_RAISE_EXCEPTION)


def run_cache_rules(
    rule_ids: list[int],
    rule_kwargs: dict[str, dict[str, Any]],
    *,
    dispatcher_name: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Run registered invalidation rules.

    Synchronous worker entry used by every dispatcher except the
    asyncio one. Errors are caught and logged unless an explicit
    raise_exception override has been configured.
    """
    try:
        run_sync(
            CacheRegister.run_cache_rules(
                rule_ids=rule_ids, rule_kwargs=rule_kwargs
            )
        )
    except Exception:
        if _resolve_raise_errors(dispatcher_name):
            raise
        logger.exception(
            "restflow.run_cache_rules failed (rule_ids=%s, dispatcher=%s, context=%s)",
            rule_ids,
            dispatcher_name,
            context,
        )


async def arun_cache_rules(
    rule_ids: list[int],
    rule_kwargs: dict[str, dict[str, Any]],
    *,
    dispatcher_name: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Async variant of run_cache_rules with the same error-handling semantics."""
    try:
        await maybe_await(
            CacheRegister.run_cache_rules(
                rule_ids=rule_ids, rule_kwargs=rule_kwargs
            )
        )
    except Exception:
        if _resolve_raise_errors(dispatcher_name):
            raise
        logger.exception(
            "restflow.arun_cache_rules failed (rule_ids=%s, dispatcher=%s, context=%s)",
            rule_ids,
            dispatcher_name,
            context,
        )


def task_run_cache_rules(
    *,
    rule_ids: list[int],
    rule_kwargs: dict[str, dict[str, Any]],
    **context: Any,
) -> None:
    """Celery task that invalidates cache rules, registered as a shared_task when Celery is installed."""
    run_cache_rules(
        rule_ids,
        rule_kwargs,
        dispatcher_name="celery",
        context=context,
    )


if shared_task is not None:
    # For celery task creation.
    task_run_cache_rules = shared_task(
        name="restflow.caching.tasks.task_run_cache_rules"
    )(task_run_cache_rules)
