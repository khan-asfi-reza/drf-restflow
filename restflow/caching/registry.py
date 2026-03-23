from __future__ import annotations

import enum
import importlib
import inspect
import logging
import pkgutil
import threading
from typing import TYPE_CHECKING, Any, TypedDict

from django.apps import apps
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save

from restflow.caching.constants import CACHE_MISSING
from restflow.caching.rules import InvalidationRule
from restflow.helpers import run_sync

if TYPE_CHECKING:  # pragma: no cover
    from restflow.caching.dispatchers.base import Dispatcher
    from restflow.caching.wrapper import CachedWrapper

logger = logging.getLogger(__name__)


class _RuleTypeBase(TypedDict):
    func: CachedWrapper
    invalidation_rule: InvalidationRule


class PendingConfigType(_RuleTypeBase):
    model: type[models.Model]


class RuleType(_RuleTypeBase):
    id: int


class CacheRegistry:
    """
    Process-wide registry of cache invalidation rules.

    Tracks which Django models have InvalidationRule objects registered
    against them, connects post_save and post_delete signals the first
    time a model shows up, and hands the invalidation work to the
    rule's Dispatcher whenever a signal fires.
    """

    _instance: CacheRegistry = None
    _counter = 0
    _lock = threading.Lock()

    class SignalTypes(enum.Enum):
        """Which Django model signal triggered an invalidation."""

        POST_SAVE = "POST_SAVE"
        POST_DELETE = "POST_DELETE"

    @classmethod
    def _create_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._initialized = False
        return cls._instance

    def __new__(cls):
        return cls._create_instance()

    def __init__(self, name: str = "default"):
        if self._initialized:
            return

        self.name = name
        self._pending: list[PendingConfigType] = []
        self._model_rule_ids: dict[type[models.Model], list[int]] = {}
        self._rules: dict[int, RuleType] = {}
        self._connected_models: set[type[models.Model]] = set()
        self._discovered: bool = False
        self._initialized = True

    def add(
        self,
        model: type[models.Model],
        func: CachedWrapper,
        invalidation_rule: InvalidationRule,
    ):
        """Register a cache wrapper so that saves and deletes on the given model invalidate it."""
        if not (
            hasattr(func, "is_cached_function") and func.is_cached_function
        ):
            msg = "Must be a decorated function of `@cached_result`"
            raise AttributeError(msg)

        config: PendingConfigType = {
            "model": model,
            "func": func,
            "invalidation_rule": invalidation_rule,
        }

        self._pending.append(config)

        if self._discovered:
            self._register(config)

    def register(
        self,
        model: type[models.Model],
        func: CachedWrapper,
        invalidation_rule: InvalidationRule,
    ):
        """Alias for add()."""
        self.add(
            model=model,
            func=func,
            invalidation_rule=invalidation_rule,
        )

    def _register(self, config: PendingConfigType):
        model = config["model"]

        if model not in self._model_rule_ids:
            self._model_rule_ids[model] = []

        self._counter += 1
        CacheRegistry._counter = self._counter

        _registry: RuleType = {
            "id": self._counter,
            "invalidation_rule": config["invalidation_rule"],
            "func": config["func"],
        }
        self._rules[self._counter] = _registry
        self._model_rule_ids[model].append(self._counter)
        self._connect_signals(model)

    def auto_discover(self):
        """Walk every installed app and import its submodules so module-level @cache_result decorators run."""
        if self._discovered:
            return self

        self._discovered = True
        self._import_cache_modules()

        for config in self._pending:
            self._register(config)

        logger.info(
            f"Cache rule '{self.name}': "
            f"{len(self._pending)} functions, "
            f"{len(self._connected_models)} models"
        )
        self._pending.clear()
        return self

    @staticmethod
    def _import_cache_modules():
        """Import every submodule of each installed app, skipping migrations."""
        # Migrations are auto generated, so skip it.
        skip = {"migrations",}
        for app_config in apps.get_app_configs():
            app_module = importlib.import_module(app_config.name)
            if not hasattr(app_module, "__path__"):
                continue

            module_file = getattr(app_module, "__file__", "") or ""
            # Site packages must also be excluded, otherwise the startup time of the app will increase.
            if "site-packages" in module_file:
                continue

            for _, subname, _is_pkg in pkgutil.walk_packages(
                app_module.__path__, prefix=f"{app_config.name}."
            ):
                parts = subname[len(app_config.name) + 1 :].split(".")
                if skip & set(parts):
                    continue
                try:
                    importlib.import_module(subname)
                except ImportError:
                    # Optional adapters may fail if dependencies are missing, but that's fine.
                    # We'll try again when the user explicitly uses the adapter in settings.
                    pass
                except (KeyboardInterrupt, SystemExit, MemoryError):  # pragma: no cover
                    raise
                except BaseException:
                    logger.warning(
                        "restflow auto_discover: failed to import %s",
                        subname,
                        exc_info=True,
                    )

    def get_rule(self, rule_id: int):
        """Return the rule recorded under rule_id, or None when there is no such rule."""
        return self._rules.get(rule_id, None)

    def _connect_signals(self, model):
        if model not in self._connected_models:
            post_save.connect(self._on_save, sender=model)
            post_delete.connect(self._on_delete, sender=model)
            self._connected_models.add(model)

    def _on_save(self, sender, instance, created, **kwargs):  # noqa: ARG002
        update_fields = kwargs.get("update_fields")
        transaction.on_commit(
            lambda: self.invalidate_for_instance(
                instance,
                instance_created=created,
                signal_type=self.SignalTypes.POST_SAVE,
                update_fields=(
                    frozenset(update_fields) if update_fields else None
                ),
            )
        )

    def _on_delete(self, sender, instance, **kwargs):  # noqa: ARG002
        transaction.on_commit(
            lambda: self.invalidate_for_instance(
                instance,
                instance_created=False,
                signal_type=self.SignalTypes.POST_DELETE,
                update_fields=None,
            )
        )

    def _resolve_rule_kwargs(self, instance, invalidation_rule):
        field_mapping = invalidation_rule.field_mapping

        if field_mapping and not instance:
            return None

        func_kwargs = self._extract_kwargs(instance, field_mapping)

        require = invalidation_rule.require_args
        if require is True:
            required_fields = list(field_mapping.keys())
        elif require is False:
            required_fields = []
        else:
            required_fields = list(require)

        for field in required_fields:
            if func_kwargs.get(field) is None:
                return None

        if require is True:
            func_kwargs = {
                k: v for k, v in func_kwargs.items() if v is not None
            }

        return func_kwargs

    def process_rule(self, rule: RuleType, func_kwargs: dict):
        """Apply a single rule by either rewarming the cached value or wiping its partition."""
        func = rule["func"]
        invalidation_rule = rule["invalidation_rule"]
        rewarm = invalidation_rule.rewarm
        raise_exception = bool(invalidation_rule.raise_exception)

        if getattr(func, "_is_async", False):
            return self.process_rule_async(
                func, rewarm, func_kwargs, raise_exception
            )

        try:
            if rewarm:
                func.refresh(**func_kwargs)
                return None
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(f"Re-warm failed for {func.__name__}: {e}")

        try:
            func.delete_by_prefix(**func_kwargs)
            return None
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(f"Cache delete failed for {func.__name__}: {e}")

    async def process_rule_async(
        self, func, rewarm, func_kwargs, raise_exception
    ):
        try:
            if rewarm:
                await func.arefresh(**func_kwargs)
                return
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(f"Re-warm failed for {func.__name__}: {e}")

        try:
            await func.adelete_by_prefix(**func_kwargs)
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(f"Cache delete failed for {func.__name__}: {e}")

    def _run_invalidator(
        self,
        rule: RuleType,
        instance: Any,
        signal_type: CacheRegistry.SignalTypes,
        instance_created: bool,
        update_fields: frozenset | None,
    ) -> None:
        # Custom invalidator runner.
        # If custom invalidator function is defined in rules, call it, otherwise use default behavior.
        invalidation_rule = rule["invalidation_rule"]
        func = rule["func"]
        raise_exception = bool(invalidation_rule.raise_exception)
        target = invalidation_rule.resolve_invalidator()

        all_extras = {
            "signal_type": signal_type,
            "instance_created": instance_created,
            "update_fields": update_fields,
        }
        try:
            sig = inspect.signature(target)
            params = sig.parameters
            accepts_var_kw = any(
                p.kind is inspect.Parameter.VAR_KEYWORD
                for p in params.values()
            )
            extras = (
                all_extras
                if accepts_var_kw
                else {k: v for k, v in all_extras.items() if k in params}
            )
        except (TypeError, ValueError):
            extras = {}

        if inspect.iscoroutinefunction(target):
            return self._run_invalidator_async(
                target, func, instance, extras, raise_exception
            )

        try:
            target(func, instance, **extras)
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(
                f"Custom invalidator failed for {func.__name__}: {e}"
            )

    async def _run_invalidator_async(
        self, target, func, instance, extras, raise_exception
    ):
        # Async custom invalidator runner.
        try:
            await target(func, instance, **extras)
        except Exception as e:
            if raise_exception:
                raise
            logger.warning(
                f"Custom invalidator failed for {func.__name__}: {e}"
            )

    @staticmethod
    def _has_watched_field_changed(
        watch_fields: list[str],
        update_fields: frozenset | None = None,
    ) -> bool:
        if not watch_fields:
            return True

        if update_fields is not None:
            return bool(set(watch_fields) & update_fields)

        return False

    def invalidate_for_instance(
        self,
        instance: models.Model,
        instance_created: bool,
        signal_type: SignalTypes,
        update_fields: frozenset | None = None,
    ):
        """Run every registered rule for the instance's model class against the given instance."""
        rule_ids = self._model_rule_ids.get(instance.__class__, [])
        self._invalidate_via_dispatchers(
            instance=instance,
            rule_ids=rule_ids,
            instance_created=instance_created,
            signal_type=signal_type,
            update_fields=update_fields,
        )

    def _should_run_rule(
        self,
        instance: models.Model,
        rule: RuleType | None,
        instance_created: bool,
        signal_type: SignalTypes,
        update_fields: frozenset | None = None,
    ):
        if not rule:
            return False

        invalidation_rule = rule["invalidation_rule"]

        if (
            signal_type == self.SignalTypes.POST_SAVE
            and instance_created
            and not invalidation_rule.trigger_on_create
        ):
            return False

        watch_fields = invalidation_rule.watch_fields

        if (
            watch_fields
            and signal_type == self.SignalTypes.POST_SAVE
            and not instance_created
        ):
            # If watch_fields are specified, check if any of them have changed.
            # Checks via model.objects.save(update_fields=...)
            # Currently no other safe way to identify if a field changed or not.
            # One option would be attach a pre_init hook, but, that is very costly and dangerous.
            return self._has_watched_field_changed(
                watch_fields, update_fields
            )

        invalidate_when = invalidation_rule.invalidate_when
        for key, expected in invalidate_when.items():
            negate = key.startswith("!")
            field = key[1:] if negate else key

            actual = getattr(instance, field, CACHE_MISSING)

            if expected is None:
                ok = (actual is not None) if negate else (actual is None)
            else:
                ok = (actual != expected) if negate else (actual == expected)

            if not ok:
                return False

        return True

    def _invalidate_via_dispatchers(
        self,
        instance: models.Model,
        rule_ids: list[int],
        instance_created: bool,
        signal_type: SignalTypes,
        update_fields: frozenset | None = None,
    ):
        # Group by `dispatcher.batch_key()` so rules sharing a
        # dispatcher + config land in one `dispatch()`, rules whose
        # dispatcher refuses batching fall into the per-rule path.
        batch_groups: dict[tuple, list[int]] = {}
        batch_kwargs_per_group: dict[
            tuple, dict[str, dict[str, Any]]
        ] = {}
        dispatcher_per_group: dict[tuple, Dispatcher] = {}

        for rule_id in rule_ids:
            rule: RuleType = self.get_rule(rule_id)

            should_run = self._should_run_rule(
                instance=instance,
                rule=rule,
                instance_created=instance_created,
                signal_type=signal_type,
                update_fields=update_fields,
            )

            if not should_run:
                continue

            invalidation_rule = rule["invalidation_rule"]

            if invalidation_rule.invalidator is not None:
                run_sync(
                    self._run_invalidator(
                        rule=rule,
                        instance=instance,
                        signal_type=signal_type,
                        instance_created=instance_created,
                        update_fields=update_fields,
                    )
                )
                continue

            func_kwargs = self._resolve_rule_kwargs(
                instance, invalidation_rule
            )
            if func_kwargs is None:
                continue

            dispatcher = invalidation_rule.get_dispatcher()
            # Per rule dispatch as a standalone task / operation.
            # This is done when batching is disabled or not supported by the dispatcher.
            # Or user opts in as not using batching.
            standalone = (
                not invalidation_rule.batch
                or not dispatcher.supports_batching
            )

            if standalone:
                dispatcher.dispatch(
                    model_label=instance._meta.label,
                    pk=instance.pk,
                    rule_ids=[rule_id],
                    signal_type=signal_type,
                    rule_kwargs={str(rule_id): func_kwargs},
                )
                continue

            key = dispatcher.batch_key()
            batch_groups.setdefault(key, []).append(rule_id)
            batch_kwargs_per_group.setdefault(key, {})[
                str(rule_id)
            ] = func_kwargs
            dispatcher_per_group[key] = dispatcher

        # Batching is preferred when async/broker based dispatcher are used.
        # Can be helpful for low resource environments or
        # when there are many cache invalidations.
        self._dispatch_batch_groups(
            instance,
            batch_groups,
            signal_type=signal_type,
            batch_kwargs_per_group=batch_kwargs_per_group,
            dispatcher_per_group=dispatcher_per_group,
        )

    def _dispatch_batch_groups(
        self,
        instance: models.Model,
        batch_groups: dict[tuple, list[int]],
        signal_type: SignalTypes,
        batch_kwargs_per_group: dict[tuple, dict[str, dict[str, Any]]],
        dispatcher_per_group: dict[tuple, Dispatcher],
    ):
        for key, ids in batch_groups.items():
            dispatcher_per_group[key].dispatch(
                model_label=instance._meta.label,
                pk=instance.pk,
                rule_ids=ids,
                signal_type=signal_type,
                rule_kwargs=batch_kwargs_per_group.get(key, {}),
            )

    def run_cache_rules(
        self,
        *,
        rule_ids: list[int],
        rule_kwargs: dict[str, dict[str, Any]] | None = None,
    ):
        """Run the invalidation work for rule_ids, returning a coroutine when any rule's wrapper is async."""
        rule_kwargs = rule_kwargs or {}
        pending: list = []

        for rule_id in rule_ids:
            rule = self.get_rule(rule_id)
            if not rule:
                continue

            func_kwargs = rule_kwargs.get(str(rule_id))
            if func_kwargs is None:
                continue

            result = self.process_rule(rule=rule, func_kwargs=func_kwargs)
            if inspect.isawaitable(result):
                pending.append(result)

        if pending:
            return self.await_pending(pending)
        return None

    async def await_pending(self, pending):
        for awaitable in pending:
            await awaitable

    def _extract_kwargs(
        self, instance: models.Model, field_mapping: dict[str, str]
    ) -> dict[str, Any]:
        kwargs = {}
        for arg_name, field_path in field_mapping.items():
            kwargs[arg_name] = self._get_field_value(instance, field_path)
        return kwargs

    @staticmethod
    def _get_field_value(instance, field_path: str):
        value = instance
        for part in field_path.split("."):
            if value is None:
                return None
            try:
                value = getattr(value, part, None)
            except Exception:  # pragma: no cover
                value = None  # pragma: no cover

        return value

    def _disconnect_all_signals(self):
        for model in self._connected_models:
            post_save.disconnect(self._on_save, sender=model)
            post_delete.disconnect(self._on_delete, sender=model)

    @property
    def is_discovered(self) -> bool:
        """True once auto_discover has finished walking installed apps."""
        return self._discovered

    @property
    def pending_count(self) -> int:
        """Number of registrations queued before the first auto_discover."""
        return len(self._pending)

    @property
    def model_count(self) -> int:
        """Number of distinct Django models with at least one registered rule."""
        return len(self._model_rule_ids)

    def get_status(self) -> dict:
        """Return a snapshot of the registry, useful for observability or debugging."""
        status = {
            "name": self.name,
            "discovered": self._discovered,
            "pending": len(self._pending),
            "models": {},
        }
        for model, regs in self._model_rule_ids.items():
            status["models"][model.__name__] = []
            for rule_id in regs:
                rule = self.get_rule(rule_id)
                if not rule:  # pragma: no cover
                    continue  # pragma: no cover
                status["models"][model.__name__].append(
                    {
                        "function": (
                            f"{rule['func'].__module__}."
                            f"{rule['func'].__name__}"
                        ),
                        "id": rule["id"],
                    }
                )
        return status

    def clear(self):
        """Disconnect every connected signal and drop all registered and queued rules."""
        self._disconnect_all_signals()
        self._pending.clear()
        self._model_rule_ids.clear()
        self._rules.clear()
        self._connected_models.clear()
        self._discovered = False


#: Process-wide :class:`CacheRegistry` singleton. The canonical
#: reference, direct :class:`CacheRegistry` construction is reserved
#: for internal use.
CacheRegister = CacheRegistry()
