# Basic Concepts

Restflow is a declarative library on top of Django REST Framework.
It does not replace DRF; it reuses DRF's serializer and validation
infrastructure and adds declarative classes for the parts of an API
that turn into boilerplate over time, it also provides async compatibility.


## Core philosophy

1. **Declarative over imperative.** Describe what the cache key looks
   like, what filters the API accepts, or what fields a serializer
   exposes; the library handles the rest.
2. **Type-safe.** Type annotations on a `FilterSet` or a `Serializer`
   are enough to build a validated, type-converted field. Cache key
   fields stringify deterministically so equivalent calls hit the
   same key.
3. **Less boilerplate.** Common patterns (lookup variants, negation,
   partition wipes, signal-driven invalidation, async dispatch,
   per-action overrides, uniform error envelopes).
4. **DRF-aligned.** Filtering plugs into DRF's filter backend
   pipeline. Caching plugs into Django's cache framework. Views,
   permissions, throttles, and pagination keep DRF's class shapes.
5. **Async-first additions.** Every feature added on top of DRF
   ships with an async surface so the components compose cleanly
   under `AsyncAPIView` and the async viewset family.

## Caching

The caching subsystem is built around three core components:
1. Cache key
2. Wrapper
3. Invalidation rule

### Cache key fields

A cache key pulls one piece of data out of a function call (an
argument, a request attribute, a query parameter, a model schema)
and turns it into a stable string. The available fields are:

- `ConstantKeyField(name, value)` -- a fixed pair on every call.
  Can be used for environment labels and feature-flag stamps.
- `ArgsKeyField(name)` -- captures the named function argument by
  inspecting the signature.
- `RequestValueKeyField(name, attr)` -- reads a value off the
  request using a dotted path such as `"user.id"`.
- `QueryParamsKeyField(names)` -- captures the listed query-string
  parameters from `request.query_params`.
- `DjangoModelKeyField(model)` -- fingerprints a Django model's
  schema so a migration that adds, removes, or retypes a field
  invalidates the cache automatically.
- `DrfSerializerKeyField(serializer_class)` -- fingerprints a DRF
  serializer's shape so changing the serializer invalidates the
  cache automatically.

Every key field accepts `partition=True`. Partition fields move into
the cache key prefix. Entries that share a prefix can be wiped
together with `delete_by_prefix(...)` (requires a redis-compatible
backend).

The cache key contains four parts:
1. Namespace
2. Version
3. Function Identifier / Cache Identifier
4. Partition Fields 
5. Suffix

Namespace, version, function idetifier / cache identifier and partition fields together forms the cache prefix. Suffix forms the cache suffix.

For example:
```python
class UserKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    environment = ConstantKeyField("v", "production", partition=True)
    scope = ArgsKeyField("scope")


    class Meta:
        namespace = "users"
```

For a function call
```python

def get_user_data(
    user_id: int,
    scope: str,
):
    return some_expensive_query()

# Function call
get_user_data(user_id=1, scope="full")
```
Cache key structure: `<namespace>::<function-id>::<partition>::<suffix>`

The cache key will be `users::get_user_data::1::production::full`

If `scope = ArgsKeyField("scope", hash=True)` 
then cache key will be `users::get_user_data::1::production::c04bc36a5d6449b7a47e181979c48529`


### Key constructors

A `KeyConstructor` is a class whose attributes are key fields. The
constructor builds the full cache key by joining the namespace, the
function identifier, the partition prefix, and the suffix of
non-partition fields.

```python
from restflow.caching import (
    KeyConstructor, ArgsKeyField, ConstantKeyField,
)


class UserKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    version = ConstantKeyField("v", "1")

    class Meta:
        namespace = "users"
```

For one-off use, `InlineKeyConstructor({"user": ArgsKeyField(...)})`
builds a constructor class from a plain dict. When `@cache_result`
runs without an explicit key constructor, `DefaultKeyConstructor`
captures every positional and keyword argument.

### cache_result and CachedWrapper

`@cache_result` wraps a function so calls hit the cache before
running the function. The wrapped function becomes a `CachedWrapper`
instance with a callable plus extra control methods.

