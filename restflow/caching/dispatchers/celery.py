from __future__ import annotations

from typing import Any

from restflow.caching.dispatchers.base import Dispatcher

try:
    from celery import current_app as _celery_current_app
except ImportError:  # pragma: no cover
    _celery_current_app = None


def _require_celery():
    if _celery_current_app is None:
        msg = (
            "celery is required for celery-based cache invalidation. "
            "Install celery to use "
            "`InvalidationRule(dispatcher='celery')`."
        )
        raise ImportError(msg)
    return _celery_current_app


class CeleryDispatcher(Dispatcher):
    """
    Hand invalidation work off to a Celery task.

    Calls `apply_async` when the configured task is registered on the
    current Celery app, falls back to `send_task` for tasks defined
    only on a remote worker.
    """

    name = "celery"

    def validate_config(self) -> None:
        """Verify Celery is installed and importable."""
        _require_celery()

    def _resolved_task_name(self) -> str:
        return self.config.get("task_name") or self.settings().get(
            "TASK_NAME"
        )

    def _resolved_queue(self) -> str | None:
        if "queue" in self.config:
            return self.config["queue"]
        return self.settings().get("QUEUE")

    def batch_key(self) -> tuple:
        """Group rules by Celery task name and queue."""
        return (
            self.__class__,
            self._resolved_task_name(),
            self._resolved_queue(),
        )

    def dispatch(
        self,
        *,
        model_label: str,
        pk: Any,
        rule_ids: list[int],
        signal_type,
        rule_kwargs: dict[str, dict[str, Any]],
    ) -> None:
        """Send the rules to the configured Celery task."""
        celery_app = _require_celery()
        task_name = self._resolved_task_name()
        queue = self._resolved_queue()

        options: dict[str, Any] = {}
        if queue:
            options["queue"] = queue

        kwargs = {
            "model_label": model_label,
            "pk": pk,
            "rule_ids": rule_ids,
            "signal_type": signal_type.value,
            "rule_kwargs": rule_kwargs,
        }

        if task_name in celery_app.tasks:
            celery_app.tasks[task_name].apply_async(
                kwargs=kwargs, **options
            )
        else:
            celery_app.send_task(task_name, kwargs=kwargs, **options)
