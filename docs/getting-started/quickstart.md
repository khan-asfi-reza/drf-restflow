# Quick Start
Restflow quickstart guide.

## Prerequisites

- Django and DRF installed and configured.
- The relevant restflow Django apps in `INSTALLED_APPS`. See
  [Installation](installation.md) for the full setup.

## Caching

The caching layer plugs into Django's cache framework. The
recommended setup is django-redis backed by redis (valkey, keydb, and
dragonfly also work). See the
[Installation page](installation.md#cache-backend) for the install
line and the `CACHES` snippet.

### Cache an expensive function

Wrap a function with `@cache_result`. The first call computes the
value and stores it in the cache; subsequent calls return the cached
value.

```python
# app/services.py
from django.contrib.auth import get_user_model
from restflow.caching import (
    KeyConstructor, ArgsKeyField, ConstantKeyField,
    cache_result, InvalidationRule,
)

User = get_user_model()


class UserPayloadKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    version = ConstantKeyField("v", "1")

    class Meta:
        namespace = "users"


@cache_result(
    key_constructor=UserPayloadKey,
    ttl=300,
    invalidates_on=[
        InvalidationRule(
            model=User,
            field_mapping={"user_id": "id"},
            watch_fields=["email", "username"],
        ),
    ],
)
def get_user_payload(user_id: int):
    user = User.objects.get(pk=user_id)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }
```

`partition=True` on `user` puts the user id in the cache key prefix.
`watch_fields` makes the rule fire only when `email` or `username`
actually changes on save. `ttl=300` expires entries after five
minutes.

Note: To efficiently use `watch_fields`, make sure to pass
`update_fields` to model `save` method, e.g.:

```python
model.objects.save(update_fields=["field_name"]...)
```

Instead of:

```python
model.objects.save(...)
```

### Use the wrapped function

```python
# app/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .services import get_user_payload


@api_view(["GET"])
def user_view(request, user_id):
    return Response(get_user_payload(user_id))
```

The first request runs `get_user_payload`; the next requests within
minutes return the cached value. When the underlying user is
saved with a changed email, the registered `InvalidationRule` drops
the cached entry and the next request recomputes.

### Surface the cache status

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from restflow.caching import set_response_cache_header
from .services import get_user_payload


@api_view(["GET"])
def user_view(request, user_id):
    value, metadata = get_user_payload.get_with_metadata(user_id)
    response = Response(value)
    return set_response_cache_header(response, metadata)
```

The response carries `X-Cache-status` (`HIT`, `MISS`, `STALE`,
`BYPASS`, or `REFRESH`), `X-Cached-at`, and `X-Cache-reset-at`.

See the [Caching Guide](../guide/caching/index.md) for the full API.

## Filtering

`FilterSet` validates query parameters and applies filters to a
Django queryset.

### Declare a FilterSet

```python
# app/filters.py
from restflow.filters import (
    FilterSet, StringField, IntegerField,
)
from .models import Product


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"])
    category: str
    in_stock: bool

    class Meta:
        model = Product
        order_fields = [
            ("price", "price"),
            ("name", "name"),
            ("created_at", "created_at"),
        ]
```

### Plug it into a DRF view

```python
# app/views.py
from restflow.views import AsyncListAPIView
from restflow.filters import RestflowFilterBackend
from .filters import ProductFilterSet
from .models import Product
from .serializers import ProductSerializer


class ProductListView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
```

### Regular AsyncAPIView

```python
# app/views.py
from restflow.views import AsyncAPIView
from restflow.filters import RestflowFilterBackend
from .filters import ProductFilterSet
from .models import Product
from .serializers import ProductSerializer


class ProductAPIView(AsyncAPIView):
    serializer_class = ProductSerializer
    
    async def get(self, request):
        qs = Product.objects.all()
        qs = await ProductFilterSet(request).afilter_queryset(qs)
        return await self.aserialized_response(qs, many=True)
```


Sample requests:

```bash
GET /api/products/?name__icontains=laptop&price__lte=1000&order_by=-price
GET /api/products/?category!=electronics
```

See the [Filtering Guide](../guide/filtering/filterset.md) for the full API.

## Serializers

Type-annotated serializers resolve fields from Python annotations.

```python
from restflow.serializers import (
    Serializer, ModelSerializer, Field, Email,
)


class UserSerializer(Serializer):
    name: str
    age: int
    email: Email
    bio: str | None
    role: str = Field(read_only=True)


class UserModelSerializer(ModelSerializer):
    full_name: str

    class Meta:
        model = User
        fields = ["id", "username"]
```

`Optional[T]` and `T | None` become `allow_null=True`.
`Literal[...]` becomes `ChoiceField`. `list[T]` becomes `ListField`.
The async surface (`ais_valid`, `asave`, `acreate`, `aupdate`) is
available on every serializer.

See the [Serializers Guide](../guide/serializers/index.md) for the resolution rules.

## Authentication

JWT authentication ships with built-in obtain, refresh, and blacklist
views and works on any Django auth backend.

### Configure a signing key

```python
# settings.py
from datetime import timedelta

RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": "change-me-in-production",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    },
}
```

### Mount the token views

```python
# urls.py
from django.urls import path
from restflow.authentication.views import (
    TokenObtainView, TokenRefreshView, TokenBlacklistView,
)