```python
from restflow.caching import cache_result


@cache_result(key_constructor=UserKey, ttl=300)
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)


# Normal call, hits the cache.
data = get_user_payload(42)

# Pull the cache metadata along with the value.
data, metadata = get_user_payload.get_with_metadata(42)
metadata["cache_status"]  # "HIT" / "MISS" / "STALE" / "BYPASS" / "REFRESH"

# Re-run and re-cache.
data = get_user_payload.refresh(42)

# Skip the cache entirely.
data = get_user_payload.bypass_cache(42)

# Drop one entry.
get_user_payload.delete_cache(42)

# Drop every entry that shares the user_id partition.
# Useful when multiple cached data depends on one row / or one object. 
get_user_payload.delete_by_prefix(user_id=42)

# Drop every entry the wrapper has ever written.
get_user_payload.invalidate_all()
```

Async functions get the same surface with an `a` prefix
(`aget_with_metadata`, `arefresh`, `abypass_cache`, `adelete_cache`,
`adelete_by_prefix`, `ainvalidate_all`). Calling an async-wrapped
function returns a coroutine; calling a sync-wrapped function
returns the value.

### InvalidationRule

`InvalidationRule` connects a Django model's `post_save` and
`post_delete` signals to the wrapper. The most common shape is a
`field_mapping` from kwarg names on the wrapped function to fields
on the saved model.

```python
from restflow.caching import InvalidationRule


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
def get_user_payload(user_id: int):
    return expensive_lookup(user_id)
```

`watch_fields` makes the rule fire only when a watched field
actually changes on save. `rewarm=True` re-runs the function instead
of dropping the entry, which keeps response latency low after a
write. For derived values, multiple invalidations per save, or
custom routing, pass a callable as `invalidator` in place of
`field_mapping`.

Note: To make sure `watch_fields` work, pass the updated field name in 
`objects.save(update_fields=["field_name"])`

### Dispatchers

Each `InvalidationRule` decides where the invalidation work runs
through its `dispatcher` attribute. The choices are `inline`
(default, runs synchronously inside `transaction.on_commit`),
`threadpool`, `asyncio`, `celery`, `django_rq`, `django_q`, and
`dramatiq`.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

See the [Dispatchers guide](../guide/caching/dispatchers.md) for the
broker setup steps.

## Filtering

The filtering subsystem is built around `FilterSet`.

### FilterSet

A `FilterSet` defines filterable fields, validates query parameters
through DRF's validators, and applies the resulting filters to a
Django queryset. When called with a request, the FilterSet extracts
query parameters, validates them, builds a `Q` object per field,
combines them with the configured operator, and applies the result
to the queryset.

```python
from restflow.filters import FilterSet


class ProductFilterSet(FilterSet):
    name: str
    price: int
    in_stock: bool

    class Meta:
        model = Product
```

### Field declaration styles

Fields can be declared with type annotations, explicit field
classes, model-based generation, or any mix. The priority is
explicit declarations, then annotations, then model fields.

```python
from restflow.filters import StringField, IntegerField


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])  # explicit
    description: str                             # annotation
    in_stock: bool                               # annotation

    class Meta:
        model = Product
        fields = ["price"]                       # model-derived
        extra_kwargs = {"price": {"min_value": 0}}
```

### filter_by and db_field

Two parameters control how a field maps to the ORM:

- `filter_by` is the lookup expression applied to the queryset. It
  accepts a Django ORM string (`"name__icontains"`), a callable that
  returns a `Q` object, or a callable that returns a filter dict.
- `db_field` is the column name used when generating lookup
  variants. It defaults to the field name on the FilterSet.

```python
class ProductFilterSet(FilterSet):
    # query string parameter name "product_price" maps to ORM column "price"
    product_price = IntegerField(db_field="price", lookups=["comparison"])
```

### Lookup categories and variants

`lookups` accepts individual ORM lookup names (`"icontains"`,
`"gte"`) or category names that expand into a group:

| Category | Lookups |
| --- | --- |
| `basic` | `exact`, `in`, `isnull` |
| `text` | `icontains`, `contains`, `startswith`, `endswith`, `iexact` |
| `comparison` | `gt`, `gte`, `lt`, `lte` |
| `date` | `date`, `year`, `month`, `day`, `week`, `week_day`, `quarter` |
| `time` | `time`, `hour`, `minute`, `second` |
| `postgres` | `search`, `trigram_similar`, `unaccent` |
| `pg_array` | `contains`, `overlaps`, `contained_by` |

Each base field automatically generates a base parameter, lookup
variants, and negation variants:

