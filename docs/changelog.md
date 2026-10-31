# Changelog

All notable changes to drf-restflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2026-10-31

### Fixed

- Cache invalidation rules register once instead of twice. `auto_discover()` marked discovery finished before importing the cache modules, so every `@cache_result` rule was registered by its decorator on import and then again from the pending list. Each save on a watched model ran its invalidation set twice, and a rule declared with `rewarm=True` recomputed and reserialized its cached value twice per write.

  ```python
  # one @cache_result rule, two registrations before this release
  CacheRegister.auto_discover()
  len(CacheRegister._rules)  # 2
  ```

- `watch_fields` no longer ignores a plain `save()`. Django reports `update_fields=None` for a full save, meaning every column was written, and the registry read that as "none of the watched fields changed". A rule with `watch_fields` only invalidated for `save(update_fields=[...])`, so an ordinary save left its cached value in place for the rest of the entry's lifetime. A save that names no fields now invalidates, since any watched field may have changed.

  ```python
  InvalidationRule(model=User, field_mapping={"user_id": "id"}, watch_fields=["email"])

  user.email = "new@example.com"
  user.save()  # cache kept the old value before this release
  ```

## [2.0.1] - 2026-08-05

### Fixed

- Naming a restflow subclass in a DRF setting no longer breaks Django startup. `restflow.permissions`, `restflow.throttling`, `restflow.pagination`, and `restflow.exceptions` imported `rest_framework.views` at module scope. DRF evaluates `DEFAULT_AUTHENTICATION_CLASSES`, `DEFAULT_PERMISSION_CLASSES`, and `DEFAULT_THROTTLE_CLASSES` while `rest_framework.views` is still initialising, so importing a module that reached back into it raised `ImportError: cannot import name 'APIView' from partially initialized module`. No import ordering in the project could avoid it. The annotation-only imports now live behind `TYPE_CHECKING` and the exception handler resolves DRF's handler at call time.

  ```python
  # settings.py, previously unusable on 2.0.0
  REST_FRAMEWORK = {
      "DEFAULT_PERMISSION_CLASSES": ["myapp.permissions.IsApiKeyAuthenticated"],
  }
  ```

- `ais_valid()` no longer raises `SynchronousOnlyOperation` on a serializer with a related field or a unique validator. Resolving a primary key and running a uniqueness check both query the database, so those field validations now run in a thread. Async `ModelSerializer` validation works for models with foreign keys and unique columns.

- Async views no longer return 500 when a response renders a lazy queryset or follows a relation. `aserialized_response()`, `apaginated_response()`, and the async create mixin built `serializer.data` on the event loop, which opened a cursor while iterating the queryset or resolving a nested serializer. The render step now runs off the loop.

- `OPTIONS` works on async views and on views without a `serializer_class`. DRF's metadata class inspects the serializer and calls `get_object()` synchronously, which failed inside async dispatch, and because every restflow view exposes `get_serializer()`, DRF also reached it on views that never declare one. `AsyncAPIView` now answers `OPTIONS` off the event loop, and both view classes fall back to metadata without the serializer-derived actions.

- `RelatedField` expansion now filters through the relation. `RelatedField(model=Category, fields=["slug"])` exposed `category__slug` but filtered the base model's own `slug` column, returning wrong rows with no error when the base model happened to have a column of the same name.

- Component lookups accept a component value. `DateField(lookups=["year"])` and the `date`, `time`, `hour`, `minute`, `second`, `month`, `day`, `week`, `week_day`, and `quarter` variants generated a field typed like the parent, so `?published_at__year=2026` failed validation with "Date has wrong format". Component variants are integer fields now, and `date` and `time` variants take a date and a time.

- Substring lookups no longer inherit the parent field's format validator. `EmailField(lookups=["icontains"])` rejected `?email__icontains=alice` with "Enter a valid email address". The `contains`, `startswith`, `endswith`, `regex`, `search`, `trigram_similar`, and `unaccent` families resolve to a plain string field, while `exact` and `iexact` still validate the full format.

- `OrderField` keeps the requested ordering precedence. The value arrived as a set, so `?order_by=name,-price` applied the two keys in an arbitrary order.

- A partial `labels` list on `OrderField` no longer drops the unlabelled ordering options, and display labels reach the field instead of being lost on the way to DRF.

- `AsyncAPIClient.delete()`, `.post()`, and `.options()` work without a body. They passed `content_type=None` to Django's async client, which raised `TypeError` before the request was made.

