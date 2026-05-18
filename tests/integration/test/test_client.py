import asyncio
import json

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from django.urls import path
from rest_framework import permissions
from rest_framework import serializers as drf_serializers
from rest_framework.response import Response

from restflow.test import (
    AsyncAPIClient,
    AsyncAPIRequestFactory,
    force_authenticate,
)
from restflow.views import APIView, AsyncAPIView


def _run(coro):
    return asyncio.run(coro)


class _EchoSer(drf_serializers.Serializer):
    name = drf_serializers.CharField()


class _AsyncEchoView(AsyncAPIView):
    request_serializer_class = _EchoSer
    response_serializer_class = _EchoSer

    async def post(self, request):
        ser = await self.avalidated_serializer()
        return await self.aserialized_response(ser.validated_data)

    async def get(self, request):
        return await self.aserialized_response({"name": "anon"})


class _RequireAuth(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user is not None and not isinstance(request.user, AnonymousUser)


class _PrivateAsyncView(AsyncAPIView):
    permission_classes = [_RequireAuth]

    async def get(self, request):
        return Response({"user": str(request.user)})


class _HeaderEchoView(AsyncAPIView):
    async def get(self, request):
        return Response({"token": request.META.get("HTTP_X_API_TOKEN", "")})


class _MethodEchoView(AsyncAPIView):
    async def get(self, request):
        return Response({"method": "GET"})

    async def post(self, request):
        return Response({"method": "POST", "body": request.body.decode("utf-8")})

    async def put(self, request):
        return Response({"method": "PUT", "body": request.body.decode("utf-8")})

    async def patch(self, request):
        return Response({"method": "PATCH", "body": request.body.decode("utf-8")})

    async def delete(self, request):
        return Response({"method": "DELETE"})

    async def options(self, request):
        return Response({"method": "OPTIONS"})

    async def head(self, request):
        return Response()


class _XHeaderEchoView(AsyncAPIView):
    async def get(self, request):
        return Response({"header": request.META.get("HTTP_X_CUSTOM", "")})


urlpatterns = [
    path("echo/", _AsyncEchoView.as_view(), name="echo"),
    path("private/", _PrivateAsyncView.as_view(), name="private"),
    path("headers/", _HeaderEchoView.as_view(), name="headers"),
    path("methods/", _MethodEchoView.as_view(), name="methods"),
    path("xheader/", _XHeaderEchoView.as_view(), name="xheader"),
]


@pytest.fixture
def urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


def test_factory_post_encodes_json_by_default():
    factory = AsyncAPIRequestFactory()
    raw = factory.post("/echo/", data={"name": "khan"})
    assert raw.headers["content-type"].startswith("application/json")
    assert json.loads(raw.body) == {"name": "khan"}


def test_factory_get_builds_asgi_request():
    factory = AsyncAPIRequestFactory()
    raw = factory.get("/echo/")
    assert raw.method == "GET"
    assert raw.path == "/echo/"


def test_force_authenticate_sets_attrs():
    factory = AsyncAPIRequestFactory()
    raw = factory.get("/echo/")
    user = object()
    token = "abc"
    force_authenticate(raw, user=user, token=token)
    assert raw._force_auth_user is user
    assert raw._force_auth_token == token


def test_client_post_json_default(urls):
    client = AsyncAPIClient()
    response = _run(client.post("/echo/", data={"name": "bob"}))
    assert response.status_code == 200
    assert response.json() == {"name": "bob"}


def test_client_get_anonymous(urls):
    client = AsyncAPIClient()
    response = _run(client.get("/echo/"))
    assert response.status_code == 200
    assert response.json() == {"name": "anon"}


def test_client_force_authenticate_passes_permission_check(urls):
    client = AsyncAPIClient()
    response = _run(client.get("/private/"))
    assert response.status_code == 403

    class _U:
        is_authenticated = True
        is_active = True

        def __str__(self):
            return "khan"

    client.force_authenticate(user=_U())
    response = _run(client.get("/private/"))
    assert response.status_code == 200
    assert response.json() == {"user": "khan"}


def test_client_force_authenticate_clear(urls):
    client = AsyncAPIClient()

    class _U:
        is_authenticated = True
        is_active = True

        def __str__(self):
            return "khan"

    client.force_authenticate(user=_U())
    response = _run(client.get("/private/"))
    assert response.status_code == 200

    client.force_authenticate(user=None, token=None)
    response = _run(client.get("/private/"))
    assert response.status_code == 403


def test_client_credentials_attaches_headers(urls):
    client = AsyncAPIClient()
    client.credentials(HTTP_X_API_TOKEN="secret-token")
    response = _run(client.get("/headers/"))
    assert response.status_code == 200
    assert response.json() == {"token": "secret-token"}


def test_client_post_invalid_returns_400(urls):
    client = AsyncAPIClient()
    response = _run(client.post("/echo/", data={}))
    assert response.status_code == 400


def test_client_post_explicit_content_type(urls):
    client = AsyncAPIClient()
    response = _run(
        client.post(
            "/echo/",
            data='{"name": "carol"}',
            content_type="application/json",
        )
    )
    assert response.status_code == 200
    assert response.json() == {"name": "carol"}


def test_factory_works_with_sync_apiview_dispatch():
    class V(APIView):
        request_serializer_class = _EchoSer
        response_serializer_class = _EchoSer

        def post(self, request):
            ser = self.validated_serializer()
            return self.serialized_response(ser.validated_data)

    factory = AsyncAPIRequestFactory()
    raw = factory.post("/echo/", data={"name": "dan"})
    view = V()
    view.request = view.initialize_request(raw)
    view.format_kwarg = None
    response = view.post(view.request)
    assert response.status_code == 200
    assert response.data == {"name": "dan"}


def test_factory_post_with_no_data_uses_empty_body():
    factory = AsyncAPIRequestFactory()
    raw = factory.post("/echo/", data=None)
    assert raw.body == b""


def test_factory_post_multipart_renders_with_charset():
    factory = AsyncAPIRequestFactory()
    raw = factory.post("/echo/", data={"name": "khan"}, format="multipart")
    ct = raw.headers["content-type"]
    assert ct.startswith("multipart/form-data")
    assert "charset=utf-8" in ct


def test_encode_data_encodes_string_renderer_output(monkeypatch):
    from rest_framework.renderers import BaseRenderer

    from restflow.test import client as client_module

    class _StrRenderer(BaseRenderer):
        media_type = "text/plain"
        format = "plain"
        charset = "utf-8"

        def render(self, data, accepted_media_type=None, renderer_context=None):
            return str(data)

    monkeypatch.setattr(
        client_module, "_renderer_classes", lambda: {"plain": _StrRenderer}
    )
    body, ct = client_module._encode_data("hello", format="plain")
    assert body == b"hello"
    assert ct == "text/plain; charset=utf-8"


def test_factory_put_encodes_json_by_default():
    factory = AsyncAPIRequestFactory()
    raw = factory.put("/methods/", data={"name": "khan"})
    assert raw.method == "PUT"
    assert json.loads(raw.body) == {"name": "khan"}


def test_factory_patch_encodes_json_by_default():
    factory = AsyncAPIRequestFactory()
    raw = factory.patch("/methods/", data={"name": "khan"})
    assert raw.method == "PATCH"
    assert json.loads(raw.body) == {"name": "khan"}


def test_factory_delete_encodes_json_by_default():
    factory = AsyncAPIRequestFactory()
    raw = factory.delete("/methods/")
    assert raw.method == "DELETE"


def test_factory_options_encodes_json_by_default():
    factory = AsyncAPIRequestFactory()
    raw = factory.options("/methods/")
    assert raw.method == "OPTIONS"


@pytest.mark.django_db
def test_client_logout_clears_credentials_and_force_auth(urls):
    client = AsyncAPIClient()

    class _U:
        is_authenticated = True
        is_active = True

        def __str__(self):
            return "khan"

    client.force_authenticate(user=_U())
    client.credentials(HTTP_X_API_TOKEN="secret-token")
    response = _run(client.get("/private/"))
    assert response.status_code == 200

    client.logout()
    assert client._credentials == {}
    assert client.handler._force_user is None
    assert client.handler._force_token is None
    response = _run(client.get("/private/"))
    assert response.status_code == 403


def test_client_credentials_rejects_non_http_or_content_keys():
    client = AsyncAPIClient()
    with pytest.raises(ValueError, match="HTTP_"):
        client.credentials(X_CUSTOM="custom-value")


def test_client_put_json_default(urls):
    client = AsyncAPIClient()
    response = _run(client.put("/methods/", data={"name": "khan"}))
    assert response.status_code == 200
    assert response.json()["method"] == "PUT"
    assert json.loads(response.json()["body"]) == {"name": "khan"}


def test_client_patch_json_default(urls):
    client = AsyncAPIClient()
    response = _run(client.patch("/methods/", data={"name": "khan"}))
    assert response.status_code == 200
    assert response.json()["method"] == "PATCH"
    assert json.loads(response.json()["body"]) == {"name": "khan"}


def test_client_delete_json_default(urls):
    client = AsyncAPIClient()
    response = _run(client.delete("/methods/", data={"id": 1}))
    assert response.status_code == 200
    assert response.json() == {"method": "DELETE"}


def test_client_options_json_default(urls):
    client = AsyncAPIClient()
    response = _run(client.options("/methods/", data={"x": 1}))
    assert response.status_code == 200


def test_client_head_returns_no_body(urls):
    client = AsyncAPIClient()
    response = _run(client.head("/methods/"))
    assert response.status_code == 200


def test_client_credentials_accepts_content_prefix(urls):
    client = AsyncAPIClient()
    client.credentials(CONTENT_LANGUAGE="en-US")
    response = _run(client.get("/echo/"))
    assert response.status_code == 200
