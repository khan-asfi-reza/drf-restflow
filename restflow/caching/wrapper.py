import datetime
import inspect
from collections.abc import Callable
from contextlib import suppress
from functools import partial, wraps
from typing import Any, Generic, ParamSpec, TypeVar

from django.core.cache import cache
from django.utils import timezone

from restflow.caching.constants import (
    CACHE_MISSING,
    CACHED_DATA_METADATA_KEY,
    CACHED_DATA_VALUE_KEY,
    METADATA_CACHE_STATUS,
    METADATA_CACHED_AT_KEY,
    METADATA_RESET_AT_KEY,
    CacheStatus,
)
from restflow.caching.key_constructor import (
    DefaultKeyConstructor,
    InlineKeyConstructor,
    KeyConstructor,
)
from restflow.caching.registry import CacheRegister
from restflow.caching.rules import InvalidationRule

P = ParamSpec("P")
T = TypeVar("T")


class CachedWrapper(Generic[P, T]):
    """
    Callable wrapper that caches a function's return value in the Django cache.

    Produced by applying cache_result to a function. Calling the wrapper
    behaves like calling the original function, with results looked up
    in and stored in the Django cache. When the wrapped function is
    async, every cache I/O runs through Django's async cache API and
    the call returns a coroutine.
    """

    is_cached_function: bool = True

    def __init__(
        self,
        func: Callable[P, T],
        key_constructor: (
            "KeyConstructor | dict[str, Any] | type[KeyConstructor]"
        ),
        ttl: int | None,
        invalidates_on: list[InvalidationRule],
        cache_if: Callable | None = None,
        cache_unless: Callable | None = None,
    ):
        if isinstance(key_constructor, dict):
            constructor = InlineKeyConstructor(**key_constructor)()
        elif inspect.isclass(key_constructor) and issubclass(
            key_constructor, KeyConstructor
        ):
            constructor = key_constructor()
        else:
            msg = "Invalid KeyConstructor"
            raise ValueError(msg)

        self._func = func
        self._is_async = inspect.iscoroutinefunction(func)
        self._constructor = constructor
        self._ttl = ttl
        self._invalidates_on = invalidates_on
        self._cache_if = cache_if
        self._cache_unless = cache_unless
        wraps(func)(self)

        for invalidates in self._invalidates_on:
            signature = inspect.signature(func)
            needs_kwargs = bool(signature.parameters)
            has_strategy = bool(invalidates.field_mapping) or (
                invalidates.invalidator is not None
            )
            if needs_kwargs and not has_strategy:
                params = [f"`{k}`" for k in signature.parameters]
                msg = (
                    f"Invalidation rule for function with parameters "
                    f"{','.join(params)} must declare either "
                    f"`field_mapping=` or `invalidator=`."
                )
                raise ValueError(msg)
            CacheRegister.add(
                model=invalidates.model,
                func=self,
                invalidation_rule=invalidates,
            )

    @property
    def key_constructor(self):
        """Return the KeyConstructor instance used to build cache keys for this wrapper."""
        return self._constructor

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return partial(self, instance)

    def _refuse_if_async(self, async_method_name):
        if self._is_async:
            msg = (
                f"{self.__name__!r} is async, use {async_method_name} "
                f"instead of the sync method."
            )
            raise TypeError(msg)

    def _refuse_if_sync_predicate_returns_coroutine(self, value):
        if inspect.isawaitable(value):
            close = getattr(value, "close", None)
            if close is not None:
                close()
            msg = (
                f"async predicate detected on sync-wrapped function "
                f"{self.__name__!r}. Make the wrapped function async or "
                f"use a sync predicate."
            )
            raise TypeError(msg)
        return value

    def cache_get_with_metadata(self, key):
        """Look up key in the cache and return (value, metadata) on hit, or (CACHE_MISSING, None) on miss."""
        data = cache.get(
            key, version=self.get_key_version(), default=CACHE_MISSING
        )
        return self._unpack_cache_payload(data)

    async def acache_get_with_metadata(self, key):
        """Async variant of cache_get_with_metadata using cache.aget."""
        data = await cache.aget(
            key, version=self.get_key_version(), default=CACHE_MISSING
        )
        return self._unpack_cache_payload(data)

    def _unpack_cache_payload(self, data):
        if data and isinstance(data, dict) and CACHED_DATA_VALUE_KEY in data:
            result = data[CACHED_DATA_VALUE_KEY]
            metadata = data.get(CACHED_DATA_METADATA_KEY) or {}
            metadata[METADATA_CACHE_STATUS] = CacheStatus.HIT
            return result, metadata
        return data, None

    def _build_cache_payload(self, value, timeout):
        reset_at = None
        with suppress(Exception):
            reset_at = (
                (
                    timezone.now() + datetime.timedelta(seconds=timeout)
                ).isoformat()
                if timeout
                else None
            )
        metadata = {
            METADATA_CACHED_AT_KEY: timezone.now().isoformat(),
            METADATA_RESET_AT_KEY: reset_at,
        }
        payload = {
            CACHED_DATA_VALUE_KEY: value,
            CACHED_DATA_METADATA_KEY: metadata,
        }
        return payload, metadata

    def cache_set_with_timestamp(
        self, key, value, timeout: int | None = None, version=1
    ):
        """Write value to the cache under key with cached-at and reset-at timestamps. Returns (value, metadata)."""
        payload, metadata = self._build_cache_payload(value, timeout)
        cache.set(key, payload, timeout=timeout, version=version)
        metadata[METADATA_CACHE_STATUS] = CacheStatus.MISS
        return value, metadata

    async def acache_set_with_timestamp(
        self, key, value, timeout: int | None = None, version=1
    ):
        """Async variant of cache_set_with_timestamp using cache.aset."""
        payload, metadata = self._build_cache_payload(value, timeout)
        await cache.aset(key, payload, timeout=timeout, version=version)
        metadata[METADATA_CACHE_STATUS] = CacheStatus.MISS
        return value, metadata

    def __call__(self, *args: P.args, **kwargs: P.kwargs):
        if self._is_async:
            return self._async_call(args, kwargs, with_metadata=False, refresh=False)
        return self._sync_call(args, kwargs, with_metadata=False, refresh=False)

    def _sync_call(self, args, kwargs, *, with_metadata, refresh):
        cache_key = self.get_cache_key(*args, **kwargs)

        if not refresh:
            cached_result, metadata = self.cache_get_with_metadata(cache_key)
            if cached_result is not CACHE_MISSING:
                return (
                    (cached_result, metadata)
                    if with_metadata
                    else cached_result
                )

        result = self._func(*args, **kwargs)
        do_cache = self._evaluate_cache_predicate_sync(result)

        if do_cache:
            value, _metadata = self.cache_set_with_timestamp(
                key=cache_key,
                value=result,
                timeout=self._ttl,
                version=self.get_key_version(),
            )
        else:
            value, _metadata = result, None

        return (value, _metadata) if with_metadata else value

    async def _async_call(self, args, kwargs, *, with_metadata, refresh):
        cache_key = self.get_cache_key(*args, **kwargs)

        if not refresh:
            cached_result, metadata = await self.acache_get_with_metadata(
                cache_key
            )
            if cached_result is not CACHE_MISSING:
                return (
                    (cached_result, metadata)
                    if with_metadata
                    else cached_result
                )

        result = await self._func(*args, **kwargs)
        do_cache = await self._evaluate_cache_predicate_async(result)

        if do_cache:
            value, _metadata = await self.acache_set_with_timestamp(
                key=cache_key,
                value=result,
                timeout=self._ttl,
                version=self.get_key_version(),
            )
        else:
            value, _metadata = result, None

        return (value, _metadata) if with_metadata else value

    def _evaluate_cache_predicate_sync(self, result):
        if self._cache_if is not None:
            out = self._refuse_if_sync_predicate_returns_coroutine(
                self._cache_if(result)
            )
            return bool(out)
        if self._cache_unless is not None:
            out = self._refuse_if_sync_predicate_returns_coroutine(
                self._cache_unless(result)
            )
            return not bool(out)
        return True

    async def _evaluate_cache_predicate_async(self, result):
        if self._cache_if is not None:
            out = self._cache_if(result)
            if inspect.isawaitable(out):
                out = await out
            return bool(out)
        if self._cache_unless is not None:
            out = self._cache_unless(result)
            if inspect.isawaitable(out):
                out = await out
            return not bool(out)
        return True

    def get_key_version(self) -> int:
        """Return the cache version number from the key constructor. Bumping it invalidates every entry."""
        return self._constructor.get_version()

    def get_with_metadata(self, *args: P.args, **kwargs: P.kwargs):
        """Run the call and return (value, metadata) so callers can read cache status and timestamps."""
        self._refuse_if_async("aget_with_metadata")
        return self._sync_call(args, kwargs, with_metadata=True, refresh=False)

    async def aget_with_metadata(self, *args: P.args, **kwargs: P.kwargs):
        """Async variant of get_with_metadata."""
        return await self._async_call(
            args, kwargs, with_metadata=True, refresh=False
        )

    def get_cache_key(self, *args: P.args, **kwargs: P.kwargs) -> str:
        """Return the cache key the wrapper would use for these call arguments."""
        return self._constructor.generate_key(self._func, args, kwargs)

    def get_cache_only(self, *args: P.args, **kwargs: P.kwargs):
        """Return the cached value without running the function. Returns CACHE_MISSING on miss."""
        self._refuse_if_async("aget_cache_only")
        cache_key = self.get_cache_key(*args, **kwargs)
        return self.cache_get_with_metadata(cache_key)[0]

    async def aget_cache_only(self, *args: P.args, **kwargs: P.kwargs):
        """Async variant of get_cache_only."""
        cache_key = self.get_cache_key(*args, **kwargs)
        result, _ = await self.acache_get_with_metadata(cache_key)
        return result

    def refresh(self, *args: P.args, **kwargs: P.kwargs):
        """Run the function again and overwrite the cache entry for these call arguments."""
        self._refuse_if_async("arefresh")
        return self._sync_call(args, kwargs, with_metadata=False, refresh=True)

    async def arefresh(self, *args: P.args, **kwargs: P.kwargs):
        """Async variant of refresh."""
        return await self._async_call(
            args, kwargs, with_metadata=False, refresh=True
        )

    def get_cached_metadata(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> dict | None:
        """Return the metadata dict for the cached call, or None if there is no cache entry yet."""
        self._refuse_if_async("aget_cached_metadata")
        cache_key = self.get_cache_key(*args, **kwargs)
        return self.cache_get_with_metadata(cache_key)[1]

    async def aget_cached_metadata(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> dict | None:
        """Async variant of get_cached_metadata."""
        cache_key = self.get_cache_key(*args, **kwargs)
        _, metadata = await self.acache_get_with_metadata(cache_key)
        return metadata

    def delete_cache(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """Drop the cache entry for these specific call arguments."""
        self._refuse_if_async("adelete_cache")
        cache_key = self.get_cache_key(*args, **kwargs)
        cache.delete(cache_key)

    async def adelete_cache(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """Async variant of delete_cache."""
        cache_key = self.get_cache_key(*args, **kwargs)
        await cache.adelete(cache_key)

    def _delete_prefix(self, cache_prefix: str):
        """Wipe every cache entry whose key starts with `cache_prefix` (uses the backend's `delete_pattern`).

        Raises:
            NotImplementedError: When the configured Django cache backend
                doesn't support pattern deletes (Django's local-memory
                cache, for example). Use django-redis or another backend
                that exposes `delete_pattern`.
        """
        delete_pattern = getattr(cache, "delete_pattern", None)
        if delete_pattern is None:
            raise NotImplementedError(self._delete_pattern_unsupported_msg())
        return delete_pattern(f"{cache_prefix}*")

    async def _adelete_prefix(self, cache_prefix: str):
        """Async variant of _delete_prefix that falls back to the sync delete_pattern when no async one exists."""
        adelete_pattern = getattr(cache, "adelete_pattern", None)
        if adelete_pattern is not None:
            return await adelete_pattern(f"{cache_prefix}*")
        delete_pattern = getattr(cache, "delete_pattern", None)
        if delete_pattern is None:
            raise NotImplementedError(self._delete_pattern_unsupported_msg())
        return delete_pattern(f"{cache_prefix}*")

    def _delete_pattern_unsupported_msg(self):
        return (
            f"Cache backend {cache.__class__.__name__!r} does not "
            "support delete_pattern. Install django-redis (or another "
            "backend that exposes delete_pattern) to use "
            "delete_by_prefix() / invalidate_all()."
        )

    def delete_by_prefix(self, *args: P.args, **kwargs: P.kwargs):
        """Wipe every cache entry that shares the partition prefix derived from these call arguments."""
        self._refuse_if_async("adelete_by_prefix")
        if (
            getattr(cache, "delete_pattern", None) is None
            and self._constructor.has_only_partition_fields
        ):
            return self.delete_cache(*args, **kwargs)
        cache_prefix = self._constructor.build_key_prefix(
            self._func, args, kwargs
        )
        return self._delete_prefix(cache_prefix)

    async def adelete_by_prefix(self, *args: P.args, **kwargs: P.kwargs):
        """Async variant of delete_by_prefix."""
        no_async_pattern = getattr(cache, "adelete_pattern", None) is None
        no_sync_pattern = getattr(cache, "delete_pattern", None) is None
        if (
            no_async_pattern
            and no_sync_pattern
            and self._constructor.has_only_partition_fields
        ):
            return await self.adelete_cache(*args, **kwargs)
        cache_prefix = self._constructor.build_key_prefix(
            self._func, args, kwargs
        )
        return await self._adelete_prefix(cache_prefix)

    def bypass_cache(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Call the wrapped function directly, skipping both cache reads and cache writes."""
        self._refuse_if_async("abypass_cache")
        return self._func(*args, **kwargs)

    async def abypass_cache(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Async variant of bypass_cache."""
        return await self._func(*args, **kwargs)

    def invalidate_all(self):
        """Drop every cache entry this wrapper has ever written, across every set of call arguments."""
        self._refuse_if_async("ainvalidate_all")
        cache_prefix = self._constructor.build_key_prefix(
            self._func, args=None, kwargs=None
        )
        return self._delete_prefix(cache_prefix)

    async def ainvalidate_all(self):
        """Async variant of invalidate_all."""
        cache_prefix = self._constructor.build_key_prefix(
            self._func, args=None, kwargs=None
        )
        return await self._adelete_prefix(cache_prefix)


def cache_result(
    key_constructor: (
        "KeyConstructor | dict[str, Any] | type[KeyConstructor]"
    ) = DefaultKeyConstructor,
    ttl: int | None = 3600,
    invalidates_on: list["InvalidationRule"] | None = None,
    cache_if: Callable | None = None,
    cache_unless: Callable | None = None,
):
    """
    Cache a function's return value, with optional invalidation triggered by Django model signals.

    Works for sync and async targets. Returns a decorator that replaces
    the target function with a CachedWrapper.

    Example:
        ::

            @cache_result(
                key_constructor=UserKeyConstructor,
                ttl=300,
                invalidates_on=[
                    InvalidationRule(
                        model=User,
                        field_mapping={"user_id": "id"},
                        rewarm=True,
                    )
                ],
            )
            def get_user_data(user_id: int) -> dict:
                return expensive_computation(user_id)
    """
    invalidates_on = invalidates_on or []

    def decorator(func):
        return CachedWrapper(
            func=func,
            key_constructor=key_constructor,
            invalidates_on=invalidates_on,
            cache_if=cache_if,
            cache_unless=cache_unless,
            ttl=ttl,
        )

    return decorator


def set_response_cache_header(response, metadata):
    """Attach cache metadata as X-Cached-at, X-Cache-reset-at, and X-Cache-status headers on a DRF response."""
    if not metadata:
        return response
    cached_at = metadata.get(METADATA_CACHED_AT_KEY)
    reset_at = metadata.get(METADATA_RESET_AT_KEY)
    status = metadata.get(METADATA_CACHE_STATUS)
    if cached_at:
        response["X-Cached-at"] = cached_at
    if reset_at:
        response["X-Cache-reset-at"] = reset_at
    if status:
        response["X-Cache-status"] = str(status)
    return response
