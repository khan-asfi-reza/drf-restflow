# Viewsets

Viewsets group the list, retrieve, create, update, and destroy actions
for a single resource onto one class. The async viewsets keep DRF's
viewset semantics (action_map, basename, suffix, the `@action`
decorator) and add an async dispatch path plus action-config-aware
getters.

## AsyncViewSetMixin

`AsyncViewSetMixin` is the base mixin shared by every async viewset.
It does three things.

- Replaces `as_view()` with a closure that returns an async view
  callable. The closure binds the action map, instantiates the
  viewset, and awaits `self.dispatch(...)`.
- Wraps every getter that drives dispatch with action-config awareness.
  The wrapped getters consult `self.action_configs.get(self.action)`
  and return the override when one is configured. When no override is
  set the call delegates to the parent getter, preserving the rest of
  the lookup chain.
- Caches the paginator instance on `self._paginator` so repeated
  reads of `self.paginator` do not rebuild it.

The wrapped getters are: get_serializer_class,
get_request_serializer_class, get_response_serializer_class,
get_permissions, get_throttles, get_parsers, get_renderers,
get_pagination_class, and get_queryset. Each follows the same lookup
order: ActionConfig field -> super().get_*() -> class attribute.

`get_queryset` accepts three queryset shapes from an ActionConfig:

- A static QuerySet instance. Returned as-is via `.all()`.
- A Manager. Resolved with `manager.all()`.
- A callable with signature `(self) -> QuerySet`. Called every request.

When no ActionConfig is set and the parent getter is missing, an
AssertionError is raised with guidance to set `queryset` on the class,
on the action's ActionConfig, or by overriding `get_queryset()`.

## AsyncViewSet

`AsyncViewSet = AsyncViewSetMixin + AsyncAPIView`. The class has no
default actions. Use it when the wanted actions do not map onto a
queryset, or when implementing several non-CRUD endpoints under a
single resource URL.

```python
from rest_framework.decorators import action
from restflow.views import AsyncViewSet

class HealthViewSet(AsyncViewSet):
    @action(detail=False, methods=["get"])
    async def ping(self, request):
        return await self.aserialized_response({"status": "ok"})

    @action(detail=False, methods=["get"])
    async def time(self, request):
        return await self.aserialized_response({"now": timezone.now()})
```

## AsyncGenericViewSet

`AsyncGenericViewSet = AsyncViewSetMixin + AsyncGenericAPIView`. It
adds the generic surface (`aget_object`, `afilter_queryset`,
`apaginate_queryset`) but provides no actions by default. Use it when
composing a viewset out of mixins manually.

```python
from restflow.views import (
    AsyncGenericViewSet,
    AsyncListModelMixin,
    AsyncRetrieveModelMixin,
    AsyncCreateModelMixin,
)

class ProductViewSet(
    AsyncCreateModelMixin,
    AsyncRetrieveModelMixin,
    AsyncListModelMixin,
    AsyncGenericViewSet,
):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination
```

## AsyncReadOnlyModelViewSet

A viewset that exposes only `list` and `retrieve`.

```python
from restflow.views import AsyncReadOnlyModelViewSet

class ProductViewSet(AsyncReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
    pagination_class = PageNumberPagination
```

Pair with a router and the resource is browsable but immutable.

## AsyncModelViewSet

The full CRUD viewset: list, retrieve, create, update, partial_update,
destroy.

```python
from restflow.views import AsyncModelViewSet

class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
    pagination_class = PageNumberPagination
    permission_classes = [IsAuthenticated]
```

This is the default starting point for a model resource. Add
ActionConfig entries to override per action without subclassing.

## Routing

Async viewsets register with DRF's `DefaultRouter`. The router builds
the same URL patterns as for sync viewsets; the dispatch path is the
only thing that differs.

```python
from rest_framework.routers import DefaultRouter
from django.urls import include, path

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    path("api/", include(router.urls)),
]
```

The router calls `as_view({"get": "list", "post": "create"})` and
similar maps under the hood. `AsyncViewSetMixin.as_view` returns a
csrf-exempt async view callable, which Django and DRF handle the same
way as sync views.

## Custom actions

DRF's `@action` decorator works as expected; restflow's dispatch path
routes to the decorated method based on the action map the router
built from it.

