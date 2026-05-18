# Restflow

A declarative library on top of Django REST Framework. It uses DRF's
serializer and validation infrastructure and adds declarative classes
for the parts of an API that turn into boilerplate over time.

Restflow covers caching, filtering, type-annotated serializers, async
authentication, async permissions, full async view and viewset, async pagination, async throttling, streaming responses, a
unified exception handler, OpenAPI schema generation, and an async
test client and case suite.

Restflow is heavily inspired by [FastAPI](https://fastapi.tiangolo.com/)
and [django-filter](https://django-filter.readthedocs.io). It is built on top of Django REST Framework.


## Motivation

Hi, I am Khan, the author of Restflow. This library was born from
the realities of building APIs in a fast-moving startup environment.
Most of my work involved large database tables, constantly evolving
product requirements, and the challenge of exposing clean, reliable
REST APIs while making sure new developers could onboard quickly and
understand the codebase and business logic as early as possible.

I started with django-filter, which is an excellent and very mature
tool. But as our product grew (and pivoted repeatedly), the FilterSets
became harder to maintain. They were getting long, repetitive, and full
of boilerplate. Some might say this was a skill issue, and honestly, I
agree. But the truth is, I am a lazy developer. I like writing less
code. I like being fast. I like tools that let me declare what I want
instead of wiring everything by hand. Over time, I built small internal
utilities to reduce repetition and make filtering easier. Those tools
worked well, so I compiled them into a proper library so I could reuse
them across projects.

The caching layer comes from the same instinct, applied to a different
problem. In production the part of caching that goes wrong is rarely
the read or the write; it is the cache-key construction and the
invalidation. So Restflow models the cache key as a declarative
class made of small, composable fields, and models invalidation as
rules attached to Django model signals. The function and the rule sit
side by side in the same file, which makes it much easier to keep them
in sync as the schema changes.

Many of the early internal utilities were built from scratch, which
brought some inconsistency. Instead of reinventing the wheel everywhere,
I leaned on what is already battle-tested and borrowed ideas from
different libraries, including FastAPI, django-filter, and
django-ninja. That is how Restflow took its current shape: a
library that does not replace Django REST Framework but extends it with
declarative classes for the parts of an API that turn into boilerplate.

## Installation

```bash
pip install drf-restflow
```

```bash
uv add drf-restflow
```

Two Core Apps of Restflow:

- `restflow.caching` -- registers post-save and post-delete signal
  handlers that drive cache invalidation. Required for any project
  that uses `@cache_result` with `invalidates_on=[...]`.
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

To only use async views, serializers, pagination, installation of these apps are not required.

For the full set of optional extras (redis, celery, django-rq,
django-q, dramatiq, postgres, simplejwt, spectacular) see the
[Installation](getting-started/installation.md) page.

## Caching

The caching layer plugs into Django's cache framework and works with
any configured backend.

!!! note "Cache backend recommendation"
    A small set of features only works on a redis-compatible backend (IE: Redis, Valkey, Dragonfly, keydb, etc):
    `delete_by_prefix()`, `invalidate_all()`, and any
    `InvalidationRule` that needs to wipe a partition rather than a
    single key. Without a redis-compatible backend, those calls raise errors;
    the rest of the caching API keeps working on Django's local-memory
    or database cache. For real-world projects the recommended setup
    is django-redis backed by redis (valkey, keydb, and dragonfly all
    work as drop-in replacements).

A `KeyConstructor` describes how to build a cache key from a function
call. `@cache_result` wraps a function in a `CachedWrapper` and
optionally registers `InvalidationRule` objects against Django model
signals.

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

See the [Caching guide](guide/caching/index.md) for the full API.

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

Each field generates a base parameter, lookup variants, and negation
variants. See the [Filtering guide](guide/filtering/filterset.md) for
the full API.

## Serializers

`Serializer`, `ModelSerializer`, and `HyperlinkedModelSerializer`
subclasses driven by Python type annotations, plus an
`InlineSerializer` factory and async variants (`ais_valid`, `asave`,
`acreate`, `aupdate`, `ato_internal_value`, `arun_validation`).

```python
from restflow.serializers import Serializer, Field, Email


class UserSerializer(Serializer):
    name: str
    age: int
    email: Email
    bio: str | None
    role: str = Field(read_only=True)
```

See the [Serializers guide](guide/serializers/index.md) for the
resolution rules and the async hooks.

## Authentication

`JWTAuthentication` is a fully async JSON Web Token authenticator
backed by PyJWT. It validates signature, expiry, issuer, and audience,
looks up the user with async ORM, and consults a configurable
blacklist on every request. Built-in obtain, refresh, and blacklist
views ship as async APIViews.

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

Async-aware wrappers for `BasicAuthentication`, `TokenAuthentication`,
`SessionAuthentication`, and `RemoteUserAuthentication` are also
provided, plus a `SimpleJWTAuthentication` adapter for projects
already on `djangorestframework-simplejwt`.

See the [Authentication guide](guide/authentication/index.md) for the
full configuration surface.

## Permissions

Async-aware wrapper for Restframework and Django's permission classes . 
Restflow provides
async-native operator classes so combinator branches resolve through
the async hook.

```python
from restflow.permissions import (
    IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
)
from restflow.views import AsyncRetrieveUpdateDestroyAPIView


class AdminOrReadOnly(AsyncRetrieveUpdateDestroyAPIView):
    permission_classes = [
        IsAuthenticated & (IsAdminUser | IsAuthenticatedOrReadOnly)
    ]
```

See the [Permissions guide](guide/permissions/index.md) for the async
async hooks and combinator behaviour.

## Views

A complete async view stack: `AsyncAPIView`, eight generic views, five
model mixins, and the viewset family (`AsyncViewSet`,
`AsyncGenericViewSet`, `AsyncReadOnlyModelViewSet`,
`AsyncModelViewSet`).

```python
from restflow.views import AsyncModelViewSet, ActionConfig
from restflow.permissions import IsAuthenticated, IsAdminUser


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    action_configs = {
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

`ActionConfig` overrides serializer, permission, throttle, parser,
renderer, pagination, and queryset on a per-action basis. `PostFetch`
attaches related rows to a list of base objects after pagination.

See the [Views guide](guide/views/index.md) for the full async pipeline
and per-action override rules.

## Pagination

Async-aware paginators that drive the `apaginate_queryset()` hook on
async views and viewsets. `PageNumberPagination`,
`LimitOffsetPagination`, and `FastPageNumberPagination` use async ORM
iteration directly.

```python
from restflow.pagination import FastPageNumberPagination
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    pagination_class = FastPageNumberPagination
```

See the [Pagination guide](guide/pagination/index.md) for selection
criteria and tuning.

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

See the [Throttling guide](guide/throttling/index.md) for cache-backend
selection and per-action scoping.

## Responses

Three streaming responses for endpoints that produce large or
open-ended payloads.

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

See the [Responses guide](guide/responses/index.md) for buffering,
encoder customisation, and SSE reconnection notes.

## Exception handler

An exception handler that renders every error as a uniform
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

See the [Exception handler guide](guide/exception-handler/index.md)
for the full code list and customisation hooks.

## Spectacular

`RestflowAutoSchema` provides automatic OpenAPI 3 schema generation for
`drf-spectacular` projects. It automatically resolves serializers from
`action_configs`, non-generic `serializer_class` plus the request and
response variants, and pagination classes attached either at the view
level or per action.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}
```

See the [Spectacular guide](guide/spectacular/index.md) for
action-config resolution rules and pagination handling.

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

See the [Testing guide](guide/testing/index.md) for picking the right
base class and writing signal-driven cache invalidation tests.

## Next Steps

- [Installation](getting-started/installation.md): full setup,
  including the cache backend and task brokers.
- [Quick Start](getting-started/quickstart.md): short walkthroughs
  for every feature.
- [Basic Concepts](getting-started/concepts.md): the mental model
  behind every subsystem.
- Guides: [Caching](guide/caching/index.md),
  [Filtering](guide/filtering/filterset.md),
  [Serializers](guide/serializers/index.md),
  [Authentication](guide/authentication/index.md),
  [Permissions](guide/permissions/index.md),
  [Views](guide/views/index.md),
  [Pagination](guide/pagination/index.md),
  [Throttling](guide/throttling/index.md),
  [Responses](guide/responses/index.md),
  [Exception handler](guide/exception-handler/index.md),
  [Spectacular](guide/spectacular/index.md),
  [Testing](guide/testing/index.md).
- [API Reference](api/caching/cache-result.md): generated reference
  for the public API surface.
