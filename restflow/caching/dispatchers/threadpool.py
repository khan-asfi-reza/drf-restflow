from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from restflow.caching.dispatchers.base import Dispatcher
from restflow.caching.tasks import run_cache_rules

logger = logging.getLogger(__name__)


class ThreadPoolDispatcher(Dispatcher):
    """
    Run invalidation off the request thread on a shared ThreadPoolExecutor.

    The executor is built once per process. There is no durability,
    work that has not finished is lost if the process exits.
    """

    name = "threadpool"

    _executor: ThreadPoolExecutor | None = None
    _executor_lock = threading.Lock()

    def validate_config(self) -> None:
        """Verify max_workers is a positive integer when supplied."""
        max_workers = self.config.get("max_workers")
        if max_workers is not None and (
            not isinstance(max_workers, int) or max_workers < 1
        ):
            msg = (
                "ThreadPoolDispatcher max_workers must be a positive int, "
                f"got {max_workers!r}."
            )
            raise ValueError(msg)

    def _resolved_max_workers(self) -> int:
        return int(
            self.config.get("max_workers")
            or self.settings().get("MAX_WORKERS")
            or 4
        )

    @classmethod
    def _get_executor(cls, max_workers: int) -> ThreadPoolExecutor:
        if cls._executor is None:
            with cls._executor_lock:
                if cls._executor is None:
                    cls._executor = ThreadPoolExecutor(
                        max_workers=max_workers,
                        thread_name_prefix="restflow-cache",
                    )
        return cls._executor

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Submit the rules to the shared thread-pool executor."""
        executor = self._get_executor(self._resolved_max_workers())
        future = executor.submit(
            run_cache_rules,
            rule_ids=rule_ids,
            rule_kwargs=rule_kwargs,
            dispatcher_name=self.name,
        )
        future.add_done_callback(_log_future_exception)


def _log_future_exception(future) -> None:
    try:
        future.result()
    except Exception:
        logger.warning(
            "restflow ThreadPoolDispatcher: worker raised", exc_info=True
        )
