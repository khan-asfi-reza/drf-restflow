# cache_response

The decorator that wraps a view method or function-based view in a
`CachedResponseWrapper`. See the
[cache_response guide](../../guide/caching/cache-response.md) for an
overview and worked examples.

::: restflow.caching.cache_response

::: restflow.caching.CachedResponseWrapper
    options:
      members:
        - render_view_response_sync
        - render_view_response_async
        - extract_view_and_request
        - serialize_response
        - rebuild_http_response

::: restflow.caching.ResponseCacheKeyConstructor