- `restflow.authentication` pins `default_auto_field`, and `BlacklistedToken` declares its index name explicitly. A project using Django's default `BigAutoField` no longer gets a spurious migration generated inside site-packages on every `makemigrations`.

- `FastPageNumberPagination.paginate_queryset` accepts a sequence as well as a queryset, matching the base signature that `djangorestframework-stubs` 3.17.1 made generic. The override no longer reports `reportIncompatibleMethodOverride` under pyright.

### Changed

- `FilterSet.filter_queryset` and `afilter_queryset` are typed with a type variable bound to the queryset, so the return value keeps the caller's model instead of widening to a bare `QuerySet`. `ignore` is annotated as an optional list of field names and `data` as an optional mapping.

  ```python
  qs = ProductFilterSet(request=request).filter_queryset(Product.objects.all())
  # QuerySet[Product] instead of QuerySet[Unknown]
  ```

- Instantiating a `FilterSet` subclass reports the subclass to type checkers, and editor go-to-definition on the call lands on `FilterSet` rather than the metaclass.

## [2.0.0] - 2026-07-20

### Changed

- BREAKING: `cache_if` and `cache_unless` now receive `(result, *args, **kwargs)` instead of just the result. The predicates are called with the function's return value followed by the call arguments, matching the new callable `ttl`. A predicate written for an earlier release that accepts only the result must add `*args, **kwargs`. The same applies to `cache_response`, where the first argument is the rendered response.

  ```python
  # before
  @cache_result(UserKey, ttl=300, cache_if=lambda result: result is not None)
  def get_profile(user_id): ...

  # after
  @cache_result(
      UserKey, ttl=300,
      cache_if=lambda result, *args, **kwargs: result is not None,
  )
  def get_profile(user_id): ...
  ```

### Added

- restflow now ships a `py.typed` marker and a fully annotated public API. The package type-checks clean under pyright in standard mode with `django-stubs` and `djangorestframework-stubs`, and a `typecheck` job gates it in CI. Serializers, views, filters, permissions, caching, throttling, pagination, and the test client all carry real types instead of `Any`. Because the package was previously untyped, a project running mypy or pyright in a strict configuration may surface new type errors in its own code where restflow symbols resolved to `Any` before.

- `ttl` on `cache_result` and `cache_response` accepts a callable that computes the time-to-live per call. It runs on a cache miss, right before the write, and receives `(result, *args, **kwargs)`. Return an int number of seconds, or `None` to cache without expiry. On an async target the callable may be `async def`.

  ```python
  @cache_result(
      UserKey,
      ttl=lambda result, *args, **kwargs: 60 if not result else 3600,
  )
  def get_report(brand_id, month):
      return build_report(brand_id, month)
  ```

- A decorated function exposes `.func`, the undecorated target typed with its original signature. Calling it runs the function directly and skips the cache, so it doubles as an escape hatch and as the function object to pass around or introspect. The stdlib `__wrapped__` attribute that `functools.wraps` already sets is now declared with the same type.

  ```python
  @cache_result(UserKey, ttl=300)
  def get_profile(user_id: int) -> Profile: ...

  get_profile.func(1)   # uncached call, typed (user_id: int) -> Profile
  ```

- `filterset_schema_methods` controls which HTTP methods expose a view's filterset parameters in the OpenAPI schema. `RestflowAutoSchema` injects filter parameters for every method of a view that declares `filterset_class`, including `POST`, `PUT`, and `PATCH`. Set `filterset_schema_methods` on the view to limit them to specific methods (case-insensitive), or set `SCHEMA.FILTER_METHODS` in `RESTFLOW_SETTINGS` for a project-wide default. A per-view attribute overrides the setting, and `None` means every method. The default is unchanged, so existing schemas keep filter parameters on every method.

  ```python
  class ProductView(AsyncModelViewSet):
      filterset_class = ProductFilterSet
      filterset_schema_methods = ["GET"]
  ```

- Instantiating a `Serializer` or `ModelSerializer` subclass now reports the concrete class to type checkers, and `many=True` reports `ListSerializer`, instead of the `ListSerializer | Any` union inherited from DRF. IDE go-to-definition and autocomplete resolve to the subclass and its fields. Runtime behavior is unchanged, this only sharpens the static types.

