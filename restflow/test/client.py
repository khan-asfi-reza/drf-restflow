from django.conf import settings as django_settings
from django.test import AsyncClient as DjangoAsyncClient
from django.test import AsyncRequestFactory as DjangoAsyncRequestFactory
from django.test.client import AsyncClientHandler
from django.utils.encoding import force_bytes
from rest_framework.settings import api_settings


def force_authenticate(request, user=None, token=None):
    """
    Force-authenticate a request, bypassing the authenticator chain.
    """
    request._force_auth_user = user
    request._force_auth_token = token


def _renderer_classes():
    return {cls.format: cls for cls in api_settings.TEST_REQUEST_RENDERER_CLASSES}


def _encode_data(data, format=None, content_type=None):
    if data is None:
        return (b"", content_type)

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
        ret = ret.encode(renderer.charset)
    return ret, media_type


class AsyncAPIRequestFactory(DjangoAsyncRequestFactory):
    """
    Builds raw ASGI requests for tests that bind a request directly to a
    view instance and await dispatch.

    Mirrors DRF's `APIRequestFactory` but produces ASGI-style requests
    suitable for `await view.dispatch(request)`.
    """

    default_format = "json"

    def __init__(self, enforce_csrf_checks=False, **defaults):
        self.enforce_csrf_checks = enforce_csrf_checks
        super().__init__(**defaults)

    def post(self, path, data=None, format=None, content_type=None, **extra):
        """Construct a POST request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("POST", path, body, ct, **extra)

    def put(self, path, data=None, format=None, content_type=None, **extra):
        """Construct a PUT request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("PUT", path, body, ct, **extra)

    def patch(self, path, data=None, format=None, content_type=None, **extra):
        """Construct a PATCH request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("PATCH", path, body, ct, **extra)

    def delete(self, path, data=None, format=None, content_type=None, **extra):
        """Construct a DELETE request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("DELETE", path, body, ct, **extra)

    def options(self, path, data=None, format=None, content_type=None, **extra):
        """Construct an OPTIONS request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return self.generic("OPTIONS", path, body, ct, **extra)

    def request(self, **kwargs):
        """Construct a generic request, marking CSRF checks per the factory setting."""
        request = super().request(**kwargs)
        request._dont_enforce_csrf_checks = not self.enforce_csrf_checks
        return request


class _ForceAuthAsyncClientHandler(AsyncClientHandler):
    """AsyncClientHandler that injects force-authentication onto each outgoing request."""

    def __init__(self, *args, **kwargs):
        self._force_user = None
        self._force_token = None
        super().__init__(*args, **kwargs)

    async def get_response_async(self, request):
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

    def __init__(self, enforce_csrf_checks=False, **defaults):
        super().__init__(enforce_csrf_checks=enforce_csrf_checks, **defaults)
        self.handler = _ForceAuthAsyncClientHandler(enforce_csrf_checks)
        self._credentials = {}

    def credentials(self, **kwargs):
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

    def force_authenticate(self, user=None, token=None):
        """Forcibly authenticate outgoing requests with the given user or token."""
        self.handler._force_user = user
        self.handler._force_token = token

    def logout(self):
        """Clear credentials, force-auth, and any active session."""
        self._credentials = {}
        self.handler._force_user = None
        self.handler._force_token = None
        if self.session:
            super().logout()

    async def request(self, **kwargs):
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

    async def get(self, path, data=None, follow=False, secure=False, **extra):
        """Send a GET request."""
        return await super().get(
            path, data=data, follow=follow, secure=secure, **extra
        )

    async def post(
        self, path, data=None, format=None, content_type=None,
        follow=False, secure=False, **extra,
    ):
        """Send a POST request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().post(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra
        )

    async def put(
        self, path, data=None, format=None, content_type=None,
        follow=False, secure=False, **extra,
    ):
        """Send a PUT request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().put(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra
        )

    async def patch(
        self, path, data=None, format=None, content_type=None,
        follow=False, secure=False, **extra,
    ):
        """Send a PATCH request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().patch(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra
        )

    async def delete(
        self, path, data=None, format=None, content_type=None,
        follow=False, secure=False, **extra,
    ):
        """Send a DELETE request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().delete(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra
        )

    async def options(
        self, path, data=None, format=None, content_type=None,
        follow=False, secure=False, **extra,
    ):
        """Send an OPTIONS request with DRF-style format encoding."""
        body, ct = _encode_data(data, format, content_type)
        return await super().options(
            path, data=body, content_type=ct, follow=follow, secure=secure, **extra
        )

    async def head(self, path, data=None, follow=False, secure=False, **extra):
        """Send a HEAD request."""
        return await super().head(
            path, data=data, follow=follow, secure=secure, **extra
        )
