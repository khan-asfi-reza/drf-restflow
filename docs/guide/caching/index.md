# Caching Overview

The caching subsystem is a declarative layer on top of Django's cache
framework. It models three things separately: how a cache key is
built, when a cached value is invalidated, and where invalidation work
runs.

## Cache backend

The caching layer plugs into Django's cache framework and works with
any configured backend.

!!! note "Cache backend recommendation"
    A small set of features only works on a redis-compatible backend:
    `delete_by_prefix()`, `invalidate_all()`, and any
    `InvalidationRule` that needs to wipe a partition rather than a
    single key. Without a redis-compatible backend, those calls
    raise; the rest of the caching API still works on Django's
    local-memory or database cache.

```bash
pip install drf-restflow[redis]
```

```python
# settings.py
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}
```

## Caching

A cached function in Restflow is a `CachedWrapper` built by the
`@cache_result` decorator. The wrapper has three pieces:

1. **A cache key.** Built by a `KeyConstructor`, which is a
   declarative class whose attributes are key fields. Each field
   contributes a deterministic string slice to the final key. Some
   fields are marked as part of the key prefix (a partition); others
   contribute to the suffix.
2. **A TTL.** A timeout in seconds. `None` means no expiration.
3. **A list of invalidation rules.** Each rule is an
   `InvalidationRule` that hooks into a Django model's `post_save`
   and `post_delete` signals. When the rule fires, the wrapper drops
   or refreshes the relevant cache entries.

```python
from restflow.caching import (
    KeyConstructor, ArgsKeyField, ConstantKeyField,
    cache_result, InvalidationRule,
)


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
        ),
    ],
)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)
```

## Picking a dispatcher

Each `InvalidationRule` decides where its work runs through the
`dispatcher` attribute. The default is `inline`, which runs the work
synchronously inside `transaction.on_commit`.

| Dispatcher | Use when |
| --- | --- |
| `inline` (default) | Invalidation is fast and extra moving parts are not wanted. |
| `threadpool` | Invalidation is slower than the request can afford, but a task broker is not wanted. Loses work on process exit. |
| `asyncio` | Async views and async signal handlers. Falls back to inline when no event loop is running. |
| `celery` | The project already runs celery; cache work needs retries, dead-lettering, or fan-out. |
| `django_rq` | Redis-backed queue without celery's broker abstraction. |
| `django_q` | Django-native queue with built-in scheduling. |
| `dramatiq` | The project already runs dramatiq, or its actor-based middleware is preferred. |

See the [Dispatchers guide](dispatchers.md) for the per-broker setup.

## Caching API

| Topic | Page |
| --- | --- |
| Building cache keys declaratively | [Key Constructors](key-constructors.md) |
| The `@cache_result` decorator and `CachedWrapper` methods | [cache_result](cache-result.md) |
| Connecting model signals to cache invalidation | [Invalidation Rules](invalidation.md) |
| Choosing where invalidation runs | [Dispatchers](dispatchers.md) |
| Reporting cache status to the client | [Response Headers](response-headers.md) |
| Tuning defaults globally | [Settings](../settings.md) |

## Where to next

- [Caching API reference](../../api/caching/cache-result.md) for the
  generated reference of every public symbol.
