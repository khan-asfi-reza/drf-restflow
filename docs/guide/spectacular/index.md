# Spectacular

`RestflowAutoSchema` is a drop-in replacement for drf-spectacular's
`AutoSchema` that understands restflow's view conventions, including
per-action serializer splits, request/response serializer pairs,
and pagination resolution through `ActionConfig`.

## Features

drf-spectacular generates an OpenAPI 3.x schema from a DRF project,
along with Swagger UI and Redoc views to browse the schema in the
browser. The default `AutoSchema` reads a single `serializer_class`
attribute on the view, which does not fit restflow viewsets that
declare per-action overrides through `action_configs` or split
request and response shapes through `request_serializer_class` and
`response_serializer_class`.

`RestflowAutoSchema` adds:

- Awareness of `action_configs[<action>]` so the schema reflects the
  serializer that will actually run for the current action.
- A separate request/response serializer resolution path that picks
  up `get_request_serializer_class()` and
  `get_response_serializer_class()` defined by the
  `APIViewHelpersMixin` and `AsyncViewSetMixin`.
- Pagination resolution from `ActionConfig.pagination_class` and
  `view.get_pagination_class()`, so list endpoints render the
  correct paginated envelope.
- Automatic `many=True` handling on GET list endpoints when a
  pagination class is resolved and the URL is not a detail route.

## Install and setup

Install drf-spectacular through the optional extra:

```bash
pip install drf-restflow[spectacular]
```

Wire the schema class into the DRF settings:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "drf_spectacular",
    "restflow.caching",
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Example API",
    "DESCRIPTION": "An API powered by Restflow.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
```

Mount the schema endpoint and one or both UI views:

```python
# urls.py
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/schema/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
```

Importing `restflow.spectacular` raises `ImportError` if drf-spectacular
is not installed. The error message points at the install command above.

## Request serializer resolution

When the schema generator asks for the request serializer of an
operation, `RestflowAutoSchema` walks the following lookup chain
and returns the first non-None match:

1. `view.action_configs[view.action].request_serializer_class` if an
   action config is registered for the current action and the field is
   set.
2. `view.action_configs[view.action].serializer_class` for the same
   action.
3. `view.get_request_serializer_class()` if the method is callable.
4. drf-spectacular's default lookup, which reads `view.serializer_class`.

If a step raises `AttributeError`, `ImproperlyConfigured`, or `TypeError`
during schema generation, the failure is logged and the chain falls
through to the next step. Errors during request handling itself are
not affected by this safety net.

## Response serializer resolution

The response serializer lookup mirrors the request side:

1. `view.action_configs[view.action].response_serializer_class`.
2. `view.action_configs[view.action].serializer_class`.
3. `view.get_response_serializer_class()` if callable.
4. `view.serializer_class` when `many=True` is needed for a paginated
   list endpoint and no earlier step matched.
5. drf-spectacular's default lookup.

Steps 1 through 4 wrap the serializer in `many=True` automatically
for paginated list responses. The detection rules for `many=True`
are described in the next section.

## List vs detail detection

`many=True` is applied when all of the following hold:

- The HTTP method is GET.
- The view does not look like a detail route. The schema checks the
  resolved `lookup_url_kwarg` or `lookup_field` against the path and
  the path regex. If the kwarg appears in either form, the operation
  is treated as a detail endpoint and `many=True` is not applied.
- A pagination class is resolved.

Pagination resolution itself walks:

1. `view.action_configs[view.action].pagination_class`.
2. `view.get_pagination_class()`.
3. `view.pagination_class`.

If no pagination class resolves, the schema does not assume a list
shape even on GET, so single-item GET endpoints without an ID kwarg
still render as the single-object response.

## Request and response serializer split

Restflow encourages a request/response serializer split: a write
shape used to validate the incoming body, and a read shape used to
serialise the response. The schema renders both correctly without
extra annotations.

```python
from restflow.views import AsyncModelViewSet


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    request_serializer_class = ProductWriteSerializer
    response_serializer_class = ProductReadSerializer
```

POST, PUT, and PATCH request bodies render with
`ProductWriteSerializer`. 2xx responses on every action render with
`ProductReadSerializer`. List endpoints wrap the read serializer in
the paginator envelope when a pagination class is in effect.

Per-action overrides are declared with `ActionConfig`:

```python
from restflow.views import AsyncModelViewSet, ActionConfig
from restflow.pagination import FastPageNumberPagination


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductReadSerializer
    request_serializer_class = ProductWriteSerializer

    action_configs = {
        "list": ActionConfig(
            response_serializer_class=ProductListSerializer,
            pagination_class=FastPageNumberPagination,
        ),
        "create": ActionConfig(
            request_serializer_class=ProductCreateSerializer,
        ),
    }