```python
from rest_framework.decorators import action

class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    @action(detail=False, methods=["post"])
    async def bulk_archive(self, request):
        ser = await self.avalidated_serializer()
        await Product.objects.filter(id__in=ser.validated_data["ids"]).aupdate(
            is_archived=True,
        )
        return await self.aserialized_response({"ok": True})

    @action(detail=True, methods=["post"])
    async def archive(self, request, pk=None):
        instance = await self.aget_object()
        instance.is_archived = True
        await instance.asave()
        return await self.aserialized_response(instance)
```

A custom action's `self.action` attribute is the method name, so
`action_configs["bulk_archive"]` and `action_configs["archive"]` will
be picked up automatically.

For per-action overrides defined inline on the decorator -- for
example, `@action(serializer_class=ArchiveInputSer)` -- the resolver
falls through ActionConfig (no entry), the parent getter (which reads
the inline attribute), and finally the class attribute. The two
mechanisms can coexist on the same viewset.

## Per-method handlers vs viewset actions

The generic views (AsyncListAPIView, AsyncListCreateAPIView, and the
rest) expose handlers named after HTTP methods: get, post, put,
patch, delete. Viewsets expose handlers named after actions: list,
retrieve, create, update, partial_update, destroy. The router builds
the HTTP-method-to-action map at registration time.

The two styles produce identical wire behaviour for the same CRUD
shape, but they differ in three ways.

- **Single URL vs many.** A viewset registered through a router
  covers list, retrieve, create, update, and destroy under one
  register call. Per-method generic views need one URL pattern per
  route.
- **Action awareness.** Inside a viewset, `self.action` resolves to
  the action name like list, create, or bulk_archive. Generic views
  do not have an action attribute, so ActionConfig overrides do not
  apply.
- **Custom routes.** `@action(detail=True/False, methods=[...])` is a
  viewset-only decorator; the router collects the decorated methods
  and builds extra URL patterns for them.

For a single-resource API with standard CRUD plus a few custom
endpoints, the viewset path scales better. For a small endpoint with
no model lookup, a generic view (or AsyncAPIView) keeps the wiring
shorter.

## Hook overrides

The same hooks available on the generic views are available on the
viewsets.

| Hook                | Where to override                                |
| ------------------- | ------------------------------------------------ |
| get_queryset        | Class method (sync or async). Wins over None ActionConfig.queryset. |
| aperform_create     | When the create persistence path needs side-effects. |
| aperform_update     | When the update persistence path needs side-effects. |
| aperform_destroy    | When destroy means archive instead of delete.        |
| afilter_queryset    | Rare; reach for a filter backend instead.            |
| apaginate_queryset  | Rare; reach for a pagination class instead.          |
| acheck_permissions  | Cross-cutting permission gating.                     |
| ahandle_exception   | Customise error mapping.                             |

The shared rule is the same as for the generic views: prefer overriding
the named hook over rewriting the action method, so the action method
keeps owning the request/response contract while the hook owns the
behaviour change.

## Async get_queryset

`get_queryset` may stay sync, the way DRF defines it, or be redefined
as `async def`. The viewset's getters await the result when it is a
coroutine, so an async override slots into the existing dispatch path
without changing the contract.

```python
class ProductViewSet(AsyncModelViewSet):
    serializer_class = ProductSerializer

    async def get_queryset(self):
        ids = await fetch_visible_ids(self.request.user)
        return Product.objects.filter(id__in=ids)
```

When an `ActionConfig.queryset` is also configured for the current
action, the ActionConfig wins (because the action-config-aware
`get_queryset` checks the dict first). To honour both, leave the
ActionConfig queryset as None and put the request-dependent logic in
`get_queryset` itself.

## Nested routers

Restflow viewsets are compatible with the
`drf-nested-routers` package. The nested router builds the parent and
child URL patterns the same way it does for sync viewsets, and the
async dispatch closure works under both. Pass the parent lookup field
through to the child viewset's `get_queryset` to scope results.

```python
from rest_framework_nested.routers import NestedDefaultRouter
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")

products_router = NestedDefaultRouter(router, "products", lookup="product")
products_router.register("reviews", ReviewViewSet, basename="product-reviews")

urlpatterns = router.urls + products_router.urls


class ReviewViewSet(AsyncModelViewSet):
    serializer_class = ReviewSerializer
    queryset = Review.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(product_id=self.kwargs["product_pk"])
```

The nested lookup arrives in `self.kwargs` and is consumed by
`get_queryset` to filter the child queryset before any of the action
flows run.
