# cache_result

`@cache_result` wraps a function so calls hit the Django cache before
running the function. The decorated function becomes a `CachedWrapper`
with extra methods for inspecting and managing the cache.

## Basic usage

```python
from restflow.caching import cache_result, KeyConstructor, ArgsKeyField


class UserPayloadKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)


@cache_result(key_constructor=UserPayloadKey, ttl=300)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)
```

## Parameters

| Parameter | Type | Default | Effect |
| --- | --- | --- | --- |
| `key_constructor` | `KeyConstructor` subclass, instance, or dict of fields | `DefaultKeyConstructor` | How cache keys are built. A dict goes through `InlineKeyConstructor`. |
| `ttl` | `int \| None` | `3600` | Time-to-live in seconds. `None` means no expiration. |
| `invalidates_on` | `list[InvalidationRule]` | `None` | Rules that fire on Django model signals to invalidate the cache. |
| `cache_if` | `Callable` | `None` | Predicate on the function's result. The result is cached only when this returns truthy. |
| `cache_unless` | `Callable` | `None` | Predicate on the function's result. The result is skipped (not cached) when this returns truthy. |

`cache_if` and `cache_unless` are mutually exclusive on a single
decorator.

## Wrapper attributes

```python
@cache_result(key_constructor=UserPayloadKey, ttl=300)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)
```

After decoration, `get_user_payload` is a `CachedWrapper`. Calling it
behaves like calling the original function: a hit returns the cached
value; a miss runs the function, stores the result, and returns it.

The wrapper also has these methods.

### Normal call

```python
value = get_user_payload(42)
```

Reads from the cache; on a miss, runs the function, stores the
result, and returns it.

### get_with_metadata

```python
value, metadata = get_user_payload.get_with_metadata(42)
print(metadata["cache_status"])
```

Returns `(value, metadata)`. The metadata dict carries cache status
and timestamps. The status is one of `HIT`, `MISS`, `STALE`,
`BYPASS`, or `REFRESH`. See the
[Response Headers guide](response-headers.md) for surfacing this on
DRF responses.

### get_cache_only

```python
from restflow.caching import CACHE_MISSING

cached = get_user_payload.get_cache_only(42)
if cached is not CACHE_MISSING:
    print(cached)
```

Returns the cached value without running the function. On a miss,
returns the `CACHE_MISSING` sentinel. Use `is CACHE_MISSING` rather
than `== None` to distinguish a real miss from a cached `None` value.

### refresh

```python
value = get_user_payload.refresh(42)
```

Runs the function and overwrites the cache entry for these arguments.
The metadata reports `REFRESH`.

### bypass_cache

```python
value = get_user_payload.bypass_cache(42)
```

Calls the wrapped function directly, skipping both cache reads and
cache writes.

### delete_cache

```python
get_user_payload.delete_cache(42)
```

Drops the cache entry for the exact arguments. Works on any cache
backend.

### delete_by_prefix

```python
get_user_payload.delete_by_prefix(user_id=42)
```

Wipes every cache entry that shares the partition prefix derived from
the given arguments. Useful when one logical change should drop many
cache entries, for example dropping every cached page for a user.

!!! warning "Cache backend requirement"
    `delete_by_prefix()` uses `delete_pattern`, which Django's
    local-memory and database cache backends do not implement. A
    redis-compatible backend (django-redis, valkey, keydb, dragonfly)
    is required to call this method. Without one, the call raises.

### invalidate_all

```python
get_user_payload.invalidate_all()
```

Drops every cache entry the wrapper has ever written, across every
set of call arguments. Same backend requirement as
`delete_by_prefix()`.

### get_cache_key

```python
key = get_user_payload.get_cache_key(42)
```

Returns the cache key the wrapper would use for the given arguments,
without touching the cache.

### get_cached_metadata

```python
metadata = get_user_payload.get_cached_metadata(42)
```

Returns the metadata dict for the cached call, or `None` if there is
no cache entry yet. Does not run the wrapped function.

## cache_if and cache_unless

Filter what gets stored based on the result. Both predicates receive
the function's return value.

```python
from restflow.caching import cache_result


@cache_result(
    ttl=60,
    cache_if=lambda result: result is not None,
)
def get_user_or_none(user_id: int):
    return User.objects.filter(pk=user_id).first()
```

