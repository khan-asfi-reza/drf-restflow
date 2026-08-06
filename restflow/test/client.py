from typing import TYPE_CHECKING, Any, cast

from django.conf import settings as django_settings
from django.test import AsyncClient as DjangoAsyncClient
from django.test import AsyncRequestFactory as DjangoAsyncRequestFactory
from django.test.client import AsyncClientHandler
from django.utils.encoding import force_bytes
from rest_framework.settings import api_settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.core.handlers.asgi import ASGIRequest
    from django.http import HttpRequest
    from django.http.response import HttpResponseBase
    from django.test.client import _MonkeyPatchedASGIResponse
    from django.utils.functional import _StrOrPromise
    from rest_framework.renderers import BaseRenderer


def force_authenticate(
    request: Any, user: Any = None, token: Any = None
) -> None:
    """
    Force-authenticate a request, bypassing the authenticator chain.
    """
    request._force_auth_user = user
    request._force_auth_token = token


def _renderer_classes() -> "dict[str, type[BaseRenderer]]":
    classes = cast(
        "Sequence[type[BaseRenderer]]",
        api_settings.TEST_REQUEST_RENDERER_CLASSES,
    )
    return {cls.format: cls for cls in classes}


def _encode_data(
    data: Any = None,
    format: str | None = None,
    content_type: str | None = None,
) -> "tuple[bytes, str | None]":
    if data is None:
        return (b"", content_type or "application/octet-stream")

    assert format is None or content_type is None, (
        "May not set both `format` and `content_type`."
    )

    if content_type:
        ret = force_bytes(data, django_settings.DEFAULT_CHARSET)
        return ret, content_type

    renderers = _renderer_classes()
    format = format or "json"
    assert format in renderers, (
        f"Invalid format '{format}'. Available formats are "
        f"{', '.join(repr(f) for f in renderers)}."
    )
    cls = renderers[format]
    renderer = cls()
    ret = renderer.render(data)
    media_type = renderer.media_type
    if renderer.charset:
        media_type = f"{media_type}; charset={renderer.charset}"
    if isinstance(ret, str):
        ret = ret.encode(cast("str", renderer.charset))
    return ret, media_type