```

The list operation in the schema uses `ProductListSerializer` as the
item shape and the FastPageNumberPagination envelope. The create
operation uses `ProductCreateSerializer` for the request body and
`ProductReadSerializer` for the response.

## Pagination in the schema

Paginated list endpoints render with the wrapped envelope that
matches the pagination class:

- `PageNumberPagination` and `LimitOffsetPagination` produce the
  standard envelope with `count`, `next`, `previous`, and `results`.
- `FastPageNumberPagination` omits the `count` field. The schema
  reflects that omission, so consumers do not see a property that
  the API never returns.
- `CursorPagination` produces the cursor envelope with `next`,
  `previous`, and `results`, plus the cursor query parameters.

Detail endpoints, action endpoints, and any GET that does not resolve
a pagination class render the bare object shape without an envelope.

## Filter backend integration

`RestflowFilterBackend.get_schema_operation_parameters()` is invoked
by drf-spectacular automatically. Every declared FilterSet field
becomes a query parameter in the OpenAPI schema, including:

- The base field, with the type and constraints derived from the
  field declaration.
- Lookup variants such as `price__gte`, `name__icontains`, and the
  full set generated by `lookups=...` or a lookup category.
- Negation variants with the `!` suffix.
- Ordering parameters when `OrderField` or `Meta.order_fields` is
  declared.

```python
from rest_framework import generics
from restflow.filters import (
    FilterSet, RestflowFilterBackend, StringField, IntegerField,
)


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"])


class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
```

The list endpoint surfaces `name`, `name__icontains`, `name!`,
`name__icontains!`, `price`, `price__gt`, `price__gte`, `price__lt`,
`price__lte`, and the corresponding negation variants in the
generated parameters list.

## Custom action endpoints

drf-spectacular's `@action` decorator works without changes. The
schema follows the regular resolution chain, so the action's own
`serializer_class` (if provided) wins through the standard
mechanism.

```python
from rest_framework.decorators import action
from restflow.views import AsyncModelViewSet


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductReadSerializer

    @action(detail=False, methods=["post"], serializer_class=ImportPayloadSerializer)
    async def bulk_import(self, request):
        ...
```

For per-action serializer or pagination overrides without an
`@action` decorator, declare an entry in `action_configs` keyed by
the action name. The schema picks it up through the same lookup
chain used at runtime.

## Plain APIView support

For views that are not generic viewsets, set the relevant attributes
on the class. The helpers mixin under restflow's `APIView` and
`AsyncAPIView` already exposes `get_request_serializer_class` and
`get_response_serializer_class`, so the schema picks them up
automatically.

```python
from restflow.views import AsyncAPIView


class TokenRefreshView(AsyncAPIView):
    request_serializer_class = TokenRefreshRequestSerializer
    response_serializer_class = TokenResponseSerializer

    async def post(self, request):
        ser = await self.avalidated_serializer()
        result = await refresh_token(ser.validated_data)
        return await self.aserialized_response(result)
```

The POST body in the schema renders with
`TokenRefreshRequestSerializer` and the 2xx response renders with
`TokenResponseSerializer`. No extra schema annotations are required.

`filterset_class` also works on plain `APIView` and `AsyncAPIView`.
The filter query parameters appear in the schema automatically.

```python
from restflow.views import AsyncAPIView
from restflow.filters import FilterSet, StringField


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])


class ProductSearchView(AsyncAPIView):
    serializer_class = ProductSerializer
    filterset_class = ProductFilterSet

    async def get(self, request):
        qs = ProductFilterSet(request=request).filter_queryset(
            Product.objects.all()
        )
        return await self.aserialized_response(qs)
```

The `name` and `name__icontains` parameters appear in the schema
without any additional annotations.

## Customising further

Two extension points cover most cases:

- Subclass `RestflowAutoSchema` and override the resolution hooks for
  project-specific behaviour. The hooks are
  `get_request_serializer`, `get_response_serializers`,
  `restflow_action_config`, `restflow_serializer_class`, and
  `resolved_pagination_class`.
- Use drf-spectacular's `extend_schema` decorator for inline
  overrides on a single operation. `extend_schema` wins over the
  resolution chain, which makes it the right tool for one-off cases
  such as documenting an operation that returns a non-serializer
  shape.

## Common pitfalls

- Forgetting to install the extra. `from restflow.spectacular import
  RestflowAutoSchema` raises `ImportError` with a message that names
  the install command. Install Restflow with the spectacular
  extra to fix it.
- Setting `DEFAULT_SCHEMA_CLASS` to a string path that does not
  match. DRF silently falls back to the default `AutoSchema`, which
  hides every restflow-specific resolution rule. Double-check the
  dotted path.
- Action configs that override `serializer_class` but not
  `response_serializer_class` explicitly. The response uses the
  shared `serializer_class`, which is fine when read and write share
  a shape but wrong when the read shape differs. Set
  `response_serializer_class` on the `ActionConfig` to be explicit.
- Mixing `@extend_schema(responses=...)` and `ActionConfig` for the
  same action. `extend_schema` wins, so an `ActionConfig` change
  goes unreflected in the schema. Pick one approach per operation.
