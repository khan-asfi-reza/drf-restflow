# Generic views

The eight async generic views mirror DRF's generics one-for-one. Each
is built by composing one or more model mixins on top of
`AsyncGenericAPIView`. Use them for the standard list, retrieve,
create, update, and delete shapes; reach for `AsyncAPIView` only when
the endpoint cannot be expressed as a queryset plus serializer.

## AsyncGenericAPIView

`AsyncGenericAPIView` extends `AsyncAPIView` and DRF's
`GenericAPIView` simultaneously. It adds three async hooks on top of
the standard generic surface.

| Hook                | Purpose                                       |
| ------------------- | --------------------------------------------- |
| afilter_queryset    | Iterate filter_backends, awaiting async ones |
| apaginate_queryset  | Page through the queryset                     |
| aget_object         | Look up a single object via queryset.aget     |

Each hook follows the same fall-back contract used elsewhere: an async
implementation is awaited directly, a sync one is wrapped in
`sync_to_async`. This means existing DRF filter backends and paginators
work without modification, and `RestflowFilterBackend` -- which exposes
`afilter_queryset` -- is awaited natively.

`AsyncGenericAPIView` is rarely used directly. Compose with mixins or
pick one of the concrete subclasses below.

## AsyncListAPIView

GET-only list endpoint. Mixes `AsyncListModelMixin`.

```python
from restflow.views import AsyncListAPIView

class ProductListView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
    pagination_class = PageNumberPagination
```

The handler is `async def get` and returns the result of
`self.list(...)`. The list flow filters the queryset, paginates, and
serialises the page. When pagination is disabled the entire queryset
is serialised in one response.

## AsyncCreateAPIView

POST-only create endpoint. Mixes `AsyncCreateModelMixin`.

```python
class ProductCreateView(AsyncCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

The handler is `async def post`. The flow is validate -> aperform_create
-> 201 with a Location header (when the serializer exposes a URL field).
Override `aperform_create` for side effects.

```python
async def aperform_create(self, serializer):
    instance = await serializer.asave(created_by=self.request.user)
    await audit_log.arecord("product_created", instance.id)
```

## AsyncRetrieveAPIView

GET detail endpoint. Mixes `AsyncRetrieveModelMixin`.

```python
class ProductDetailView(AsyncRetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = "pk"
```

The handler is `async def get`. The flow is aget_object -> serialize
-> 200.

## AsyncUpdateAPIView

PUT and PATCH endpoint for a single object. Mixes
`AsyncUpdateModelMixin`.

```python
class ProductUpdateView(AsyncUpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

`async def put` runs a full update; `async def patch` runs a partial
update by flipping `partial=True` on the serializer. Override
`aperform_update` for side effects, audit trails, or notifications.

## AsyncDestroyAPIView

DELETE endpoint. Mixes `AsyncDestroyModelMixin`.

```python
class ProductDeleteView(AsyncDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

The handler is `async def delete`. The flow is aget_object ->
aperform_destroy -> 204. The default `aperform_destroy` prefers
`instance.adelete()` and falls back to a sync_to_async wrapper around
`instance.delete()`.

```python
async def aperform_destroy(self, instance):
    instance.is_archived = True
    await instance.asave()
```

## AsyncListCreateAPIView

GET list + POST create on the same URL. Mixes both list and create
mixins.

```python
class ProductListCreateView(AsyncListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
    pagination_class = PageNumberPagination
```

GET routes to `list`, POST routes to `create`.

## AsyncRetrieveUpdateAPIView

GET detail + PUT/PATCH on the same URL. Mixes retrieve and update
mixins.

```python
class ProductDetailUpdateView(AsyncRetrieveUpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

GET routes to `retrieve`, PUT routes to `update`, PATCH routes to
`partial_update`.

## AsyncRetrieveDestroyAPIView

GET detail + DELETE on the same URL.

```python
class ProductDetailDestroyView(AsyncRetrieveDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

## AsyncRetrieveUpdateDestroyAPIView

The full single-instance CRUD shape: GET detail, PUT, PATCH, DELETE.

```python
class ProductDetailView(AsyncRetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

This is the most common detail endpoint. For the list + detail pair on a
single resource, use this view in tandem with `AsyncListCreateAPIView`,
or move both into a single `AsyncModelViewSet`.

## Filter backends

`filter_backends` works the same as in DRF. Common configurations.

```python
from restflow.filters import RestflowFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

class ProductListView(AsyncListAPIView):
    filter_backends = [RestflowFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilterSet
    search_fields = ["name", "description"]
    ordering_fields = ["created_at", "price"]
```

The async path runs each backend through `afilter_queryset`. If a
backend exposes the async hook (as `RestflowFilterBackend` does), it is
awaited directly. Otherwise the sync `filter_queryset` is wrapped in
`sync_to_async`. Either way the queryset chains through the backends in
order, exactly as it does in DRF.

## Pagination

`pagination_class` works the same as in DRF.

```python
from rest_framework.pagination import PageNumberPagination

class ProductListView(AsyncListAPIView):
    pagination_class = PageNumberPagination
```

Set it to None at the class level (or simply omit it) to disable
pagination. The async path calls `apaginate_queryset` on the paginator
when present and falls back to a thread otherwise.

## aget_object

`aget_object` is the model lookup hook. The default implementation:

1. Calls `get_queryset()` to fetch the base queryset.
2. Filters it through `afilter_queryset`.
3. Reads `lookup_url_kwarg` (or `lookup_field`) from `self.kwargs`.
4. Calls `queryset.aget(**{lookup_field: value})`. Raises `Http404` on
   missing rows or invalid lookup values.
5. Calls `acheck_object_permissions(request, obj)` before returning.

Override `aget_object` only when the lookup logic itself needs to
change. To change the queryset that is searched, override
`get_queryset` instead. To change the URL field, set
`lookup_field = "slug"` (and optionally `lookup_url_kwarg`).

## Overriding get_queryset

`get_queryset` may stay sync (the default DRF signature) or be redefined
as `async def`. The generic views call it through `aget_object` and
through the list flow, both of which await the result if it is a
coroutine.

```python
class ProductListView(AsyncListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.filter(owner=self.request.user)
```

For an async-only data source, define an async version.

```python
class ProductListView(AsyncListAPIView):
    serializer_class = ProductSerializer

    async def get_queryset(self):
        ids = await fetch_visible_ids(self.request.user)
        return Product.objects.filter(id__in=ids)
```

The async helpers (afilter_queryset, apaginate_queryset) handle the
await internally so the override only needs to return the eventual
queryset.