```python
price = IntegerField(lookups=["gte", "lte"])
# accepts: price, price__gte, price__lte,
#          price!, price__gte!, price__lte!
```

Negation is opt-out per field (`allow_negate=False`) and globally
through `Meta.allow_negate=False`.

### Operators and processors

`Meta.operator` controls how field-level `Q` objects combine
(`AND` / `OR` / `XOR`).

`Meta.preprocessors` runs before filtering; useful for permission
filtering, soft-delete exclusion, query optimisation, or
annotations.

`Meta.postprocessors` runs after filtering; useful for default
ordering, distinct enforcement, or logging.

```python
class ProductFilterSet(FilterSet):
    name: str

    class Meta:
        model = Product
        operator = "OR"
        preprocessors = [exclude_archived, apply_tenant_scope]
        postprocessors = [ensure_distinct]
```

### Type annotation mapping

| Python type | Field type |
| --- | --- |
| `str` | `StringField` |
| `int` | `IntegerField` |
| `float` | `FloatField` |
| `bool` | `BooleanField` |
| `decimal.Decimal` | `DecimalField` |
| `datetime.date` | `DateField` |
| `datetime.datetime` | `DateTimeField` |
| `datetime.time` | `TimeField` |
| `datetime.timedelta` | `DurationField` |
| `Email` (NewType) | `EmailField` |
| `IPAddress` (NewType) | `IPAddressField` |
| `list[T]` | `ListField` with `T`-typed child |
| `Literal[...]` | `ChoiceField` |
| `Optional[T]` / `T \| None` | corresponding field for `T` |

### DRF integration

`RestflowFilterBackend` plugs the FilterSet into DRF's filter
pipeline and generates OpenAPI parameters for every field. See the
[DRF integration guide](../guide/filtering/integration.md).

## Serializers

restflow's serializers extend DRF's classes with annotation-driven
fields and an async surface.

### Type-annotated fields

```python
from typing import Literal
from restflow.serializers import Serializer, Field, Email


class UserSerializer(Serializer):
    name: str
    age: int
    email: Email
    bio: str | None
    role: Literal["admin", "user"]
    tags: list[str]
    extra: str = Field(write_only=True)
```

Annotation resolution follows `SerializerFieldMap`. Optional types
(`T | None`, `Optional[T]`) become `allow_null=True`. `Literal[...]`
becomes `ChoiceField` with the literal values as choices. `list[T]`
becomes `ListField` with the child type resolved from `T`. A nested
`Serializer` subclass nests as expected.

### ModelSerializer

`ModelSerializer` reads `Meta.model` and merges annotated names into
`Meta.fields` automatically:

```python
from restflow.serializers import ModelSerializer


class UserModelSerializer(ModelSerializer):
    full_name: str  # auto-merged into Meta.fields

    class Meta:
        model = User
        fields = ["id", "username"]
```

`HyperlinkedModelSerializer` is the URL-style variant.

### InlineSerializer

`InlineSerializer` builds a serializer class on the fly from a dict
of fields and an optional model. Useful for ad-hoc nested shapes
inside another serializer.

```python
from restflow.serializers import InlineSerializer


AddressSerializer = InlineSerializer(
    name="Address",
    fields={"city": str, "country": str, "zip": str},
)
```

### Async surface

Every restflow serializer ships `ais_valid`, `asave`, `acreate`,
`aupdate`, `ato_internal_value`, and `arun_validation`. The sync
methods refuse async user callables (`validate_<name>`, `validate`,
`create`, `update`) so unintended awaitable returns surface early.

```python
async def view(request):
    serializer = UserSerializer(data=request.data)
    await serializer.ais_valid(raise_exception=True)
    user = await serializer.asave()
    return Response(serializer.data)
```

## Authentication

The authentication subsystem covers async-aware wrappers for DRF's
standard authenticators (`BasicAuthentication`, `TokenAuthentication`,
`SessionAuthentication`, `RemoteUserAuthentication`) plus a
fully-built JWT stack.

### Tokens

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

`AccessToken` and `RefreshToken` are signed JWTs. Access tokens are
short-lived and sent on every request. Refresh tokens are long-lived
and used to get new access tokens through the
`refresh_token.access_token` property.

```python
from restflow.authentication import AccessToken, RefreshToken

access = AccessToken.for_user(user)
refresh = RefreshToken.for_user(user)
new_access = refresh.access_token  # generates a new access token
```

