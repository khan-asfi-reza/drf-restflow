# Response Headers

`set_response_cache_header` attaches cache metadata to a DRF response,
so the client or monitoring tooling can see whether the response came
from cache.

## Usage

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from restflow.caching import cache_result, set_response_cache_header


@cache_result(ttl=300)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)


@api_view(["GET"])
def user_view(request, user_id):
    value, metadata = get_user_payload.get_with_metadata(user_id)
    response = Response(value)
    return set_response_cache_header(response, metadata)
```

Pair `set_response_cache_header` with
`CachedWrapper.get_with_metadata(...)`. The metadata dict carries
the cache status and timestamps, which the helper translates into
response headers.

## Headers emitted

| Header | Source | Meaning |
| --- | --- | --- |
| `X-Cache-status` | `metadata["cache_status"]` | One of `HIT`, `MISS`, `STALE`, `BYPASS`, `REFRESH`. |
| `X-Cached-at` | `metadata["cached_at"]` | ISO-format timestamp when the cached value was stored. |
| `X-Cache-reset-at` | `metadata["reset_at"]` | ISO-format timestamp when the cached value expires. |

Headers for missing fields are skipped. An empty or `None` metadata
dict makes the call a no-op.

## Cache status values

| Status | When |
| --- | --- |
| `HIT` | The value came from cache. |
| `MISS` | The cache had no entry; the value was computed and stored fresh. |
| `STALE` | A cached value was served while a background refresh ran. |
| `BYPASS` | The cache was skipped (`bypass_cache(...)`); the value was computed live. |
| `REFRESH` | A forced recompute (`refresh(...)`) overwrote the previous entry. |

Read the values from `restflow.caching.CacheStatus`:

```python
from restflow.caching import CacheStatus


if metadata["cache_status"] == CacheStatus.MISS:
    log_cache_miss(...)
```

## Class-based view

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from restflow.caching import set_response_cache_header


class UserView(APIView):
    def get(self, request, user_id):
        value, metadata = get_user_payload.get_with_metadata(user_id)
        response = Response(value)
        return set_response_cache_header(response, metadata)
```


## Where to next

- [cache_result](cache-result.md) for `get_with_metadata` and the
  rest of the wrapper API.
