from __future__ import annotations

from typing import Any

from restflow.caching.dispatchers.base import DEFAULT_FUNCTION_PATH, Dispatcher

try:
    import django_q  # noqa: F401  # `django-q` and `django-q2` both expose this name
    _django_q_available = True
except ImportError:  # pragma: no cover
    _django_q_available = False


def _require_django_q():
    if not _django_q_available:
        msg = (
            "django-q2 is required for the django_q dispatcher. "
            "Install django-q2 to use "
            "`InvalidationRule(dispatcher='django_q')`."
        )
        raise ImportError(msg)


class DjangoQDispatcher(Dispatcher):
    """Hand invalidation work off to django-q or django-q2."""

    name = "django_q"

    def validate_config(self) -> None:
        """Verify django-q is installed and importable."""
        _require_django_q()

    def _resolved_cluster(self) -> str | None:
        return self.config.get("cluster") or self.settings().get(
            "CLUSTER"
        )

    def _resolved_group(self) -> str | None:
        return self.config.get("group") or self.settings().get("GROUP")

    def _resolved_function_path(self) -> str:
        return (
            self.config.get("function_path")
            or self.settings().get("FUNCTION_PATH")
            or DEFAULT_FUNCTION_PATH
        )

    def batch_key(self) -> tuple:
        """Group rules by cluster, group, and worker function path."""
        return (
            self.__class__,
            self._resolved_cluster(),
            self._resolved_group(),
            self._resolved_function_path(),
        )

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Enqueue the rules through django-q's async_task."""
        _require_django_q()
        from django_q.tasks import async_task  # noqa: PLC0415

        opts: dict[str, Any] = {}
        cluster = self._resolved_cluster()
        if cluster:
            opts["cluster"] = cluster
        group = self._resolved_group()
        if group:
            opts["group"] = group
        async_task(
            self._resolved_function_path(),
            rule_ids,
            rule_kwargs,
            dispatcher_name=self.name,
            **opts,
        )