- `CursorPagination.apaginate_queryset` now paginates natively on the event loop with async ORM iteration instead of running DRF's sync `paginate_queryset` in a thread via `sync_to_async`. It mirrors DRF's cursor logic and only the row fetch changed, so results are identical. The `PageNumberPagination`, `LimitOffsetPagination`, and `FastPageNumberPagination` async paths were already native. A custom paginator that does not implement `apaginate_queryset` still falls back to `sync_to_async` through `BasePagination`.

## [1.4.1] - 2026-07-04

### Added
- `cache_result` now reports the wrapped callable's return type to type checkers. The decorator picks `SyncCachedWrapper` for a plain function and `AsyncCachedWrapper` for a coroutine function, so calling a cached sync function is typed as its return value and calling a cached async function is typed as a coroutine to await. Both classes are re-exported from `restflow.caching`. Runtime behavior is unchanged, this only sharpens the static types.

  ```python
  @cache_result(UserKey, ttl=300)
  def get_profile(user_id: int) -> Profile: ...

  @cache_result(UserKey, ttl=300)
  async def aget_profile(user_id: int) -> Profile: ...

  reveal_type(get_profile(1))   # Profile
  reveal_type(aget_profile(1))  # Coroutine[Any, Any, Profile]
  ```

## [1.4.0] - 2026-06-20

### Added
- `KeyConstructor.wipe()` invalidates the cache for every function that shares a constructor in one call. `delete_by_prefix()` and `invalidate_all()` act on a single wrapped function, while the constructor keeps a list of the functions decorated with it and fans the same invalidation out across all of them. Arguments bind to each function's signature like a normal call, so `wipe(user_id=42)` drops that partition everywhere and a bare `wipe()` clears every partition. Use `awipe()` for async functions. A function joins the set when its `@cache_result` or `@cache_response` decorator runs at import time, and the call needs a redis-compatible backend that implements `delete_pattern`.

  ```python
  class UserDataKey(KeyConstructor):
      user = ArgsKeyField("user_id", partition=True)

      class Meta:
          namespace = "user_data"

  @cache_result(UserDataKey, ttl=300)
  def get_profile(user_id): ...

  @cache_result(UserDataKey, ttl=300)
  def get_settings(user_id): ...

  UserDataKey.wipe(user_id=42)  # drops user 42 on both functions
  UserDataKey.wipe()            # drops every entry both functions wrote
  ```

- `KeyConstructor.delete_previous_versions()` removes cache entries left behind by older versions of a constructor. Bumping `Meta.version` makes old entries unreachable but leaves the bytes in the backend until they expire. When the version is n above 1, this deletes versions 1 through n-1 across the namespace with `cache.delete_pattern`, leaving the live version n in place. A version of 1 is a no-op. The delete is scoped by namespace, so a constructor without one raises, and the backend must implement `delete_pattern`. Use `adelete_previous_versions()` in async contexts.

### Fixes
- `delete_cache()`, `delete_by_prefix()`, and `invalidate_all()` now delete at the constructor's version. Reads and writes already passed `version=` from `Meta.version`, but the delete paths did not, so on a constructor with a non-default version the deletes targeted version 1 and never matched the stored keys. The same version is now applied on every delete, including the async variants.

## [1.3.0] - 2026-06-20

### Added
- `NotRequired[T]` annotation marker for serializer fields. It sets `required=False` without touching `allow_null`, so a key may be left out of the input but must not be null when present. This complements `Optional[T]` / `T | None`, which mark a field both optional and nullable. The marker is re-exported from `restflow.serializers`, composes with the other forms (`NotRequired[T | None]` is optional and nullable), and an explicit `Field(required=True)` still takes precedence.

  ```python
  from restflow.serializers import NotRequired, Serializer

  class SignupSer(Serializer):
      email: str
      nickname: NotRequired[str]         # optional key, not nullable
      referral: NotRequired[str | None]  # optional key and nullable
  ```

- Per-lookup help text for filter lookup variants. A lookup alias can map to a dict carrying the ORM `lookup` and an optional `help_text`, so each generated variant can describe itself in the OpenAPI schema.

  ```python
  class ProductFilter(FilterSet):
      price = IntegerField(
          help_text="Product price",
          lookups={
              "min": {"lookup": "gte", "help_text": "Minimum price"},
              "max": {"lookup": "lte"},
          },
      )
  ```

  Each variant resolves its description in three steps. An explicit per-lookup `help_text` is used as is. Otherwise, when the parent field has a `help_text`, the variant gets "parent help (Bound Label)", for example "Product price (Inclusive Upper Bound)". Otherwise it falls back to an auto-generated verb hint. Negated (`!`) variants reuse the same description as "exclude where ...".

