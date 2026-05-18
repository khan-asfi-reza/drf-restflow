from __future__ import annotations

from typing import Any

from restflow.caching.dispatchers.base import (
    DEFAULT_FUNCTION_PATH,
    Dispatcher,
    import_dotted,
)

try:
    import django_rq
except ImportError:  # pragma: no cover
    django_rq = None


def _require_django_rq():
    if django_rq is None:
        msg = (
            "django-rq is required for the rq dispatcher. "
            "Install django-rq to use "
            "`InvalidationRule(dispatcher='django_rq')`."
        )
        raise ImportError(msg)
    return django_rq


class DjangoRqDispatcher(Dispatcher):
    """Hand invalidation work off to django-rq."""

    name = "django_rq"

    def validate_config(self) -> None:
        """Verify django-rq is installed and importable."""
        _require_django_rq()

    def _resolved_queue(self) -> str:
        return (
            self.config.get("queue")
            or self.settings().get("QUEUE")
            or "default"
        )

    def _resolved_function_path(self) -> str:
        return (
            self.config.get("function_path")
            or self.settings().get("FUNCTION_PATH")
            or DEFAULT_FUNCTION_PATH
        )

    def batch_key(self) -> tuple:
        """Group rules by RQ queue and worker function path."""
        return (
            self.__class__,
            self._resolved_queue(),
            self._resolved_function_path(),
        )

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Enqueue the rules on the resolved RQ queue."""
        rq = _require_django_rq()
        worker = import_dotted(self._resolved_function_path())
        rq.get_queue(self._resolved_queue()).enqueue(
            worker,
            rule_ids,
            rule_kwargs,
            dispatcher_name=self.name,
        )
