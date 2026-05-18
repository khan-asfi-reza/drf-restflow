# Views

The restflow views module is an async-first port of DRF's view stack. It
keeps DRF's class hierarchy, semantics, and override hooks while running
the dispatch loop, authentication, permissions, throttles, pagination,
and persistence on `async def` code paths. Helpers for the routine
serialize-validate-respond pattern come bundled.

## Features

The async views layer brings five concrete capabilities on top of DRF.

- **Async dispatch loop.** AsyncAPIView.dispatch is `async def`. The
  request is processed without blocking the event loop, so the view
  works under ASGI, with Django Channels, or behind any async-capable
  server.
- **Async hook surface.** Authentication, permissions, throttling,
  pagination, filtering, and object lookup all expose async variants
  (aauthenticate, ahas_permission, aallow_request, apaginate_queryset,
  afilter_queryset, aget_object). Each falls back to sync_to_async when
  a sync-only implementation is configured, so existing DRF code keeps
  working.
- **Helper methods.** The `APIViewHelpersMixin` adds get_serializer,
  validated_serializer, serialized_response, and paginated_response
  (and their async variants) so common endpoints stop repeating
  validate-and-respond boilerplate.
- **Action-config overrides.** ActionConfig is a small dataclass that
  lets a viewset swap serializer, permission, throttle, parser,
  renderer, pagination, and queryset on a per-action basis without
  spreading conditionals across get_*() methods.
- **PostFetch joins.** A small helper for attaching related rows to a
  paginated list when prefetch_related cannot express the join (for
  example, attaching a single latest related row per item).

## Base classes

- For a non-model endpoint (no queryset, no model lookup), pick
  `APIView` (sync) or `AsyncAPIView` (async). The helpers
  validated_serializer / serialized_response / paginated_response are
  available on both.
- For a model-backed endpoint that wires queryset, serializer_class,
  filter_backends, and pagination_class, pick one of the generic
  views: AsyncListAPIView, AsyncCreateAPIView, AsyncRetrieveAPIView,
  AsyncUpdateAPIView, AsyncDestroyAPIView, AsyncListCreateAPIView,
  AsyncRetrieveUpdateAPIView, AsyncRetrieveDestroyAPIView,
  AsyncRetrieveUpdateDestroyAPIView.
- For a CRUD set under a single resource URL, pick a viewset:
  AsyncReadOnlyModelViewSet for list + retrieve only, or
  AsyncModelViewSet for the full CRUD surface. Register with
  rest_framework's DefaultRouter.
- For a non-standard view (for example list + create + destroy with no
  retrieve), compose mixins on top of AsyncGenericAPIView.

DRF concepts apply unchanged. lookup_field, lookup_url_kwarg,
filter_backends, pagination_class, permission_classes, queryset, and
serializer_class behave the same. The async layer wraps them rather
than replacing them.

## The serializer split

DRF uses a single `serializer_class` for both request validation and
response rendering. restflow keeps that as the default but adds two
optional overrides for endpoints whose input and output shapes diverge.

| Attribute                    | Direction | Default          |
| ---------------------------- | --------- | ---------------- |
| serializer_class             | both      | required         |
| request_serializer_class     | input     | serializer_class |
| response_serializer_class    | output    | serializer_class |

Resolved through three getters that any subclass can override.

```python
def get_serializer_class(self):
    return self.serializer_class

def get_request_serializer_class(self):
    return self.request_serializer_class or self.get_serializer_class()

def get_response_serializer_class(self):
    return self.response_serializer_class or self.get_serializer_class()
```

The helpers wire these up automatically: validated_serializer picks the
request class, serialized_response and paginated_response pick the
response class.

## Helper methods

Every helper exists as a sync method on `APIView` and as an async variant
on `AsyncAPIView`. The async variants differ only in that they await
`ais_valid` / `asave` when the serializer exposes them, and they await
PostFetch.afetch when post_fetches is non-empty.

| Sync                   | Async                  | Use                                     |
| ---------------------- | ---------------------- | --------------------------------------- |
| get_serializer         | get_serializer         | Build a serializer with request context |
| validated_serializer   | avalidated_serializer  | Validate request body, raise on errors  |
| serialized_response    | aserialized_response   | Serialize and return a Response         |
| paginated_response     | apaginated_response    | Paginate, serialize, and respond        |

Short example with AsyncAPIView.

```python
class TopProductsView(AsyncAPIView):
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination

    async def get(self, request):
        qs = Product.objects.filter(is_top=True)
        return await self.apaginated_response(qs)

    async def post(self, request):
        ser = await self.avalidated_serializer()
        product = await ser.asave()
        return await self.aserialized_response(product, status=201)
```

The same code works on `APIView` once the async keyword is dropped and
sync helpers replace the async variants.

## PostFetch helpers

`PostFetch` attaches related rows to a list of base objects after the
list has been fetched (or paginated). Use it when prefetch_related
cannot express the join, when the related rows live on a different
database, or when only the latest related row per base item is needed.

```python
latest_review = PostFetch(
    queryset=Review.objects.all(),
    to_attr="latest_review",
    values=["id", "rating", "comment"],
    order_by=["-created_at"],
    limit=1,
    product_id="id",
)

return await self.apaginated_response(
    Product.objects.all(),
    post_fetches=[latest_review],
)
```

The fetch runs once per call, regardless of page size. See the
[PostFetch guide](post-fetch.md) for a deeper walkthrough.

## Where to read next

- [APIView](apiview.md) -- the dispatch loop and helper surface.
- [Generic views](generic-views.md) -- the eight async generic views
  and the hooks they call.
- [Mixins](mixins.md) -- the five model mixins, what they do, and how
  to compose them.
- [Viewsets](viewsets.md) -- AsyncViewSet, AsyncGenericViewSet,
  AsyncReadOnlyModelViewSet, AsyncModelViewSet, and routing.
- [Action configs](action-configs.md) -- per-action overrides through
  ActionConfig.
- [PostFetch](post-fetch.md) -- joining related rows after pagination.
