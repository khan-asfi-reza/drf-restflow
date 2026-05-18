from __future__ import annotations

from typing import Any

from restflow.caching.dispatchers.base import Dispatcher
from restflow.caching.tasks import run_cache_rules


class InlineDispatcher(Dispatcher):
    """
    Run invalidation work synchronously on the same thread as the model save.

    The default dispatcher when no dispatcher is specified on a rule.
    """

    name = "inline"
    supports_batching = False

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Run the rules immediately on the calling thread."""
        run_cache_rules(
            rule_ids=rule_ids,
            rule_kwargs=rule_kwargs,
            dispatcher_name=self.name,
        )