### Breaking
- Dropped Python 3.10 support. The minimum supported version is now Python 3.11.

## [1.2.0] - 2026-06-18

### Fixes
- Filter fields no longer invent values for parameters the client never sent. `BooleanField` and `MultipleChoiceField` (and `OrderField`) returned `False` and `[]` for an absent key because `request.query_params` is a `QueryDict` and DRF treats it as HTML form input. A missing parameter now skips the field, so a bare list request no longer applies a `field=False` or `field__in=[]` filter that drops rows it should keep.
- `delete_by_prefix()` now clears keys built from a partition-only `KeyConstructor`. `generate_key` had stripped the trailing separator from the stored key while the delete pattern kept it, so the prefix never matched. The separator is preserved on both sides, and a value like `user:42` still does not match `user:420`.

### Docs
- Note that `delete_by_prefix()`, `delete_cache()`, and `refresh()` bind arguments to the wrapped function's signature. Pass partition values by keyword so a positional value cannot bind to the wrong parameter.

## [1.1.0] - 2026-05-26

### Added

#### Caching
- `@cache_response` decorator for whole-view and `@api_view` HTTP caching. Stores the rendered response triple (content, status code, headers) and rebuilds a plain `HttpResponse` on a hit.
- `set_cache_headers=False` flag on `@cache_response`. When set to `True`, the wrapper attaches the `X-Cached-at`, `X-Cache-reset-at`, and `X-Cache-status` headers to every returned response so clients and monitoring can tell hits from misses without a separate metadata lookup.
- `ResponseCacheKeyConstructor` default key constructor for `@cache_response`. Hashes the full query string and captures the view method's URL kwargs as the partition.
- `ViewKwargsKeyField` cache-key field that captures a view method's URL kwargs while skipping `self`, `cls`, and `request`.

#### Responses
- `restflow.responses.Response` with an `arender()` method. Renders content and awaits any coroutine-function post-render callbacks on the live event loop. Async views and `@cache_response` on async methods use this path to keep rendering on the loop instead of bouncing through `async_to_sync`.



### Fixes
- `set_response_cache_header` emitted the `X-Cache-status` header as `"CacheStatus.MISS"` instead of `"MISS"` on Python 3.11+ because `str(enum)` now includes the class name. The helper now writes the enum's `value` so the header matches the documented vocabulary (`HIT`, `MISS`, `STALE`, `BYPASS`, `REFRESH`).
- `ArgsKeyField.get_key_payload` now uses `inspect.Signature.bind_partial` instead of `bind`, so invalidation handlers that supply only the fields named in `field_mapping` (for example, a view method whose signature includes `self` and `request`) no longer raise `TypeError: missing a required argument` and abort the rule.

## [1.0.2] - 2026-05-26

### Fixes
- Fix circular import on Django startup when `restflow.authentication.JWTAuthentication` is listed in `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`. The package no longer re-exports view classes at import time, breaking the cycle between `restflow.authentication`, `restflow.views`, and `rest_framework.views` during DRF settings resolution.

### Breaking
- `TokenObtainView`, `TokenRefreshView`, and `TokenBlacklistView` are no longer re-exported from `restflow.authentication`. Import them from `restflow.authentication.views` instead.

  ```python
  # Before
  from restflow.authentication import TokenObtainView, TokenRefreshView, TokenBlacklistView

  # After
  from restflow.authentication.views import TokenObtainView, TokenRefreshView, TokenBlacklistView
  ```



## [1.0.1] - 2026-05-25

### Fixes
- Fix Response caching bug


## [1.0.0] - 2026-05-19

### Added

#### Serializers

- `Serializer`, `ModelSerializer`, and `HyperlinkedModelSerializer` with annotation-driven field declaration using Python type hints
- `Field` sentinel for layering DRF kwargs on top of annotated fields
- Full async surface: `ais_valid`, `arun_validation`, `ato_internal_value`, `asave`, `acreate`, `aupdate`, `ato_representation`
- `ModelSerializer` ships default async `acreate` and `aupdate` that mirror DRF's sync logic using the async ORM
- `InlineSerializer` factory for building serializer classes at runtime without a dedicated class definition
- `ValidatedData` dict subclass with attribute access and `to_json()` helper
- `Email`, `IPAddress`, and `BlankableString` type aliases; `SerializerFieldMap` for custom type-to-field mappings
- `DecimalField` subclass with sensible default precision (`max_digits=20`, `decimal_places=6`)

