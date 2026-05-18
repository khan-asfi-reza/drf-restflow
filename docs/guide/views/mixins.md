# Mixins

The five async model mixins implement the action methods for create,
list, retrieve, update, and destroy. The generic views and the
`AsyncModelViewSet` viewset are built by combining them with
`AsyncGenericAPIView` (or its viewset cousin). Mix and match to build
non-standard views without giving up the async pipeline.

## AsyncCreateModelMixin

Provides the `create` action.

```python
async def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    await avalidate_or_is_valid_serializer(serializer, raise_exception=True)
    await self.aperform_create(serializer)
    headers = self.get_success_headers(serializer.data)
    return Response(serializer.data, status=201, headers=headers)
```

Validates the request body and calls `aperform_create`, which saves
the instance. Returns 201 with the serialized data. Override
`aperform_create` to add side effects without changing the response
shape.

```python
async def aperform_create(self, serializer):
    instance = await serializer.asave(created_by=self.request.user)
    await notify_created(instance)
```

## AsyncListModelMixin

Provides the `list` action.

```python
async def list(self, request, *args, **kwargs):
    queryset = await self.afilter_queryset(self.get_queryset())
    page = await self.apaginate_queryset(queryset)
    if page is not None:
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    serializer = self.get_serializer(queryset, many=True)
    return Response(serializer.data)
```

Filters the queryset, paginates it, and returns the serialized page.
When no paginator is configured, the full queryset is serialized and
returned directly.

The mixin does not call the helper methods from
`APIViewHelpersMixin`; it uses DRF's classic `get_serializer(...)`
contract directly so it stays compatible with viewsets that do not
need separate request/response serializers. When custom response
shapes or PostFetch joins are needed, override `list` and call
`apaginated_response(...)` from the helper surface instead.

## AsyncRetrieveModelMixin

Provides the `retrieve` action.

```python
async def retrieve(self, request, *args, **kwargs):
    instance = await self.aget_object()
    serializer = self.get_serializer(instance)
    return Response(serializer.data)
```

Fetches the object via `aget_object` (filtering, lookup, and
object-level permission checks), serializes it, and returns 200.

## AsyncUpdateModelMixin

Provides `update` (PUT) and `partial_update` (PATCH).

```python
async def update(self, request, *args, **kwargs):
    partial = kwargs.pop("partial", False)
    instance = await self.aget_object()
    serializer = self.get_serializer(instance, data=request.data, partial=partial)
    await avalidate_or_is_valid_serializer(serializer, raise_exception=True)
    await self.aperform_update(serializer)
    if getattr(instance, "_prefetched_objects_cache", None):
        instance._prefetched_objects_cache = {}
    return Response(serializer.data)

async def partial_update(self, request, *args, **kwargs):
    kwargs["partial"] = True
    return await self.update(request, *args, **kwargs)
```

Fetches the object, validates the request body, and calls
`aperform_update` to save. Returns 200 with the serialized data.
`partial_update` delegates to `update` with `partial=True`, giving
PATCH semantics. Override `aperform_update` to add side effects.

```python
async def aperform_update(self, serializer):
    instance = await serializer.asave()
    await audit_log.arecord("product_updated", instance.id)
```

## AsyncDestroyModelMixin

Provides the `destroy` action.

```python
async def destroy(self, request, *args, **kwargs):
    instance = await self.aget_object()
    await self.aperform_destroy(instance)
    return Response(status=204)
```

Fetches the object and calls `aperform_destroy` to delete it, then
returns 204. Override `aperform_destroy` for soft-delete semantics,
archive flags, or cascade hooks.

## Composing mixins

A custom view can be assembled by mixing the relevant action mixins
on top of `AsyncGenericAPIView` and exposing the wanted HTTP methods.

```python
from restflow.views import (
    AsyncCreateModelMixin,
    AsyncListModelMixin,
    AsyncRetrieveModelMixin,
    AsyncGenericAPIView,
)

class ProductReadAndCreateView(
    AsyncListModelMixin,
    AsyncCreateModelMixin,
    AsyncRetrieveModelMixin,
    AsyncGenericAPIView,
):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination

    async def get(self, request, *args, **kwargs):
        if "pk" in kwargs:
            return await self.retrieve(request, *args, **kwargs)
        return await self.list(request, *args, **kwargs)

    async def post(self, request, *args, **kwargs):
        return await self.create(request, *args, **kwargs)
```

The same pattern applies to viewsets. To build a viewset that exposes
list, create, and destroy but no retrieve or update, mix only those
three action mixins on top of `AsyncGenericViewSet`.

```python
from restflow.views import (
    AsyncCreateModelMixin,
    AsyncDestroyModelMixin,
    AsyncListModelMixin,
    AsyncGenericViewSet,
)

class ProductSoftViewSet(
    AsyncListModelMixin,
    AsyncCreateModelMixin,
    AsyncDestroyModelMixin,
    AsyncGenericViewSet,
):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

## Override hooks

The persistence hooks (`aperform_create`, `aperform_update`,
`aperform_destroy`) are the recommended extension points. They run
after validation and before the response, which makes them the right
place for audit logging, notifications, and side-channel writes.

| Mixin                    | Hook to override                       |
| ------------------------ | -------------------------------------- |
| AsyncCreateModelMixin    | aperform_create                        |
| AsyncUpdateModelMixin    | aperform_update                        |
| AsyncDestroyModelMixin   | aperform_destroy                       |
| AsyncListModelMixin      | list (when the standard flow is wrong) |
| AsyncRetrieveModelMixin  | retrieve (rare; aget_object is better) |

For most customisation, override the perform hook rather than the
action method itself. The action methods own the request/response
plumbing; the perform hooks own the persistence.
