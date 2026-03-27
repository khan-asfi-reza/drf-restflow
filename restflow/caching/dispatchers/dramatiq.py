from __future__ import annotations

import threading
from typing import Any

from restflow.caching.dispatchers.base import Dispatcher
from restflow.caching.tasks import run_cache_rules

try:
    import dramatiq as _dramatiq
except ImportError:  # pragma: no cover
    _dramatiq = None


def _require_dramatiq():
    if _dramatiq is None:
        msg = (
            "dramatiq is required for the dramatiq dispatcher. "
            "Install dramatiq to use "
            "`InvalidationRule(dispatcher='dramatiq')`."
        )
        raise ImportError(msg)
    return _dramatiq


def register_actor(actor_name: str = "restflow.task_run_cache_rules"):
    """Register the cache invalidation actor with the current Dramatiq broker."""
    dr = _require_dramatiq()

    @dr.actor(actor_name=actor_name)
    def _actor(rule_ids, rule_kwargs):
        run_cache_rules(rule_ids, rule_kwargs, dispatcher_name="dramatiq")

    return _actor


class DramatiqDispatcher(Dispatcher):
    """Hand invalidation work off to a Dramatiq actor."""

    name = "dramatiq"

    _actor = None
    _actor_lock = threading.Lock()

    def validate_config(self) -> None:
        """Verify Dramatiq is installed and importable."""
        _require_dramatiq()

    def _resolved_queue(self) -> str:
        return (
            self.config.get("queue")
            or self.settings().get("QUEUE")
            or "default"
        )

    def _resolved_actor_name(self) -> str:
        return (
            self.config.get("actor_name")
            or self.settings().get("ACTOR_NAME")
            or "restflow.task_run_cache_rules"
        )

    def batch_key(self) -> tuple:
        """Group rules by Dramatiq queue and actor name."""
        return (
            self.__class__,
            self._resolved_queue(),
            self._resolved_actor_name(),
        )

    def _ensure_actor(self):
        if DramatiqDispatcher._actor is None:
            with DramatiqDispatcher._actor_lock:
                if DramatiqDispatcher._actor is None:
                    DramatiqDispatcher._actor = register_actor(
                        self._resolved_actor_name()
                    )
        return DramatiqDispatcher._actor

    def dispatch(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]],
        **_context: Any,
    ) -> None:
        """Send the rules to the Dramatiq actor on the resolved queue."""
        actor = self._ensure_actor()
        actor.send_with_options(
            args=(rule_ids, rule_kwargs),
            queue_name=self._resolved_queue(),
        )