`cache_unless` is the inverse:

```python
@cache_result(
    ttl=60,
    cache_unless=lambda result: result == [],
)
def search(query: str):
    return list(Search.run(query))
```

## Putting it all together

```python
from django.contrib.auth import get_user_model
from restflow.caching import (
    cache_result, KeyConstructor, ArgsKeyField, ConstantKeyField,
    InvalidationRule,
)

User = get_user_model()


class UserPayloadKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    version = ConstantKeyField("v", "1")

    class Meta:
        namespace = "users"


@cache_result(
    key_constructor=UserPayloadKey,
    ttl=300,
    invalidates_on=[
        InvalidationRule(
            model=User,
            field_mapping={"user_id": "id"},
            watch_fields=["email", "username"],
            rewarm=True,
        ),
    ],
    cache_if=lambda result: bool(result),
)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)
```

## Async support

`@cache_result` works on `async def` targets. Restflow detects the
coroutine function at decoration time and drives every cache I/O
through Django's async cache API (`cache.aget`, `cache.aset`,
`cache.adelete`).

```python
@cache_result(key_constructor=UserPayloadKey, ttl=300)
async def get_user_payload(user_id: int):
    return await fetch_payload(user_id)


value = await get_user_payload(42)
```

Calling the wrapper returns a coroutine. Awaiting it returns the
cached value on a hit, or runs the function and caches the result on
a miss.

### Async wrapper methods

When the wrapped function is async, the `a`-prefixed methods
manipulate the cache from async contexts. Each one mirrors its sync
counterpart:

| Sync | Async |
| --- | --- |
| `wrapper(...)` | `await wrapper(...)` |
| `get_with_metadata(...)` | `await aget_with_metadata(...)` |
| `get_cache_only(...)` | `await aget_cache_only(...)` |
| `get_cached_metadata(...)` | `await aget_cached_metadata(...)` |
| `refresh(...)` | `await arefresh(...)` |
| `bypass_cache(...)` | `await abypass_cache(...)` |
| `delete_cache(...)` | `await adelete_cache(...)` |
| `delete_by_prefix(...)` | `await adelete_by_prefix(...)` |
| `invalidate_all()` | `await ainvalidate_all()` |

```python
value, metadata = await get_user_payload.aget_with_metadata(42)
await get_user_payload.arefresh(42)
await get_user_payload.adelete_cache(42)
await get_user_payload.adelete_by_prefix(user_id=42)
```

The sync-named methods raise `TypeError` when called on an
async-wrapped function, pointing at the async-prefixed alternative.

### Async predicates

`cache_if` and `cache_unless` may be `async def` when the wrapped
function is async.

```python
async def has_payload(result):
    return result is not None


@cache_result(
    key_constructor=UserPayloadKey,
    ttl=300,
    cache_if=has_payload,
)
async def get_user_payload(user_id: int):
    return await fetch_payload(user_id)
```

### Async invalidators

`InvalidationRule(invalidator=...)` accepts an `async def` callable
too. Restflow handles bridging across every dispatcher, so a sync
broker (Celery, Django-Q, etc.) drives async invalidators via
`asgiref.sync.async_to_sync` while the asyncio dispatcher awaits
them natively on the running loop.

```python
async def invalidate_user(wrapper, instance, **_extras):
    await wrapper.adelete_by_prefix(user_id=instance.id)


@cache_result(
    key_constructor=UserPayloadKey,
    ttl=300,
    invalidates_on=[
        InvalidationRule(model=User, invalidator=invalidate_user),
    ],
)
async def get_user_payload(user_id: int):
    return await fetch_payload(user_id)
```

### Choosing a dispatcher

The asyncio dispatcher (`InvalidationRule(dispatcher="asyncio")`)
applies when invalidation is triggered from an async view or any
context with a running event loop. It schedules `arun_cache_rules`
directly on the loop, avoiding both a thread hop and a fresh event
loop spin per call. Other dispatchers still work with async-wrapped
functions; they bridge the async work via
`asgiref.sync.async_to_sync` inside the registry.

## Where to next

- [Key Constructors](key-constructors.md) for the cache key surface.
- [Invalidation Rules](invalidation.md) for the rule shape that
  `invalidates_on=` accepts.
- [Response Headers](response-headers.md) for surfacing cache status
  on DRF responses.
