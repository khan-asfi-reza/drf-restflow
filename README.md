# Restflow

A declarative library on top of Django REST Framework. It uses DRF's
serializer and validation infrastructure and adds declarative classes for
the parts of an API that turn into boilerplate over time.

The library covers caching, filtering, type-driven serializers, async
authentication, async permissions, a full async view and viewset stack,
async pagination, async throttling, streaming responses, a unified
exception handler, OpenAPI schema generation, and an async test client
and case suite.

Inspired by [FastAPI](https://fastapi.tiangolo.com/) and
[django-filter](https://django-filter.readthedocs.io). Works alongside
DRF rather than replacing it.

Full documentation:
[https://restflow.khanasfireza.dev/](https://restflow.khanasfireza.dev/)

## Table of Contents

- [Motivation](#motivation)
- [Installation](#installation)
- [Caching](#caching)
- [Filtering](#filtering)
- [Serializers](#serializers)
- [Authentication](#authentication)
- [Permissions](#permissions)
- [Views](#views)
- [Pagination](#pagination)
- [Throttling](#throttling)
- [Responses](#responses)
- [Exception handler](#exception-handler)
- [Spectacular](#spectacular)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Motivation

Hi, I am Khan, the author of drf-restflow. This library was born from the
realities of building APIs in a fast-moving startup environment. Most of
my work involved large database tables, constantly evolving product
requirements, and the challenge of exposing clean, reliable REST APIs
while making sure new developers could onboard quickly and understand the
codebase and business logic as early as possible.

I started with django-filter, which is an excellent and very mature tool.
But as our product grew (and pivoted repeatedly), the FilterSets became
harder to maintain. They were getting long, repetitive, and full of
boilerplate. Some might say this was a skill issue, and honestly, I
agree. But the truth is, I am a lazy developer. I like writing less
code. I like being fast. I like tools that let me declare what I want
instead of wiring everything by hand. Over time, I built small internal
utilities to reduce repetition and make filtering easier. Those tools
worked well, so I compiled them into a proper library so I could reuse
them across projects.

The caching layer comes from the same instinct, applied to a different
problem. In production the part of caching that goes wrong is rarely the
read or the write; it is the cache-key construction and the
invalidation. So drf-restflow models the cache key as a declarative
class made of small, composable fields, and models invalidation as
rules attached to Django model signals. The function and the rule sit
side by side in the same file, which makes it much easier to keep them
in sync as the schema changes.

Many of the early internal utilities were built from scratch, which
brought some inconsistency. Instead of reinventing the wheel everywhere,
I leaned on what is already battle-tested and borrowed ideas from
different libraries, including FastAPI, django-filter, and django-ninja.
That is how drf-restflow took its current shape: a library that does not
replace Django REST Framework but extends it with declarative classes for
the parts of an API that turn into boilerplate. There are likely other
libraries that promise similar things or do more, and feedback,
contributions, and constructive criticism are very welcome.

## Installation

```bash
pip install drf-restflow
```

```bash
uv add drf-restflow
```

Restflow ships two Django apps:

- `restflow.caching` -- registers post-save and post-delete signal
  handlers that drive cache invalidation. Required for any project that
  uses `@cache_result` with `invalidates_on=[...]`.
- `restflow.authentication` -- ships the `BlacklistedToken` model used
  by `ModelBlacklistBackend`. Required only when revoking JWTs through
  the model-backed blacklist.

```python
# settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "restflow.caching",
    "restflow.authentication",
]
```

The top-level `restflow` import is a regular Python package and does
not need to appear in `INSTALLED_APPS`.

### Requirements

- Python 3.11 or higher
- Django 3.2 or higher
- Django REST Framework 3.14 or higher
- PyJWT 2.8 or higher (installed automatically; powers the built-in
  JWT authentication)

PostgreSQL is optional and is only required for the postgres-specific
filtering features (full-text search, array fields, trigram similarity,
range fields).

### Optional extras

| Extra | Use case | pip | uv |
| --- | --- | --- | --- |
| `redis` | Cache backend that supports prefix-based invalidation | `pip install drf-restflow[redis]` | `uv add 'drf-restflow[redis]'` |
| `celery` | Run cache invalidation as celery tasks | `pip install drf-restflow[celery]` | `uv add 'drf-restflow[celery]'` |
| `django-rq` | Run cache invalidation through django-rq | `pip install drf-restflow[django-rq]` | `uv add 'drf-restflow[django-rq]'` |
| `django-q` | Run cache invalidation through django-q2 | `pip install drf-restflow[django-q]` | `uv add 'drf-restflow[django-q]'` |
| `dramatiq` | Run cache invalidation through dramatiq | `pip install drf-restflow[dramatiq]` | `uv add 'drf-restflow[dramatiq]'` |
| `postgres` | psycopg2 driver for PostgreSQL filtering features | `pip install drf-restflow[postgres]` | `uv add 'drf-restflow[postgres]'` |
| `postgres-psycopg3` | psycopg3 driver for PostgreSQL filtering features | `pip install drf-restflow[postgres-psycopg3]` | `uv add 'drf-restflow[postgres-psycopg3]'` |
| `simplejwt` | Adapter for djangorestframework-simplejwt | `pip install drf-restflow[simplejwt]` | `uv add 'drf-restflow[simplejwt]'` |
| `spectacular` | OpenAPI schema generation through drf-spectacular | `pip install drf-restflow[spectacular]` | `uv add 'drf-restflow[spectacular]'` |

## Caching

The caching layer plugs into Django's cache framework and works with any
configured backend.

A small set of features only works on a redis-compatible backend:
`delete_by_prefix()`, `invalidate_all()`, and any `InvalidationRule`
that needs to wipe a partition rather than a single key. Anything that
relies on `delete_pattern` falls into this group. Without a
redis-compatible backend, those calls raise; the rest of the caching API
keeps working on Django's local-memory or database cache. Real-world
projects usually want partition wipes, so the recommended setup is
django-redis backed by redis (valkey, keydb, and dragonfly all work as
drop-in replacements).

```bash
pip install drf-restflow[redis]
```

```bash
uv add 'drf-restflow[redis]'
```

```python
# settings.py
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

A `KeyConstructor` describes how to build a cache key from a function
call. Each attribute is a field that pulls a piece of data out of the
call and stringifies it deterministically. `@cache_result` wraps the
function in a `CachedWrapper` and registers `InvalidationRule` objects
against Django model signals.

```python
from django.contrib.auth import get_user_model
from restflow.caching import (
    KeyConstructor, ArgsKeyField, ConstantKeyField, QueryParamsKeyField,
    cache_result, InvalidationRule,
)

User = get_user_model()


class UserKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    version = ConstantKeyField("v", "1")
    page = QueryParamsKeyField(["page", "size"])

    class Meta:
        namespace = "users"


@cache_result(
    key_constructor=UserKey,
    ttl=300,
    invalidates_on=[
        InvalidationRule(
            model=User,
            field_mapping={"user_id": "id"},
            watch_fields=["email"],
            rewarm=True,
        ),
    ],
)
def get_user_payload(user_id: int, request=None):
    return expensive_lookup(user_id)
```

The wrapped function exposes `get_with_metadata`, `refresh`,
`bypass_cache`, `delete_cache`, `delete_by_prefix`, `invalidate_all`,
and the matching `a`-prefixed async methods.

For whole-view HTTP caching, restflow ships `@cache_response`. It caches
the rendered response (content, status code, headers) and rebuilds a
plain `HttpResponse` on a hit, skipping the view body, serializer, and
renderer. It works on class-based view methods (sync and async) and on
DRF's `@api_view` function-based views (sync only).

```python
from restflow.caching import cache_response


class TimelineView(APIView):
    @cache_response(ttl=60)
    def get(self, request):
        return Response({"items": expensive_lookup()})
```

See the [Caching guide](https://restflow.khanasfireza.dev/guide/caching/)
for the full API.

## Filtering

`FilterSet` validates query parameters and applies filters to a Django
queryset. Fields can be declared with type annotations, explicit field
classes, model-based generation, or any mix of those.

```python
from restflow.filters import (
    FilterSet, StringField, IntegerField, BooleanField,
)


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

This declaration generates the following query parameters automatically:

- `name`, `name__icontains` and the negation variants `name!`,
  `name__icontains!`.
- `price`, `price__gt`, `price__gte`, `price__lt`, `price__lte` and
  their negation variants.
- `category`, `category!`, `in_stock`, `in_stock!`.
- `order_by` accepting `price`, `-price`, `name`, `-name`,
  `created_at`, `-created_at`, or comma-separated combinations.

`RestflowFilterBackend` plugs the FilterSet into DRF's filter pipeline
and emits OpenAPI parameters for every declared field.

```python
from rest_framework import generics
from restflow.filters import RestflowFilterBackend


class ProductView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
```

See the [Filtering guide](https://restflow.khanasfireza.dev/guide/filtering/filterset/)
for custom methods, processors, ordering, PostgreSQL features, and the
DRF integration details.

## Serializers

`Serializer`, `ModelSerializer`, and `HyperlinkedModelSerializer`
subclasses driven by Python type annotations, plus an `InlineSerializer`
factory and an async surface (`ais_valid`, `asave`, `acreate`, `aupdate`,
`ato_internal_value`, `arun_validation`).

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

Annotations resolve to DRF fields through `SerializerFieldMap`. Optional
types (`str | None`, `Optional[T]`) become `allow_null=True`,
`Literal[...]` becomes `ChoiceField`, `list[T]` becomes `ListField`, and
nested `Serializer` subclasses nest as expected. See the
[Serializers guide](https://restflow.khanasfireza.dev/guide/serializers/)
for the resolution rules and the async hooks.

## Authentication

`JWTAuthentication` is a fully async JSON Web Token authenticator backed
by PyJWT. It validates signature, expiry, issuer, and audience, looks up
the user with async ORM, and consults a configurable blacklist on every
request. Built-in token obtain, refresh, and blacklist views ship as
async APIViews.

```python
from datetime import timedelta

# settings.py
RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": "change-me-in-production",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    },
}
```

```python
# urls.py
from restflow.authentication.views import (
    TokenObtainView, TokenRefreshView, TokenBlacklistView,
)

urlpatterns = [
    path("auth/token/", TokenObtainView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/blacklist/", TokenBlacklistView.as_view()),
]
```

```python
from restflow.authentication import JWTAuthentication
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    authentication_classes = [JWTAuthentication]
```

Async-aware wrappers for `BasicAuthentication`, `TokenAuthentication`,
`SessionAuthentication`, and `RemoteUserAuthentication` are also
provided, plus a `SimpleJWTAuthentication` adapter for projects already
on `djangorestframework-simplejwt`. See the
[Authentication guide](https://restflow.khanasfireza.dev/guide/authentication/)
for the full configuration surface.

## Permissions

Async-aware permission classes that compose through DRF's existing
`&`, `|`, and `~` operators (with brackets for grouping; precedence
is `~` highest, then `&`, then `|`). Restflow contributes
async-native operator classes so combinator branches resolve through
the async hook , plus async overrides on the
standard permission set so `ahas_permission` is non-blocking. Custom
permissions can implement either the sync or async hook; the dispatch
path picks the async one when present and falls back to a thread for
legacy classes.

```python
from restflow.permissions import (
    IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
)
from restflow.views import AsyncRetrieveUpdateDestroyAPIView


class AdminOrReadOnly(AsyncRetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated & (IsAdminUser | IsAuthenticatedOrReadOnly)]
```

`AllowAny`, `IsAuthenticated`, `IsAdminUser`, `IsAuthenticatedOrReadOnly`,
`DjangoModelPermissions`, `DjangoModelPermissionsOrAnonReadOnly`, and
`DjangoObjectPermissions` ship out of the box. See the
[Permissions guide](https://restflow.khanasfireza.dev/guide/permissions/)
for the async hook contract and combinator behaviour.

## Views

A complete async view stack: `AsyncAPIView`, eight generic views
(`AsyncListAPIView`, `AsyncCreateAPIView`, `AsyncRetrieveAPIView`,
`AsyncUpdateAPIView`, `AsyncDestroyAPIView`, plus the combined
`AsyncListCreate`, `AsyncRetrieveUpdate`, `AsyncRetrieveDestroy`, and
`AsyncRetrieveUpdateDestroy` variants), five model mixins
(`AsyncCreateModelMixin`, `AsyncListModelMixin`, `AsyncRetrieveModelMixin`,
`AsyncUpdateModelMixin`, `AsyncDestroyModelMixin`), and the viewset family
(`AsyncViewSet`, `AsyncGenericViewSet`, `AsyncReadOnlyModelViewSet`,
`AsyncModelViewSet`).

```python
from restflow.views import AsyncModelViewSet, ActionConfig
from restflow.permissions import IsAuthenticated, IsAdminUser
from restflow.pagination import FastPageNumberPagination


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    action_configs = {
        "list": ActionConfig(
            response_serializer_class=ProductListSerializer,
            pagination_class=FastPageNumberPagination,
        ),
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

`ActionConfig` overrides serializer, permission, throttle, parser,
renderer, pagination, and queryset on a per-action basis. `PostFetch`
attaches related rows to a list of base objects after pagination, useful
when `prefetch_related` cannot be used. See the
[Views guide](https://restflow.khanasfireza.dev/guide/views/) for the
full async pipeline and per-action override rules.

## Pagination

Async-aware paginators that drive the `apaginate_queryset()` hook on
async views and viewsets. `PageNumberPagination`, `LimitOffsetPagination`,
and `FastPageNumberPagination` use async ORM iteration directly.
`CursorPagination` falls back to DRF's sync logic via `sync_to_async`.

```python
from restflow.pagination import FastPageNumberPagination
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    pagination_class = FastPageNumberPagination
```

`FastPageNumberPagination` skips the `COUNT(*)` query and decides whether
a next page exists based on whether the current page is full. That
matters on huge tables where a count scan dominates the request budget.
See the [Pagination guide](https://restflow.khanasfireza.dev/guide/pagination/)
for selection criteria and tuning.

## Throttling

Async-aware throttle classes that use Django's async cache to avoid
blocking the event loop on rate-limit checks. `AnonRateThrottle`,
`UserRateThrottle`, `ScopedRateThrottle`, and a `SimpleRateThrottle`
base class are provided.

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

See the [Throttling guide](https://restflow.khanasfireza.dev/guide/throttling/)
for cache-backend selection and per-action scoping.

## Responses

Three streaming responses for endpoints that produce large or open-ended
payloads.

```python
from restflow.responses import (
    StreamingJSONListResponse, NDJSONResponse, SSEResponse,
)


async def products(request):
    async def items():
        async for row in Product.objects.all():
            yield {"id": row.id, "name": row.name}
    return StreamingJSONListResponse(items())
```

`StreamingJSONListResponse` emits a single JSON array element-by-element.
`NDJSONResponse` emits one JSON object per line. `SSEResponse` formats
items as Server-Sent Events with `data`, `event`, `id`, and `retry`
fields. See the [Responses guide](https://restflow.khanasfireza.dev/guide/responses/)
for buffering, encoder customisation, and SSE reconnection notes.

## Exception handler

A drop-in DRF exception handler that renders every error as a uniform
envelope with a stable error code, message, and details payload.

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

Every error -- DRF, Django, or `restflow.exceptions.APIException` --
is mapped to `{"error": {"code": "...", "message": "...", "details": {...}}}`
with stable codes for clients to branch on. See the
[Exception handler guide](https://restflow.khanasfireza.dev/guide/exception-handler/)
for the full code list and customisation hooks.

## Spectacular

`RestflowAutoSchema` is a drop-in replacement for `drf-spectacular`'s
default schema generator. It resolves serializers from `action_configs`,
non-generic `serializer_class` plus the request and response variants,
and pagination classes attached either at the view level or per action.

```bash
pip install drf-restflow[spectacular]
```

```bash
uv add 'drf-restflow[spectacular]'
```

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}
```

OpenAPI parameters from `RestflowFilterBackend` flow through the same
schema. See the [Spectacular guide](https://restflow.khanasfireza.dev/guide/spectacular/)
for action-config resolution rules and pagination handling.

## Testing

`AsyncAPIClient` and `AsyncAPIRequestFactory` send ASGI requests to
restflow async views. Four test case bases (`AsyncAPISimpleTestCase`,
`AsyncAPITestCase`, `AsyncAPITransactionTestCase`,
`AsyncAPILiveServerTestCase`) wire those into Django's test runner.

```python
from restflow.test import AsyncAPIClient, AsyncAPITestCase


class TestProducts(AsyncAPITestCase):
    async def test_list(self):
        client = AsyncAPIClient()
        response = await client.get("/api/products/")
        assert response.status_code == 200
```

`force_authenticate(request, user=...)` bypasses the authenticator chain
in unit tests. See the [Testing guide](https://restflow.khanasfireza.dev/guide/testing/)
for picking the right base class and writing signal-driven cache
invalidation tests.

## Contributing

Contributions are welcome. See the
[contributing guide](https://restflow.khanasfireza.dev/contributing/)
for the development workflow, code conventions, and test setup.

## License

BSD 3-Clause License. See [LICENSE](LICENSE).