#### Views

- `APIView` with the helper surface (`get_serializer`, `validated_serializer`, `serialized_response`, `paginated_response`) on top of DRF's sync view
- `AsyncAPIView` with a fully async dispatch loop and async twins for every helper
- Async generic views: `AsyncListAPIView`, `AsyncCreateAPIView`, `AsyncRetrieveAPIView`, `AsyncUpdateAPIView`, `AsyncDestroyAPIView`, and all composite combinations
- Async model mixins: `AsyncCreateModelMixin`, `AsyncListModelMixin`, `AsyncRetrieveModelMixin`, `AsyncUpdateModelMixin`, `AsyncDestroyModelMixin`
- `AsyncViewSet`, `AsyncGenericViewSet`, `AsyncReadOnlyModelViewSet`, `AsyncModelViewSet`
- `ActionConfig` dataclass for per-action serializer, permission, throttle, parser, renderer, pagination, and queryset overrides
- `request_serializer_class` / `response_serializer_class` split on viewsets and `APIView`
- `PostFetch` helper for attaching related rows to paginated lists outside of `prefetch_related`

#### Authentication

- Async-aware `BaseAuthentication` with `aauthenticate` on every built-in DRF class: `BasicAuthentication`, `SessionAuthentication`, `TokenAuthentication`, `RemoteUserAuthentication`
- Built-in JWT authentication (`JWTAuthentication`) with access and refresh tokens, blacklist support via pluggable backends, refresh token rotation, and configurable claims
- Pre-built JWT views: `ObtainTokenView`, `RefreshTokenView`, `VerifyTokenView`
- `SimpleJWTAdapter` for projects already using `djangorestframework-simplejwt`

#### Permissions

- Async-aware variants of all standard DRF permission classes with `ahas_permission` and `ahas_object_permission`
- Boolean combinators: `AND`, `OR`, `NOT` for composing permission rules without subclassing

#### Throttling

- Async-aware `SimpleRateThrottle`, `AnonRateThrottle`, `UserRateThrottle`, `ScopedRateThrottle` with `aallow_request` and `await_`

#### Pagination

- `AsyncPageNumberPagination`, `AsyncLimitOffsetPagination`, `AsyncCursorPagination`
- `FastPageNumberPagination` (omits `count` for performance)

#### Responses

- `NDJSONResponse` for newline-delimited JSON streaming
- `StreamingJSONListResponse` for streaming a JSON array
- `SSEResponse` for Server-Sent Events with automatic `X-Accel-Buffering: no`

#### Exception handler

- `restflow_exception_handler` with structured error codes alongside DRF's standard detail/code shape

#### Caching

- Async-aware cache key constructors

#### Spectacular (drf-spectacular integration)

- `RestflowAutoSchema` resolving `action_configs`, `request_serializer_class` / `response_serializer_class`, and per-action pagination
- `add_filterset_parameters` postprocessing hook that injects filter query parameters for any view declaring `filterset_class`, including plain `APIView`

#### Testing

- `AsyncAPIClient` and `AsyncRequestFactory` for testing async views without `sync_to_async` wrappers
- `AsyncAPITestCase` base class

## [1.0.0a2] - 2025-12-03

### Breaking Changes

- **Renamed `lookup_expr` to `filter_by`**:
  -  All Field classes now use `filter_by` parameter instead of `lookup_expr` for defining filter behavior. 
     Update all field definitions: `lookup_expr="name__icontains"` becomes `filter_by="name__icontains"`
  - Internal method `ensure_lookup_expr()` renamed to `ensure_db_field()`

- **Removed `description` parameter**: Field's `description` parameter has been removed
  - Use Django REST Framework's `help_text` parameter instead for field documentation

### Added

- **db_field parameter**: New parameter for dynamic lookup field generation
  - Allows creating filter fields with different names that map to the same database field
  - Example: `product_price = IntegerField(db_field="price", lookups=["comparison"])` creates multiple filters (product_price, product_price__gt, etc.) that all filter against the "price" database field
  - Enables lookup generation when using `method` or custom `filter_by` functions
    
- **Enhanced validation**: Added validation to ensure `db_field` is set when using `lookups` with custom `method` or `filter_by` parameters
  - Provides clear error messages with examples when validation fails

