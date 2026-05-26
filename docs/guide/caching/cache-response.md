# cache_response

`@cache_response` caches the rendered HTTP output of a view method or
function-based view. Use it when the whole response payload is safe to
cache as raw bytes, the view body and serializer work is the slow part,
and the view does not need per-call side effects.

`@cache_result` caches the return value of a function. `@cache_response`
caches the rendered HTTP response (content, status code, headers). On a
hit it rebuilds a plain `HttpResponse` and skips the view body, the
serializer, and the renderer entirely.

## Basic usage

```python
from rest_framework.response import Response
from rest_framework.views import APIView
from restflow.caching import cache_response


class TimelineView(APIView):
    @cache_response(ttl=60)
    def get(self, request):
        return Response({"items": expensive_lookup()})
```

The default key constructor builds a key from the request's query
parameters and the view's URL kwargs. Subsequent requests with the same
query string and URL kwargs return the cached response without running
`get` again.

## Parameters

| Parameter | Type | Default | Effect |
| --- | --- | --- | --- |
| `key_constructor` | `KeyConstructor` subclass, instance, or dict of fields | `ResponseCacheKeyConstructor` | How cache keys are built. |
| `ttl` | `int \| None` | `3600` | Time-to-live in seconds. `None` means no expiration. |
| `invalidates_on` | `list[InvalidationRule]` | `None` | Rules that fire on Django model signals to invalidate the cache. |
| `cache_if` | `Callable` | `None` | Predicate on the response. The response is cached only when this returns truthy. |
| `cache_unless` | `Callable` | `None` | Predicate on the response. The response is skipped (not cached) when this returns truthy. |
| `set_cache_headers` | `bool` | `False` | When `True`, attach `X-Cached-at`, `X-Cache-reset-at`, and `X-Cache-status` headers to every returned response. |

`cache_if` and `cache_unless` are mutually exclusive on a single
decorator.

## Default key constructor

`ResponseCacheKeyConstructor` ships with two fields:

```python
class ResponseCacheKeyConstructor(KeyConstructor):
    query_params = QueryParamsKeyField("*", hash_value=True)
    path_params = ViewKwargsKeyField("*", partition=True)
```

`query_params` hashes the full query string. `path_params` captures the
view method's URL kwargs (everything except `self` and `request`) and
marks them as the partition so a single instance's cache can be wiped as
a group.

Subclass to add a user partition, narrow the captured fields, or layer
extra fields on top.

```python
from restflow.caching import (
    ResponseCacheKeyConstructor, ArgsKeyField, RequestValueKeyField,
)


class UserTimelineKey(ResponseCacheKeyConstructor):
    user = RequestValueKeyField("user.id", partition=True)

    class Meta:
        version = 1
        namespace = "UserTimeline"
```

## Function-based views

`@cache_response` works on DRF's `@api_view` decorator. Apply
`@cache_response` closest to the function so it wraps the original
callable before `@api_view` turns it into a class-based view.

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from restflow.caching import cache_response


@api_view(["GET"])
@cache_response(ttl=60)
def timeline(request):
    return Response({"items": expensive_lookup()})
```

The view's `accepted_renderer` is read from the DRF parser context, so
the cached response renders the same way as a normal `@api_view` call.

!!! note "Sync-only function-based views"
    DRF's `@api_view` decorator dispatches synchronously. Async
    functions wrapped in `@api_view` return coroutines that DRF cannot
    await. For async function-based caching, use restflow's
    `AsyncAPIView` and put `@cache_response` on the method.

## Async views

`@cache_response` detects an async view method at decoration time and
routes every cache I/O through Django's async cache API.

```python
from restflow.responses import Response
from restflow.views import AsyncAPIView
from restflow.caching import cache_response


class UserMeView(AsyncAPIView):
    @cache_response(ttl=60)
    async def get(self, request):
        return Response(await fetch_user_payload(request.user.id))
```

When the wrapped method returns a `restflow.responses.Response`,
restflow renders it through `arender` so the cache write stays on the
event loop. DRF's `Response` falls back to sync render.

## Invalidating on model changes

Pair `@cache_response` with `InvalidationRule` the same way as
`@cache_result`. When the model signal fires, the rule maps fields from
the saved instance into the function's kwargs and wipes the matching
cache entries.

```python
from restflow.caching import (
    KeyConstructor, ArgsKeyField, cache_response, InvalidationRule,
)


class UserKey(KeyConstructor):
    pk = ArgsKeyField("pk", partition=True)

    class Meta:
        namespace = "UserDetail"


class UserView(APIView):
    @cache_response(
        key_constructor=UserKey,
        ttl=300,
        invalidates_on=[
            InvalidationRule(
                model=User,
                field_mapping={"pk": "pk"},
                watch_fields=["username", "email"],
            ),
        ],
    )
    def get(self, request, pk=None):
        user = User.objects.get(pk=pk)
        return Response(UserSerializer(user).data)
```

A key constructor used for invalidation should rely only on values
reachable from the model instance through `field_mapping`. The signal
handler never has the original request, so `QueryParamsKeyField` and
`RequestValueKeyField` resolve to empty during invalidation. For
partition wipes (`delete_by_prefix`), put the model-derived fields in
the partition and they will match every cached variant.

!!! warning "Rewarm is not supported for view-method caches"
    `InvalidationRule(rewarm=True)` recalls the wrapped function with
    the kwargs built from `field_mapping`. View methods have a
    `(self, request, ...)` signature that the signal handler cannot
    reconstruct, so rewarming a `@cache_response`-decorated method
    will always fail to bind and fall back to deletion. Stick to the
    default `rewarm=False` and let the next request rebuild the
    response. See
    [Invalidation Rules > Refresh instead of delete](invalidation.md#refresh-instead-of-delete)
    for the same constraint applied to plain `@cache_result`.

## Conditional caching

`cache_if` and `cache_unless` evaluate against the rendered response.
Skip caching for errors or empty payloads.

```python
class V(APIView):
    @cache_response(
        ttl=60,
        cache_if=lambda response: response.status_code < 400,
    )
    def get(self, request):
        return Response({"ok": True})
```

For async views, both predicates may be `async def`.

## Surfacing cache status to the client

Pass `set_cache_headers=True` to attach the cache metadata as response
headers on every call. Clients and monitoring can then tell hits from
misses without a separate lookup.

```python
class V(APIView):
    @cache_response(ttl=60, set_cache_headers=True)
    def get(self, request):
        return Response({"v": 1})
```

| Header | Value |
| --- | --- |
| `X-Cache-status` | `HIT`, `MISS`, `STALE`, `BYPASS`, or `REFRESH`. |
| `X-Cached-at` | ISO timestamp recorded when the value was written. |
| `X-Cache-reset-at` | ISO timestamp when the entry will expire, when a TTL is set. |

## Wrapper methods

The decorated method becomes a `CachedResponseWrapper`. It inherits
every method on `CachedWrapper`, so the management surface is the same
as `@cache_result`:

```python
view = MyView()
request = factory.get("/items/", QUERY_STRING="q=python")

# Inspect or manipulate the cached response without going through dispatch.
MyView.get.bypass_cache(view, request)
MyView.get.delete_cache(view, request)
MyView.get.refresh(view, request)
```

See the [cache_result guide](cache-result.md#wrapper-attributes) for the
full method surface and async variants.


For per-user caching, partition the cache by `request.user.id` so each
user gets a separate cache namespace.
