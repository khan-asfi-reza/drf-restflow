# Pagination

Restflow ships a small family of pagination classes that mirror
DRF's paginators while exposing an async hook (`apaginate_queryset`)
for async views. Every paginator returns a sliced result list and
builds a paginated response that includes navigation links.

Four paginators are provided. The right choice depends on the size of
the table, the access pattern, and what the consumer needs to display.

| Paginator | Best for | Trade-offs |
| --- | --- | --- |
| `PageNumberPagination` | Small to medium result sets, UIs that show "Page 3 of 50". | Issues a `COUNT(*)` per request. |
| `CursorPagination` | Large append-only tables, timelines, feeds. | No total count, no random page jumps; ordering must be unique. |
| `LimitOffsetPagination` | Explicit windowing where the consumer wants control over the slice (admin tools, bulk exports). | Issues a `COUNT(*)`; deep offsets are slow on large tables. |
| `FastPageNumberPagination` | Very large tables where the `COUNT(*)` query dominates the request budget. | Response omits the total count; only "is there a next page" is reported. |


## The async hook

All restflow paginators expose an async method:

```python
async def apaginate_queryset(self, queryset, request, view=None):
    ...
```

Async views (`AsyncListAPIView`, `AsyncListModelMixin`,
`AsyncModelViewSet`, ...) call this method when it is
present. It returns a list of items for the current page, or `None`
when pagination is disabled for the request.

`BasePagination` provides a default implementation that runs the sync
`paginate_queryset` in a thread through `sync_to_async`. Subclasses
override this method whenever an async ORM path is available.

```python
class BasePagination(drf_pagination.BasePagination):
    async def apaginate_queryset(self, queryset, request, view=None):
        return await sync_to_async(
            self.paginate_queryset, thread_sensitive=True,
        )(queryset, request, view)
```

Returning `None` from `apaginate_queryset` disables pagination for
that single request. The view consumes the queryset directly without
slicing or wrapping the response.

## PageNumberPagination

Page-number pagination using async ORM operations
(`acount`, async iteration over the sliced queryset).

### Class attributes

| Attribute | Default | Description |
| --- | --- | --- |
| `page_size` | from `api_settings.PAGE_SIZE` | Number of items per page. |
| `page_size_query_param` | None | Query parameter that, when set, lets the client override the page size. |
| `max_page_size` | None | Upper bound applied when `page_size_query_param` is honoured. |
| `page_query_param` | "page" | Query parameter that selects the page number. |
| `invalid_page_message` | DRF default | Message used in 404s when the page is invalid. |

### Response shape

```json
{
  "count": 1234,
  "next": "http://api/items/?page=4",
  "previous": "http://api/items/?page=2",
  "results": [...]
}
```

### Example

```python
from restflow.pagination import PageNumberPagination
from restflow.views import AsyncListAPIView


class ProductPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductListView(AsyncListAPIView):
    serializer_class = ProductSerializer
    pagination_class = ProductPagination

    async def get_queryset(self):
        return Product.objects.all()
```

### Async path

`apaginate_queryset` calls `await queryset.acount()` to get the total
and then materialises the sliced page with
`[obj async for obj in sliced]`. 

### Dynamic page size

Override `get_page_size(request)` to choose a page size at runtime,
for instance based on the authenticated user.

```python
class ProductPagination(PageNumberPagination):
    page_size = 20

    def get_page_size(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_staff:
            return 100
        return super().get_page_size(request)
```

## LimitOffsetPagination

Limit/offset pagination using async ORM operations.

### Class attributes

| Attribute | Default | Description |
| --- | --- | --- |
| `default_limit` | from `api_settings.PAGE_SIZE` | Limit applied when the request does not set one. |
| `limit_query_param` | "limit" | Query parameter that overrides the default limit. |
| `offset_query_param` | "offset" | Query parameter that selects the offset. |
| `max_limit` | None | Upper bound applied to the requested limit. |

### Response shape

```json
{
  "count": 1234,
  "next": "http://api/items/?limit=20&offset=40",
  "previous": "http://api/items/?limit=20",
  "results": [...]
}
```

### Example

```python
from restflow.pagination import LimitOffsetPagination


class ExportPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 500


class ExportListView(AsyncListAPIView):
    serializer_class = ExportSerializer
    pagination_class = ExportPagination
```

```bash
curl 'http://api/exports/?limit=100&offset=200'
```

### Async path

`apaginate_queryset` runs `await queryset.acount()`, computes the
offset window, and then materialises rows with
`[obj async for obj in sliced]`.

## CursorPagination

Cursor-based pagination. Suited to large append-only tables and
timelines because the cursor is stable across concurrent inserts.

### Required configuration

`ordering` must be set on the paginator and the columns it names
must form a unique tuple. A common pattern is to combine a sortable
timestamp with the primary key:

```python
from restflow.pagination import CursorPagination


class ActivityPagination(CursorPagination):
    page_size = 50
    ordering = "-created_at,-id"
```

If the ordering is not unique, the cursor cannot reliably identify
the last row of a page, which leads to skipped or duplicated rows
across pages.

### Response shape

```json
{
  "next": "http://api/activity/?cursor=cD0yMDI0LTAxLTAx",
  "previous": null,
  "results": [...]
}
```