urlpatterns = [
    path("auth/token/", TokenObtainView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/blacklist/", TokenBlacklistView.as_view()),
]
```

### Protect a view

```python
from restflow.authentication import JWTAuthentication
from restflow.permissions import IsAuthenticated
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
```

Sample requests:

```bash
curl -X POST http://localhost:8000/auth/token/ \
    -H "Content-Type: application/json" \
    -d '{"username": "khan", "password": "..."}'
# {"access": "eyJ...", "refresh": "eyJ..."}

curl http://localhost:8000/api/products/ \
    -H "Authorization: Bearer eyJ..."
```

See the [Authentication Guide](../guide/authentication/index.md) for the configuration surface and the SimpleJWT adapter.

## Permissions

Async compatible permission classes can be combined with `&`, `|`, and `~`.

```python
from restflow.permissions import (
    IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
)
from restflow.views import AsyncRetrieveUpdateDestroyAPIView


class ProductDetail(AsyncRetrieveUpdateDestroyAPIView):
    permission_classes = [
        IsAuthenticated & (IsAdminUser | IsAuthenticatedOrReadOnly)
    ]
```

Custom async permissions implement `ahas_permission`:

```python
from restflow.permissions import BasePermission


class IsOwner(BasePermission):
    async def ahas_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id
```

See the [Permissions Guide](../guide/permissions/index.md) for async hooks.

## Views

Async views, generic views, mixins, and viewsets, all driven by an
async dispatch loop.

```python
from restflow.views import AsyncModelViewSet, ActionConfig
from restflow.permissions import IsAuthenticated, IsAdminUser
from restflow.pagination import FastPageNumberPagination


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = FastPageNumberPagination
    action_configs = {
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

See the [Views Guide](../guide/views/index.md) for the async pipeline.

## Pagination

Async paginators that provides the `apaginate_queryset()` hook on async
views.

```python
from restflow.pagination import (
    PageNumberPagination, FastPageNumberPagination,
)
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination


class HugeProductView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = FastPageNumberPagination
```

`FastPageNumberPagination` skips the `COUNT(*)` query and is
appropriate when the table is large enough that counting is expensive.

See the [Pagination Guide](../guide/pagination/index.md) for selection criteria and tuning.

## Throttling

Async throttles backed by Django's async cache.

```python
from restflow.throttling import AnonRateThrottle, UserRateThrottle
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
```

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}
```

See the [Throttling Guide](../guide/throttling/index.md) for cache-backend selection.

## Responses

Stream large payloads with streaming responses.

```python
from restflow.responses import StreamingJSONListResponse


async def products(request):
    async def items():
        async for row in Product.objects.all():
            yield {"id": row.id, "name": row.name}
    return StreamingJSONListResponse(items())
```

`NDJSONResponse` produces one JSON object per line. `SSEResponse`
produces Server-Sent Events.

See the [Responses Guide](../guide/responses/index.md) for buffering and encoder customisation.

## Exception handler

Render every error in a uniform format with a stable error code.

```python
# settings.py
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "restflow.exceptions.exception_handler",
}
```

```python
from restflow.exceptions import APIException, ErrorCode


class ProductLockedException(APIException):
    code = ErrorCode.CONFLICT.value
    status_code = 409
    default_detail = "The product is locked for editing."
```

Every error becomes:

```json
{
  "error": {
    "code": "conflict",
    "message": "The product is locked for editing.",
    "details": {}
  }
}
```

See the [Exception handler Guide](../guide/exception-handler/index.md) for the full code list and customisation hooks.

## Spectacular

Generate OpenAPI schemas through drf-spectacular.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Example API",
    "VERSION": "1.0.0",
}
```

```python
# urls.py
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView,
)

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
]
```

See the [Spectacular Guide](../guide/spectacular/index.md) for action-config and pagination resolution rules.

## Testing

`AsyncAPIClient` and the four `AsyncAPI*TestCase` classes wire async
testing into Django's test runner.

```python
from restflow.test import AsyncAPIClient, AsyncAPITestCase


class TestProducts(AsyncAPITestCase):
    async def test_list(self):
        client = AsyncAPIClient()
        response = await client.get("/api/products/")
        assert response.status_code == 200
```

`force_authenticate(request, user=...)` bypasses the authenticator
chain in unit tests.

See the [Testing Guide](../guide/testing/index.md) for picking the right base class.