class AsyncAPIRequestFactory(DjangoAsyncRequestFactory):
    """
    Builds raw ASGI requests for tests that bind a request directly to a
    view instance and await dispatch.

    Mirrors DRF's `APIRequestFactory` but produces ASGI-style requests
    suitable for `await view.dispatch(request)`.
    """

    default_format = "json"

    def __init__(
        self, enforce_csrf_checks: bool = False, **defaults: Any
    ) -> None:
        self.enforce_csrf_checks = enforce_csrf_checks
        super().__init__(**defaults)

    def post(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        **extra: Any,
    ) -> "ASGIRequest":
        """Construct a POST request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("POST", path, body, ct, **extra)

    def put(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        **extra: Any,
    ) -> "ASGIRequest":
        """Construct a PUT request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("PUT", path, body, ct, **extra)

    def patch(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        **extra: Any,
    ) -> "ASGIRequest":
        """Construct a PATCH request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("PATCH", path, body, ct, **extra)

    def delete(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        **extra: Any,
    ) -> "ASGIRequest":
        """Construct a DELETE request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("DELETE", path, body, ct, **extra)

    def options(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        **extra: Any,
    ) -> "ASGIRequest":
        """Construct an OPTIONS request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("OPTIONS", path, body, ct, **extra)

    def request(self, **kwargs: Any) -> "ASGIRequest":
        """Construct a generic request, marking CSRF checks per the factory setting."""
        request: Any = super().request(**kwargs)
        request._dont_enforce_csrf_checks = not self.enforce_csrf_checks
        return request


class _ForceAuthAsyncClientHandler(AsyncClientHandler):
    """AsyncClientHandler that injects force-authentication onto each outgoing request."""

    _force_user: Any
    _force_token: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._force_user = None
        self._force_token = None
        super().__init__(*args, **kwargs)

    async def get_response_async(
        self, request: "HttpRequest"
    ) -> "HttpResponseBase":
        """Apply force-auth attrs to the request, then dispatch through middleware."""
        force_authenticate(request, self._force_user, self._force_token)
        return await super().get_response_async(request)


class AsyncAPIClient(DjangoAsyncClient):
    """
    Async test client for restflow's AsyncAPIView and AsyncViewSet.

    Drop-in for Django's `AsyncClient` and DRF's `APIClient`. Adds
    DRF-style format encoding (json by default), `force_authenticate()`,
    and `credentials()` so async views can be exercised end-to-end.
    """

    default_format = "json"
    handler: _ForceAuthAsyncClientHandler
    _credentials: dict[str, Any]

    def __init__(
        self, enforce_csrf_checks: bool = False, **defaults: Any
    ) -> None:
        super().__init__(enforce_csrf_checks=enforce_csrf_checks, **defaults)
        self.handler = _ForceAuthAsyncClientHandler(enforce_csrf_checks)  # pyright: ignore[reportIncompatibleVariableOverride]
        self._credentials = {}

    def credentials(self, **kwargs: Any) -> None:
        """Set headers used on every outgoing request. Keys must start with HTTP_ or CONTENT_ to mirror Django's WSGI environ convention."""
        for key in kwargs:
            if not key.startswith(("HTTP_", "CONTENT_")):
                msg = (
                    f"AsyncAPIClient.credentials() rejected key {key!r}. "
                    "Keys must start with 'HTTP_' (request headers) or 'CONTENT_' "
                    "(content-type / content-length)."
                )
                raise ValueError(msg)
        self._credentials = kwargs

    def force_authenticate(
        self, user: Any = None, token: Any = None
    ) -> None:
        """Forcibly authenticate outgoing requests with the given user or token."""
        self.handler._force_user = user
        self.handler._force_token = token

    def logout(self) -> None:
        """Clear credentials, force-auth, and any active session."""
        self._credentials = {}
        self.handler._force_user = None
        self.handler._force_token = None
        if self.session:
            super().logout()

    async def request(self, **kwargs: Any) -> "_MonkeyPatchedASGIResponse":
        """Make a generic async request, merging stored credentials into headers."""
        if self._credentials:
            existing_headers = list(kwargs.get("headers", []))
            for key, value in self._credentials.items():
                if key.startswith("HTTP_"):
                    name = key[5:].replace("_", "-").lower()
                else:
                    name = key.replace("_", "-").lower()
                existing_headers.append(
                    (name.encode("ascii"), str(value).encode("latin1"))
                )
            kwargs["headers"] = existing_headers
        return await super().request(**kwargs)

    async def get(
        self, path: "_StrOrPromise", data: Any = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a GET request."""
        return await super().get(
            path, data=data, follow=follow, secure=secure, **extra
        )

    async def post(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a POST request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().post(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra  # pyright: ignore[reportArgumentType]
        )

    async def put(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a PUT request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().put(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra  # pyright: ignore[reportArgumentType]
        )

    async def patch(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a PATCH request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().patch(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra  # pyright: ignore[reportArgumentType]
        )

    async def delete(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a DELETE request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().delete(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra  # pyright: ignore[reportArgumentType]
        )

    async def options(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, path: "_StrOrPromise", data: Any = None,
        format: str | None = None, content_type: str | None = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send an OPTIONS request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().options(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra  # pyright: ignore[reportArgumentType]
        )

    async def head(
        self, path: "_StrOrPromise", data: Any = None,
        follow: bool = False, secure: bool = False, **extra: Any,
    ) -> "_MonkeyPatchedASGIResponse":
        """Send a HEAD request."""
        return await super().head(
            path, data=data, follow=follow, secure=secure, **extra
        )
