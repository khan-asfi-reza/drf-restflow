import inspect
from collections.abc import Callable

from django.http import HttpResponse

from restflow.caching.constants import CACHE_MISSING
from restflow.caching.key_constructor import KeyConstructor
from restflow.caching.key_fields import (
    QueryParamsKeyField,
    ViewKwargsKeyField,
)
from restflow.caching.rules import InvalidationRule
from restflow.caching.wrapper import CachedWrapper, set_response_cache_header


class ResponseCacheKeyConstructor(KeyConstructor):
    """
    Default key constructor for cache_response. Combines every request query
    parameter with the wrapped view method's URL kwargs. Subclass to add a
    user_id partition or narrow the captured fields.
    """

    query_params = QueryParamsKeyField("*", hash_value=True)
    path_params = ViewKwargsKeyField("*", partition=True)

    class Meta:
        version = 1
        namespace = "ResponseCache"


class CachedResponseWrapper(CachedWrapper):
    """
    CachedWrapper for view methods that returns a fresh HttpResponse on hit.

    Stores (content_bytes, status_code, headers_dict). On hit, rebuilds an HttpResponse and skips the view body, serializer, and renderer.
    """
    def __init__(
        self,
        func,
        key_constructor,
        invalidates_on,
        cache_if,
        cache_unless,
        ttl,
        set_cache_headers,
    ):
        super().__init__(
            func=func,
            key_constructor=key_constructor,
            ttl=ttl,
            invalidates_on=invalidates_on,
            cache_if=cache_if,
            cache_unless=cache_unless,
        )
        self.set_cache_headers = set_cache_headers

    def _sync_call(self, args, kwargs, *, with_metadata, refresh):
        cache_key = self.get_cache_key(*args, **kwargs)

        if not refresh:
            cached, metadata = self.cache_get_with_metadata(cache_key)
            if cached is not CACHE_MISSING:
                response = self.rebuild_http_response(cached)
                self._maybe_attach_headers(response, metadata)
                return (response, metadata) if with_metadata else response

        response = self.render_view_response_sync(args, kwargs)
        if not self._evaluate_cache_predicate_sync(response):
            self._maybe_attach_headers(response, None)
            return (response, None) if with_metadata else response

        triple = self.serialize_response(response)
        _, _metadata = self.cache_set_with_timestamp(
            key=cache_key,
            value=triple,
            timeout=self._ttl,
            version=self.get_key_version(),
        )
        self._maybe_attach_headers(response, _metadata)
        return (response, _metadata) if with_metadata else response

    async def _async_call(self, args, kwargs, *, with_metadata, refresh):
        cache_key = self.get_cache_key(*args, **kwargs)

        if not refresh:
            cached, metadata = await self.acache_get_with_metadata(cache_key)
            if cached is not CACHE_MISSING:
                response = self.rebuild_http_response(cached)
                self._maybe_attach_headers(response, metadata)
                return (response, metadata) if with_metadata else response

        response = await self.render_view_response_async(args, kwargs)
        if not await self._evaluate_cache_predicate_async(response):
            self._maybe_attach_headers(response, None)
            return (response, None) if with_metadata else response

        triple = self.serialize_response(response)
        _, _metadata = await self.acache_set_with_timestamp(
            key=cache_key,
            value=triple,
            timeout=self._ttl,
            version=self.get_key_version(),
        )
        self._maybe_attach_headers(response, _metadata)
        return (response, _metadata) if with_metadata else response

    def _maybe_attach_headers(self, response, metadata):
        if self.set_cache_headers:
            set_response_cache_header(response, metadata)

    def render_view_response_sync(self, args, kwargs):
        response = self._func(*args, **kwargs)
        view, request = self.extract_view_and_request(args, kwargs)
        if view is not None and request is not None:
            forward_kwargs = {
                k: v for k, v in kwargs.items() if k != "request"
            }
            response = view.finalize_response(
                request, response, *args[2:], **forward_kwargs
            )
        response.render()
        return response

    async def render_view_response_async(self, args, kwargs):
        response = await self._func(*args, **kwargs)
        view, request = self.extract_view_and_request(args, kwargs)
        if view is not None and request is not None:
            forward_kwargs = {
                k: v for k, v in kwargs.items() if k != "request"
            }
            response = view.finalize_response(
                request, response, *args[2:], **forward_kwargs
            )
        arender = getattr(response, "arender", None)
        if arender is not None:
            await arender()
        else:
            response.render()
        return response

    def serialize_response(self, response):
        return (
            response.rendered_content,
            response.status_code,
            dict(response.items()),
        )

    def rebuild_http_response(self, triple):
        content, status_code, headers = triple
        response = HttpResponse(content=content, status=status_code)
        for k, v in headers.items():
            response[k] = v
        return response

    def extract_view_and_request(self, args, kwargs):
        """Locate the view instance and request in the wrapped method's call args."""
        sig = inspect.signature(self._func)
        params = list(sig.parameters)
        view = (
            args[0]
            if params[:1] == ["self"] and len(args) >= 1
            else None
        )
        request = None
        if "request" in kwargs:
            request = kwargs["request"]
        elif params[:2] == ["self", "request"] and len(args) >= 2:
            request = args[1]
        elif params[:1] == ["request"] and len(args) >= 1:
            request = args[0]

        if view is None and request is not None:
            parser_context = getattr(request, "parser_context", None)
            if parser_context:
                view = parser_context.get("view")

        return view, request


def cache_response(
    key_constructor: (
        "KeyConstructor | dict | type[KeyConstructor] | None"
    ) = None,
    ttl: int | None = 3600,
    invalidates_on: list["InvalidationRule"] | None = None,
    cache_if: Callable | None = None,
    cache_unless: Callable | None = None,
    set_cache_headers: bool = False,
):
    """
    Cache a view method's rendered HTTP output.

    Stores (content, status_code, headers). On a hit, returns a fresh
    HttpResponse rebuilt from the triple and skips the view body, the
    serializer, and the renderer. Use this for whole-view caching where
    cache_result would risk pickling Serializer or QuerySet state.

    Pairs with KeyConstructor and InvalidationRule the same way as
    cache_result. Default key_constructor is ResponseCacheKeyConstructor
    (query params plus the view's URL kwargs).

    When set_cache_headers is True, the wrapper attaches the X-Cached-at,
    X-Cache-reset-at, and X-Cache-status headers to every returned
    response so clients and monitoring can tell hits from misses without
    a separate metadata lookup.

    Example:
        class UserMeAPIView(AsyncAPIView):
            @cache_response(ttl=60, set_cache_headers=True)
            async def get(self, request):
                ...
    """
    key_constructor = key_constructor or ResponseCacheKeyConstructor
    invalidates_on = invalidates_on or []

    def decorator(func):
        return CachedResponseWrapper(
            func=func,
            key_constructor=key_constructor,
            invalidates_on=invalidates_on,
            cache_if=cache_if,
            cache_unless=cache_unless,
            ttl=ttl,
            set_cache_headers=set_cache_headers
        )

    return decorator
