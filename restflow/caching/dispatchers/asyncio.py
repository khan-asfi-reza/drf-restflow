from __future__ import annotations

import asyncio
import logging
from typing import Any

from restflow.caching.dispatchers.base import Dispatcher
from restflow.caching.tasks import arun_cache_rules, run_cache_rules

logger = logging.getLogger(__name__)


class AsyncIODispatcher(Dispatcher):
    """
    Schedule invalidation on the running asyncio event loop.

    Falls back to the synchronous worker when no loop is running on the
    calling thread.
    """

    name = "asyncio"
    supports_batching = False

    _pending_tasks: set[asyncio.Task] = set()

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Schedule the rules on the running loop, or run them inline if no loop is active."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug(
                "AsyncIODispatcher: no running loop, falling back to "
                "the sync worker entry."
            )
            run_cache_rules(
                rule_ids=rule_ids,
                rule_kwargs=rule_kwargs,
                dispatcher_name=self.name,
            )
            return

        task = loop.create_task(
            arun_cache_rules(
                rule_ids=rule_ids,
                rule_kwargs=rule_kwargs,
                dispatcher_name=self.name,
            )
        )
        AsyncIODispatcher._pending_tasks.add(task)
        task.add_done_callback(AsyncIODispatcher._pending_tasks.discard)
