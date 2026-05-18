# Throttling

Restflow ships async-aware throttle classes that mirror DRF's
throttling API. The throttling logic itself is reused from DRF; the
value-add is an async cache path so rate-limit checks do not block the
event loop on async views.

Throttles run after authentication and permissions and before the view
handler. Each throttle returns True to allow the request or False to
deny it. When any throttle denies, the dispatcher computes the longest
wait time across all denying throttles and raises Throttled, which DRF
turns into a 429 response with a Retry-After header.

The async dispatch in AsyncAPIView.acheck_throttles picks the async hook
when present and falls back to sync_to_async for legacy throttles. This
keeps DRF-style sync throttles working in async views while the
restflow-provided classes use the non-blocking async cache path.

```python
from restflow.throttling import AnonRateThrottle, UserRateThrottle
from restflow.views import AsyncAPIView


class ArticleView(AsyncAPIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    async def get(self, request):
        return self.respond({"ok": True})
```

The same throttle classes also work on sync DRF views; the sync
allow_request path is inherited from DRF.

## Async hooks

Every throttle in restflow.throttling exposes:

```python
async def aallow_request(self, request, view) -> bool: ...
```

The contract:

- Returns True to allow the request.
- Returns False to deny it.
- On denial, wait() returns the time in seconds until retry is allowed.

The async dispatch path collects wait times for all denying throttles
and raises Throttled with the maximum delay so the client retries no
sooner than the longest active limit allows.

```python
from restflow.throttling import BaseThrottle


class MaintenanceThrottle(BaseThrottle):
    async def aallow_request(self, request, view):
        return not maintenance_window_active()

    def wait(self):
        return 60
```

BaseThrottle's default aallow_request runs the sync allow_request in a
worker thread through sync_to_async. Subclassing BaseThrottle and
overriding aallow_request directly lets a throttle stay fully on the
event loop.

## SimpleRateThrottle

SimpleRateThrottle stores a list of recent request timestamps in
Django's cache, keyed per client. The async path uses cache.aget and
cache.aset so the rate-limit check does not block the event loop.

```python
from restflow.throttling import SimpleRateThrottle


class TenantRateThrottle(SimpleRateThrottle):
    scope = "tenant"

    def get_cache_key(self, request, view):
        tenant_id = getattr(request.user, "tenant_id", None)
        if tenant_id is None:
            return None
        return self.cache_format.format(scope=self.scope, ident=tenant_id)
```

Configuration points:

- scope is the lookup key into REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].
- get_cache_key(request, view) returns the cache key. Returning None
  skips the throttle for that request.
- cache_format defaults to "throttle_{scope}_{ident}".
- cache defaults to Django's default cache. Override to point at a
  different cache alias.

## AnonRateThrottle

Limits anonymous requests by client IP. The default scope is "anon" and
the cache key is built from get_ident(request). Authenticated requests
skip this throttle entirely, so anonymous and authenticated quotas can
coexist on the same view.

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
    },
}
```

## UserRateThrottle

Limits authenticated requests by user id; falls back to client IP for
anonymous ones. The default scope is "user".

Stacking AnonRateThrottle and UserRateThrottle is a common pattern: the
anon throttle is active for unauthenticated requests, the user throttle
covers authenticated ones, and the two scopes have independent rates.

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}
```

## ScopedRateThrottle

ScopedRateThrottle reads its scope from view.throttle_scope. This lets a
single throttle class apply different rates to different views or
actions without subclassing.

```python
from restflow.throttling import ScopedRateThrottle


class UploadView(AsyncAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"


class DownloadView(AsyncAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "downloads"
```

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "uploads": "10/min",
        "downloads": "100/hour",
    },
}
```

The pattern scales to per-action scopes: assign a different
throttle_scope per action and configure differentiated rates for
expensive endpoints (heavy uploads, search, exports) versus cheap ones
(metadata reads, health checks).

## Configuration

Throttle rates are configured globally under DEFAULT_THROTTLE_RATES.
Each entry maps a scope name to a rate string of the form
"<count>/<period>", where period is one of sec, min, hour, day.

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "restflow.throttling.AnonRateThrottle",
        "restflow.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "uploads": "10/min",
        "downloads": "100/hour",
    },
}
```

Throttle classes apply on a view by setting throttle_classes; a view
opts out of the project-wide defaults with throttle_classes = [].

## Per-action throttling