### Token views

`TokenObtainView`, `TokenRefreshView`, and `TokenBlacklistView` are
async APIViews that handle the obtain, refresh, and blacklist flows:

```python
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

### Blacklist backends

`CacheBlacklistBackend` (default) stores entries in Django's cache
with a TTL matching the remaining token lifetime.
`ModelBlacklistBackend` persists entries in the `BlacklistedToken`
Django model (requires `restflow.authentication` in
`INSTALLED_APPS`).

### Protecting a view

```python
from restflow.authentication import JWTAuthentication
from restflow.permissions import IsAuthenticated
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
```

### SimpleJWT adapter

For projects already using `djangorestframework-simplejwt`, the
optional `simplejwt` extra provides
`restflow.authentication.simplejwt.SimpleJWTAuthentication`, which
inherits the simplejwt validation logic and adds the async user
lookup needed by the async dispatch loop.

## Permissions

Permission classes use the async dispatch surface
(`ahas_permission`, `ahas_object_permission`) when available.
Standard permissions ship with explicit async overrides so they
avoid a thread hop. Custom permissions can implement either the
sync or async hook.

```python
from restflow.permissions import BasePermission


class IsOwner(BasePermission):
    async def ahas_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id
```

### Combinators

Async compatible boolean operators for permissions.

```python
from restflow.permissions import (
    IsAuthenticated, IsAdminUser, IsAuthenticatedOrReadOnly,
)


permission_classes = [
    IsAuthenticated & (IsAdminUser | IsAuthenticatedOrReadOnly)
]
```

## Views

The view stack is fully async compatible.

### APIView and AsyncAPIView

`APIView` extends DRF's `APIView` with serializer and pagination
helpers (`validated_serializer`, `serialized_response`,
`paginated_response`). `AsyncAPIView` swaps the dispatch loop for an
async one and exposes async variants
(`avalidated_serializer`, `aserialized_response`,
`apaginated_response`).

```python
from restflow.views import AsyncAPIView


class CreateOrderView(AsyncAPIView):
    request_serializer_class = OrderCreateSerializer
    response_serializer_class = OrderSerializer

    async def post(self, request):
        serializer = await self.avalidated_serializer()
        order = await Order.objects.acreate(**serializer.validated_data)
        return await self.aserialized_response(order, status=201)
```

### Generic views

Eight async generic views map to the standard CRUD shapes:
`AsyncListAPIView`, `AsyncCreateAPIView`, `AsyncRetrieveAPIView`,
`AsyncUpdateAPIView`, `AsyncDestroyAPIView`, plus the combined
`AsyncListCreateAPIView`, `AsyncRetrieveUpdateAPIView`,
`AsyncRetrieveDestroyAPIView`, and
`AsyncRetrieveUpdateDestroyAPIView`.

### Mixins

Five async model mixins (`AsyncCreateModelMixin`,
`AsyncListModelMixin`, `AsyncRetrieveModelMixin`,
`AsyncUpdateModelMixin`, `AsyncDestroyModelMixin`) compose into
custom views.

### Viewsets

`AsyncViewSet`, `AsyncGenericViewSet`,
`AsyncReadOnlyModelViewSet`, and `AsyncModelViewSet` mirror DRF's
viewset family on the async pipeline.

### ActionConfig

Per-action override for any viewset attribute that varies between
list, retrieve, create, update, partial_update, and destroy. Every
field on `ActionConfig` is optional and falls through to the
class-level attribute when unset.

```python
from restflow.views import AsyncModelViewSet, ActionConfig
from restflow.permissions import IsAdminUser
from restflow.pagination import FastPageNumberPagination