### Changed

- Improved filter field handling with better separation between field name (API) and database field name (ORM queries)
- Enhanced error messages with more descriptive and actionable text
- Model-based field generation now automatically sets both `filter_by` and `db_field` parameters
- Related field filtering (ForeignKey, OneToOneField) correctly sets both parameters

### Documentation

- Updated all references from `lookup_expr` to `filter_by` across documentation
- Added comprehensive examples for `db_field` parameter usage
- Expanded FilterSet and Field guides with new parameter explanations
- Updated tutorial and quick start guides with new syntax


### Migration from 1.0.0a1

1. Replace `lookup_expr` with `filter_by` in all FilterSet field definitions
2. Replace `description` parameter with `help_text` if used
3. Custom filter method signatures remain unchanged and compatible



## [1.0.0a1] - 2025-11-25

### Added

#### Core Features
- **FilterSet**: Declarative filtering system for Django REST Framework
- **Field Types**: Comprehensive set of filter fields
  - StringField, IntegerField, FloatField, DecimalField
  - BooleanField, DateField, DateTimeField, TimeField, DurationField
  - ChoiceField, MultipleChoiceField
  - EmailField, IPAddressField
  - ListField for array filtering
  - OrderField for result ordering
  - RelatedField for related fields in models
  - Field base class for custom filters

#### Declaration Styles
- Type annotation support (`name: str`, `price: int`)
- Explicit field declarations
- Model-based automatic field generation
- Mixed declaration styles

#### Lookup System
- Automatic lookup generation from field definitions
- Lookup categories (basic, text, comparison, date, time, postgres, pg_array)
- Custom lookup expressions via strings or callables
- Field variants (base field + lookups + negations)

#### Filtering Features
- Negation support via `!` suffix
- Multiple filter operators (AND, OR, XOR)
- Custom filter methods
- Preprocessors and postprocessors
- Related field filtering

#### Ordering
- OrderField for flexible result ordering
- Ascending/descending support
- Multiple field ordering
- Configurable ordering direction

#### PostgreSQL Support
- PostgreSQL array field filtering
- Array lookups (contains, overlaps, contained_by)
- Full-text search support
- Trigram similarity

#### Model Integration
- Automatic field generation from Django models
- Support for model field types
- ForeignKey and OneToOneField filtering
- Model choice field detection

#### Validation
- Built on DRF's validation system
- Automatic type conversion
- Field-level and custom validators
- Detailed error messages

#### Type Safety
- Python type hint support
- Automatic field type inference
- Type mapping for common Python types
- Literal type for choices

### Documentation
- Comprehensive user guide
- API reference
- Quick start tutorial
- PostgreSQL guide
- Migration guide from django-filter

### Testing
- Test suite with 95%+ coverage
- PostgreSQL-specific tests
- Multiple Python version support (3.10-3.14)
- Multiple Django version support (3.2-5.2)
- CI/CD with GitHub Actions

### Developer Experience
- Modern Python features (type hints, dataclasses)
- Clear error messages
- Extensive docstrings
- IDE-friendly API

## Version Support

| Version | Python | Django | DRF | Status |
|---------|--------|--------|-----|--------|
| 1.0.0a1 | 3.10-3.14 | 3.2-5.2 | 3.14+ | Alpha |

## Migration from django-filter

drf-restflow offers similar functionality to django-filter with a more modern, declarative API. Key differences:

- **Type annotations**: Use Python type hints instead of explicit field declarations
- **Automatic negation**: Built-in `!` suffix support for all filters
- **Lookup categories**: Group related lookups (e.g., "comparison" for gt/gte/lt/lte)
- **Better validation**: Integrated with DRF's validation system

For migration assistance, refer to the [FilterSet Guide](guide/filtering/filterset.md) and [Fields Guide](guide/filtering/fields.md) for comprehensive documentation.

## Deprecation Policy

Following semantic versioning:

- **Major versions** (x.0.0): May include breaking changes
- **Minor versions** (0.x.0): New features, backward compatible
- **Patch versions** (0.0.x): Bug fixes, backward compatible

Deprecation warnings will be issued for at least one minor version before removal.

## Reporting Issues

Found a bug or have a feature request? Please open an issue on [GitHub](https://github.com/khan-asfi-reza/drf-restflow/issues).

## Contributing

See [Contributing Guide](contributing.md) for information on how to contribute to this changelog and the project.