The cursor is an opaque base64 string. The server-side encoder may
change between releases, so the cursor must be treated as a token
rather than a structured value.

### Async path

`CursorPagination` inherits DRF's sync `paginate_queryset` and
relies on `BasePagination.apaginate_queryset` to run that logic in a
thread through `sync_to_async`. Cursor pagination walks a single
window of size `page_size` plus a peek row, so the lack of an async
ORM call is not a meaningful overhead.

### Stability across inserts

Because the cursor encodes the position in the ordering rather than
an offset, rows inserted at the head of the table (with newer
timestamps) do not shift the next page. The next call returns the
same window the previous response promised.

## FastPageNumberPagination

Page-number pagination that omits the `COUNT(*)` query. The
response includes `next` and `previous` links but no total count.

### Class attributes

| Attribute | Default | Description |
| --- | --- | --- |
| `page_size` | `api_settings.PAGE_SIZE` | Items per page. |
| `page_query_param` | "page" | Query parameter that selects the page. |
| `page_size_query_param` | None | Query parameter that lets the client override the page size. |
| `max_page_size` | None | Upper bound applied when `page_size_query_param` is honoured. |
| `invalid_page_message` | "Invalid page." | Message used in 404 responses. |

### Response shape

```json
{
  "next": "http://api/events/?page=4",
  "previous": "http://api/events/?page=2",
  "results": [...]
}
```

There is no `count` field. The `next` link is set when the current
page came back full; otherwise it is `null`.

### Example

```python
from restflow.pagination import FastPageNumberPagination


class EventPagination(FastPageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class EventListView(AsyncListAPIView):
    serializer_class = EventSerializer
    pagination_class = EventPagination
```

### next URL

After fetching the page, the paginator checks whether the slice
returned exactly `page_size` rows. If it did, a next page is assumed
to exist. If it did not, the next link is `null`. This avoids the
`COUNT(*)`.

### When the page is empty

When the slice is empty and the requested page number is greater
than 1, the paginator raises a 404 with `invalid_page_message`. An
empty result on page 1 is treated as a valid empty list rather than
an error.

### Async path

`apaginate_queryset` materialises the slice with an async iteration
(`[obj async for obj in sliced]`) and never issues a count.

## Configuring through ActionConfig

`restflow.views.ActionConfig` is a dataclass that lets a viewset
override per-action settings, including `pagination_class`. When a
field is set on the config, it takes precedence over the class-level
attribute for that single action.

```python
from restflow.pagination import (
    FastPageNumberPagination,
    LimitOffsetPagination,
)
from restflow.views import ActionConfig, AsyncModelViewSet


class ArticleViewSet(AsyncModelViewSet):
    serializer_class = ArticleSerializer
    queryset = Article.objects.all()
    pagination_class = None

    action_configs = {
        "list": ActionConfig(
            pagination_class=FastPageNumberPagination,
        ),
        "exports": ActionConfig(
            pagination_class=LimitOffsetPagination,
        ),
    }
```

`get_pagination_class()` consults `action_configs` first and falls
back to the class attribute. Setting the config field to `None`
keeps the class-level value; setting it to an explicit `None` does
not "unset" pagination for that action. To disable pagination on a
specific action, override `get_pagination_class()` directly.

## Disabling pagination

Set the class attribute to `None`:

```python
class ArticleListView(AsyncListAPIView):
    pagination_class = None
```

Or override the hook to disable pagination conditionally:

```python
class ArticleListView(AsyncListAPIView):
    pagination_class = PageNumberPagination

    def get_pagination_class(self):
        if self.request.query_params.get("all") == "true":
            return None
        return super().get_pagination_class()
```

A paginator can also disable itself for a single request by
returning `None` from `apaginate_queryset`. The view then bypasses
the paginated response wrapper and serialises the entire queryset.

## Custom paginators

Two routes are supported.

### Subclass BasePagination

Subclassing `BasePagination` gives an async-aware paginator out of
the box. The default `apaginate_queryset` runs the sync method in a
thread, so a sync-only implementation works without further wiring.

```python
from restflow.pagination import BasePagination


class HeaderPagination(BasePagination):
    def paginate_queryset(self, queryset, request, view=None):
        ...

    def get_paginated_response(self, data):
        ...
```

### Subclass an existing DRF paginator

When extending one of DRF's paginators directly, override
`apaginate_queryset` to keep the database call on the event loop:

```python
from rest_framework import pagination as drf_pagination
from asgiref.sync import sync_to_async


class CustomPagination(drf_pagination.PageNumberPagination):
    async def apaginate_queryset(self, queryset, request, view=None):
        return await sync_to_async(
            self.paginate_queryset, thread_sensitive=True,
        )(queryset, request, view)
```

Restflow's own paginators take this shape but use the async ORM
where it pays off.

## Settings interaction

DRF's `DEFAULT_PAGINATION_CLASS` and `PAGE_SIZE` settings still
apply.

```python
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": (
        "restflow.pagination.PageNumberPagination"
    ),
    "PAGE_SIZE": 20,
}
```

The class-level `page_size` defaults read from `api_settings.PAGE_SIZE`,
so configuring the global value is the simplest way to change the
default for every paginator. `FastPageNumberPagination.page_size`
reads from the same setting at class definition time.


## Next steps

- [Pagination API reference](../../api/pagination/index.md): the
  full class signatures.