class ProductViewSet(AsyncModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    action_configs = {
        "list": ActionConfig(
            response_serializer_class=ProductListSerializer,
            pagination_class=FastPageNumberPagination,
        ),
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

### PostFetch

Attaches related rows to a list of base objects after they have been
fetched or paginated. Useful when `prefetch_related` cannot express
the join (denormalised counts, JSON aggregations, computed columns).
`fetch` runs in sync code; `afetch` iterates the secondary queryset
asynchronously.

```python
from restflow.views import PostFetch


review_fetch = PostFetch(
    queryset=Review.objects.all(),
    to_attr="latest_review",
    values=["id", "rating", "created_at"],
    order_by=("-created_at",),
    limit=1,
    product_id="id",
)
```

## Pagination

Pagination classes drive the `apaginate_queryset()` hook on async
views and viewsets.

- `PageNumberPagination` -- standard page numbering. Uses async ORM
  for `count()` and async iteration over the page slice.
- `LimitOffsetPagination` -- explicit limit and offset window.
- `CursorPagination` -- cursor-based pagination, stable across
  inserts. Inherits DRF's sync logic; the async surface defaults to
  `sync_to_async`.
- `FastPageNumberPagination` -- page numbering that skips the
  `COUNT(*)` query. Decides whether a next page exists by checking
  whether the current page is full. No total count is
  returned.

```python
from restflow.pagination import FastPageNumberPagination
from restflow.views import AsyncListAPIView


class ProductView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = FastPageNumberPagination
```

## Throttling

Throttle classes use Django's async cache to record request
timestamps without blocking the event loop.

- `AnonRateThrottle` -- limits anonymous requests by client IP.
- `UserRateThrottle` -- limits authenticated requests by user id.
- `ScopedRateThrottle` -- per-action limits driven by
  `view.throttle_scope`.
- `SimpleRateThrottle` -- base class for custom throttles. Override
  `get_cache_key` to control the key strategy.

Rates are configured through DRF's `DEFAULT_THROTTLE_RATES` setting
and follow the standard `"<count>/<period>"` syntax.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "uploads": "10/min",
    },
}
```

## Responses

Three streaming responses cover endpoints that produce large or
open-ended payloads.

- `StreamingJSONListResponse` -- emits a single JSON array, one
  element at a time.
- `NDJSONResponse` -- emits newline-delimited JSON, one object per
  line.
- `SSEResponse` -- emits Server-Sent Events with `data`, `event`,
  `id`, and `retry` fields.

```python
from restflow.responses import SSEResponse


async def heartbeat(request):
    async def events():
        async for tick in clock():
            yield {"event": "tick", "data": {"at": tick}}
    return SSEResponse(events())
```

The responses accept any async iterable and use Django's
`StreamingHttpResponse` underneath.

## Exception handler

`restflow.exceptions.exception_handler` exception handler that renders every error in a uniform format:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {"email": ["Enter a valid email."]}
  }
}
```

```python
# settings.py
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "restflow.exceptions.exception_handler",
}
```

`ErrorCode` is a stable string enum (`not_authenticated`,
`authentication_failed`, `permission_denied`, `validation_error`,
`parse_error`, `not_found`, `method_not_allowed`,
`unsupported_media_type`, `not_acceptable`, `throttled`, `conflict`,
`internal_error`, `service_unavailable`).

Custom application errors subclass `restflow.exceptions.APIException`:

```python
from restflow.exceptions import APIException, ErrorCode


class ProductLockedException(APIException):
    code = ErrorCode.CONFLICT.value
    status_code = 409
    default_detail = "The product is locked for editing."


raise ProductLockedException(details={"locked_by": user.id})
```

## Spectacular

`RestflowAutoSchema` extends `drf-spectacular`'s schema to support restflow's specific features. It resolves serializers
from action configs, the request and response serializer split on
non-generic views, and pagination classes attached either at the
view level or per action. OpenAPI parameters from
`RestflowFilterBackend` flow through the same schema.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}
```

## Testing

`AsyncAPIClient` and `AsyncAPIRequestFactory` send ASGI requests to
restflow async views. Four test case bases mirror Django's
hierarchy:

- `AsyncAPISimpleTestCase` -- no database transaction.
- `AsyncAPITestCase` -- wraps each test in a transaction that rolls
  back at teardown.
- `AsyncAPITransactionTestCase` -- real transactions; required for
  signal-driven cache invalidation tests where
  `transaction.on_commit` must fire.
- `AsyncAPILiveServerTestCase` -- spins up a live server in a
  thread.

`force_authenticate(request, user=...)` bypasses the authenticator
chain in unit tests.

```python
from restflow.test import AsyncAPIClient, AsyncAPITestCase


class TestProducts(AsyncAPITestCase):
    async def test_list_returns_200(self):
        client = AsyncAPIClient()
        response = await client.get("/api/products/")
        assert response.status_code == 200
```

## Next steps

- [Quick Start](quickstart.md): short walkthroughs for each feature.
- Guides hold the comprehensive API reference for each subsystem,
  one click deeper.
