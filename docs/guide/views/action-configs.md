# Action configs

`ActionConfig` is a small frozen dataclass for declaring per-action
overrides on a viewset. It avoids the maintenance cost of writing one
`if self.action == "list": ...` branch per getter and keeps overrides
visible in a single mapping at the top of the class.

## The dataclass

```python
@dataclass(frozen=True)
class ActionConfig:
    serializer_class: type | None = None
    request_serializer_class: type | None = None
    response_serializer_class: type | None = None
    permission_classes: list | tuple | None = None
    throttle_classes: list | tuple | None = None
    parser_classes: list | tuple | None = None
    renderer_classes: list | tuple | None = None
    pagination_class: type | None = None
    queryset: Any = None
```

Every field is optional and defaults to None. None means "fall through
to the next layer". Set only the fields the action needs to override.

The dataclass is frozen so an instance is safe to share between
viewsets. Build them at module level when they need to be reused.

## Lookup order

The viewset getters consult three layers in order.

1. The ActionConfig field for the current action.
2. The parent's `get_*()` method (DRF's chain).
3. The class attribute (`serializer_class`, `pagination_class`, etc).

The first non-None value wins. The chain is the same for every getter,
which means the override semantics are predictable across attributes.

```
ActionConfig.serializer_class   ->   super().get_serializer_class()   ->   self.serializer_class
```

The same chain applies to permission_classes, throttle_classes,
parser_classes, renderer_classes, pagination_class, and queryset.

## The queryset field

The queryset field is the only one that accepts more than a class
reference. Three shapes are supported.

| Shape       | Resolution                                       |
| ----------- | ------------------------------------------------ |
| QuerySet    | Returned via `qs.all()`                          |
| Manager     | Returned via `manager.all()`                     |
| Callable    | Called with `self`, expected to return a QuerySet |

The callable form is useful when the queryset depends on the current
request.

```python
ActionConfig(
    queryset=lambda self: Product.objects.filter(owner=self.request.user),
)
```

The callable receives the viewset instance, so `self.request`,
`self.action`, and `self.kwargs` are all available.

## Common patterns

### Lighter list serializer

A list endpoint typically returns less detail per item than a retrieve
endpoint. Configure both response shapes from a single declaration.

```python
class ProductViewSet(AsyncModelViewSet):
    serializer_class = ProductDetailSer
    queryset = Product.objects.all()
    action_configs = {
        "list": ActionConfig(response_serializer_class=ProductListSer),
    }
```

### Admin-only destroy

```python
action_configs = {
    "destroy": ActionConfig(permission_classes=[IsAdminUser]),
}
```

The class-wide `permission_classes` still applies to every other
action. The destroy action gets its own list, replacing the default
during the dispatch loop.

### Faster pagination on list

```python
from restflow.pagination import FastPageNumberPagination

action_configs = {
    "list": ActionConfig(pagination_class=FastPageNumberPagination),
}
```

`PageNumberPagination` runs an extra `count(*)` query to compute
totals; `FastPageNumberPagination` skips the count and trades total
counts for query speed. Use it on hot list endpoints.

### Per-action queryset

```python
action_configs = {
    "list": ActionConfig(
        queryset=lambda self: Product.objects.filter(owner=self.request.user),
    ),
    "archive_list": ActionConfig(
        queryset=Product.objects.filter(is_archived=True),
    ),
}
```

The list endpoint scopes results to the current user; a custom
`archive_list` action looks at archived rows.

### Per-action throttle

```python
action_configs = {
    "create": ActionConfig(throttle_classes=[BurstThrottle]),
}
```

## Custom actions

Custom actions added through `@action(...)` participate in the same
lookup chain. The action name on the viewset is the method name (or
the `url_name` argument when supplied).

```python
class ProductViewSet(AsyncModelViewSet):
    serializer_class = ProductSer
    queryset = Product.objects.all()

    action_configs = {
        "bulk_archive": ActionConfig(
            request_serializer_class=BulkArchiveSer,
            permission_classes=[IsAdminUser],
        ),
    }

    @action(detail=False, methods=["post"])
    async def bulk_archive(self, request):
        ser = await self.avalidated_serializer()
        ...
```

The ActionConfig entry under `"bulk_archive"` is consulted whenever
`self.action == "bulk_archive"`, so request serializer and permission
overrides apply automatically.

## ActionConfig vs @action overrides

DRF lets `@action` accept many of the same overrides directly:

```python
@action(detail=False, methods=["post"], serializer_class=BulkArchiveSer)
```

The trade-off.

| Approach     | Pros                                              |
| ------------ | ------------------------------------------------- |
| ActionConfig | One place per viewset, every override visible.    |
| @action      | Override sits next to the action it modifies.     |

The two mechanisms cooperate. ActionConfig wins when both are present,
because the action-config-aware getter checks the dict before
delegating to the parent (which reads the `@action` attribute).

For consistency, pick one approach per viewset. ActionConfig scales
better as the override surface grows.

## Worked example

A complete viewset showing several override patterns.

```python
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from restflow.pagination import FastPageNumberPagination
from restflow.views import (
    ActionConfig,
    AsyncModelViewSet,
)

class ProductViewSet(AsyncModelViewSet):
    serializer_class = ProductDetailSer
    queryset = Product.objects.all()
    pagination_class = PageNumberPagination
    permission_classes = [IsAuthenticated]
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet

    action_configs = {
        "list": ActionConfig(
            response_serializer_class=ProductListSer,
            pagination_class=FastPageNumberPagination,
            queryset=lambda self: Product.objects.filter(
                owner=self.request.user,
            ),
        ),
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
        "archive": ActionConfig(
            queryset=Product.objects.filter(is_archived=True),
            permission_classes=[IsAdminUser],
        ),
    }

    @action(detail=False, methods=["get"])
    async def archive(self, request):
        return await self.apaginated_response(self.get_queryset())
```

The same class delivers four different policies on the same model
without scattering conditionals across multiple methods.