AsyncModelViewSet supports per-action overrides through ActionConfig.
The throttle_classes field on ActionConfig replaces the class-level
throttle_classes for that action.

```python
from restflow.throttling import ScopedRateThrottle, UserRateThrottle
from restflow.views import ActionConfig, AsyncModelViewSet


class ArticleViewSet(AsyncModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    throttle_classes = [UserRateThrottle]

    action_configs = {
        "list": ActionConfig(throttle_classes=[ScopedRateThrottle]),
        "destroy": ActionConfig(throttle_classes=[ScopedRateThrottle]),
    }

    throttle_scope = "list"

    def get_throttles(self):
        if self.action == "destroy":
            self.throttle_scope = "destroy"
        else:
            self.throttle_scope = "list"
        return super().get_throttles()
```

For a custom @action, set throttle_scope through the decorator's kwargs
so ScopedRateThrottle picks up the correct rate:

```python
from rest_framework.decorators import action


class ReportViewSet(AsyncModelViewSet):
    throttle_classes = [ScopedRateThrottle]

    @action(detail=False, methods=["post"], throttle_scope="exports")
    async def export(self, request):
        return self.respond({"ok": True})
```

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "list": "1000/hour",
        "destroy": "20/hour",
        "exports": "5/min",
    },
}
```

## Cache backend

Throttle keys live in the configured Django cache. The choice of cache
backend determines correctness across processes:

- For multi-process deployments (gunicorn, uvicorn workers, multiple
  pods), use a shared cache such as redis or memcached. With a
  per-process cache each worker keeps its own counter and the effective
  rate becomes N times higher than configured.
- With django-redis, the async cache path is fully non-blocking. The
  throttle awaits cache.aget and cache.aset directly without ever
  hopping to a thread.
- LocMemCache works for single-process development and tests but is not
  shared between workers.

```python
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

To send throttle counters to a separate cache from the main application
cache, override SimpleRateThrottle.cache:

```python
from django.core.cache import caches


class IsolatedThrottle(SimpleRateThrottle):
    cache = caches["throttling"]
    scope = "isolated"
```

## Custom throttles

For a custom rate-limited throttle, subclass SimpleRateThrottle, set a
scope, and override get_cache_key.

```python
from restflow.throttling import SimpleRateThrottle


class ApiKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_cache_key(self, request, view):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        return self.cache_format.format(scope=self.scope, ident=api_key)
```

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "api_key": "10000/hour",
    },
}
```

For non-rate throttles such as concurrency limits, subclass BaseThrottle
and implement aallow_request directly.

```python
from restflow.throttling import BaseThrottle


class ConcurrencyThrottle(BaseThrottle):
    scope = "concurrency"

    async def aallow_request(self, request, view):
        in_flight = await count_in_flight_requests(request.user)
        return in_flight < 5

    def wait(self):
        return 1
```

Returning a wait value from wait() lets the dispatcher build a useful
Retry-After header for clients that respect it.

## Headers and 429 responses

When any throttle denies, restflow's dispatcher raises Throttled. DRF's
exception handler turns this into:

- A 429 Too Many Requests response.
- A Retry-After header set to the wait duration in seconds.
- A JSON body with a detail message that includes the wait time.

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
Content-Type: application/json

{"detail": "Request was throttled. Expected available in 42 seconds."}
```

When several throttles deny at once, the dispatcher uses the largest
wait time, so a client retrying at exactly Retry-After is guaranteed to
clear every active limit.

## Common pitfalls

### Forgetting DEFAULT_THROTTLE_RATES

A throttle whose scope is not present in DEFAULT_THROTTLE_RATES resolves
rate to None and silently allows every request. No log line is emitted,
and the rate appears to be effectively unlimited.

```python
REST_FRAMEWORK = {
    # missing "anon" entry - AnonRateThrottle becomes a no-op
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/hour",
    },
}
```

The fix is to add the scope, or remove the throttle if it is not needed.

### Per-process caches

When each worker has its own LocMemCache, every counter is local to the
process. With N workers behind a load balancer, the effective rate
becomes N times the configured rate. Use a shared cache (redis,
memcached) across all workers.

### LocMemCache in tests

LocMemCache works in tests but resets when cache.clear() runs in
tearDown. Tests that depend on a populated counter from a previous test
will fail. Set up cache state explicitly per test.

## Next steps

- [Throttle classes](../../api/throttling/index.md): API reference for
  every throttle class.
