# Changelog

All notable changes to drf-restflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-26

### Added
- `cache_response` now accepts `set_cache_headers=False`. When set to `True`, the wrapper attaches the `X-Cached-at`, `X-Cache-reset-at`, and `X-Cache-status` headers to every returned response so clients and monitoring can tell hits from misses without a separate metadata lookup.
- `@cache_response` now works on DRF's `@api_view` function-based views (sync only). `extract_view_and_request` falls back to `request.parser_context["view"]` when the wrapped function does not carry a `self` argument, so the cached response renders with the same `accepted_renderer` as a normal `@api_view` call.
- Documentation: new [cache_response guide](guide/caching/cache-response.md) and matching API reference page, plus rewarm caveats added to the invalidation guide.

### Fixes
- `set_response_cache_header` emitted the `X-Cache-status` header as `"CacheStatus.MISS"` instead of `"MISS"` on Python 3.11+ because `str(enum)` now includes the class name. The helper now writes the enum's `value` so the header matches the documented vocabulary (`HIT`, `MISS`, `STALE`, `BYPASS`, `REFRESH`).
- `ArgsKeyField.get_key_payload` now uses `inspect.Signature.bind_partial` instead of `bind`, so invalidation handlers that supply only the fields named in `field_mapping` (for example, a view method whose signature includes `self` and `request`) no longer raise `TypeError: missing a required argument` and abort the rule.
- `CachedResponseWrapper.render_view_response_sync` and `render_view_response_async` no longer pass `request` to `view.finalize_response` twice when the caller invokes the wrapped method with `request` as a keyword argument.

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
