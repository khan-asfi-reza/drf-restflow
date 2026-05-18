# Guide Overview

The Guide covers each feature in depth.

| Feature | Description | Link |
| --- | --- | --- |
| Caching | Declarative cache-key construction, model-signal-driven invalidation, response-header reporting, and a pluggable dispatcher layer for celery, django-rq, django-q, dramatiq, asyncio, threadpool, or inline execution. | [Caching guide](caching/index.md) |
| Filtering | Declarative `FilterSet` classes with type annotations, automatic lookup and negation variants, custom methods, ordering, preprocessors and postprocessors, and a DRF backend that emits OpenAPI parameters for every field. | [Filtering guide](filtering/filterset.md) |
| Serializers | Type-driven `Serializer`, `ModelSerializer`, and `HyperlinkedModelSerializer` subclasses with an async surface (`ais_valid`, `asave`, `acreate`, `aupdate`) and an `InlineSerializer` factory. | [Serializers guide](serializers/index.md) |
| Authentication | Async JWT authentication with PyJWT, built-in obtain, refresh, and blacklist views, swappable blacklist backends, and async wrappers for the standard DRF authenticators plus an optional adapter for djangorestframework-simplejwt. | [Authentication guide](authentication/index.md) |
| Permissions | Async-aware permission classes that compose through DRF's `&`, `|`, and `~` operators, with async-native operator classes that resolve combinator branches through the async hook . | [Permissions guide](permissions/index.md) |
| Views | Full async view stack: `AsyncAPIView`, eight generic views, five model mixins, four viewsets, plus `ActionConfig` for per-action overrides and `PostFetch` for after-pagination joins. | [Views guide](views/index.md) |
| Pagination | Async-aware page number, limit-offset, cursor, and fast page number paginators that drive `apaginate_queryset()` on async views and viewsets. | [Pagination guide](pagination/index.md) |
| Throttling | Async-aware throttle classes that use Django's async cache for non-blocking rate-limit checks. | [Throttling guide](throttling/index.md) |
| Responses | Streaming JSON, NDJSON, and Server-Sent Events responses for endpoints that produce large or open-ended payloads. | [Responses guide](responses/index.md) |
| Exception handler | A drop-in DRF exception handler that renders every error as a uniform envelope with a stable error code, message, and details payload. | [Exception handler guide](exception-handler/index.md) |
| Spectacular | `RestflowAutoSchema`, a drop-in replacement for drf-spectacular's default schema generator that understands action configs, the request and response serializer split, and async pagination. | [Spectacular guide](spectacular/index.md) |
| Testing | `AsyncAPIClient`, `AsyncAPIRequestFactory`, four `AsyncAPI*TestCase` bases, and `force_authenticate` for testing async views. | [Testing guide](testing/index.md) |
