import asyncio
import json
from unittest.mock import MagicMock

import pytest
from django.test import RequestFactory, override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.permissions import IsAuthenticated
from restflow.serializers import Serializer as RestflowSerializer
from restflow.test import AsyncAPIClient
from restflow.views import (
    ActionConfig,
    APIView,
    AsyncAPIView,
    AsyncCreateAPIView,
    AsyncListCreateAPIView,
    AsyncListAPIView,
    AsyncModelViewSet,
    AsyncRetrieveAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
    AsyncViewSet,
)


def _run(coro):
    return asyncio.run(coro)


class _Item:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value


class _DRFItemSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


class _RestflowItemSerializer(RestflowSerializer):
    value: int


class _StubAsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


class _StubQuerySet:
    model = MagicMock()

    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self

    def order_by(self, *_):
        return self

    def filter(self, **kwargs):
        filtered = [
            i for i in self._items
            if all(getattr(i, k) == v for k, v in kwargs.items())
        ]
        return _StubQuerySet(filtered)

    async def acount(self):
        return len(self._items)

    async def aget(self, **filter_kwargs):
        for item in self._items:
            if all(getattr(item, k) == v for k, v in filter_kwargs.items()):
                return item
        raise self.model.DoesNotExist()

    def __getitem__(self, key):
        if isinstance(key, slice):
            return _StubQuerySet(self._items[key])
        return self._items[key]

    def __aiter__(self):
        return _StubAsyncIter(self._items).__aiter__()

    def __iter__(self):
        return iter(self._items)


_GLOBAL_ITEMS = []


class _PingView(APIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"sync": True})

    def post(self, request):
        ser = self.validated_serializer()
        return Response(ser.validated_data, status=201)


class _AsyncPingView(AsyncAPIView):
    serializer_class = _RestflowItemSerializer
    permission_classes = [AllowAny]

    async def get(self, request):
        return Response({"async": True})

    async def post(self, request):
        ser = await self.avalidated_serializer()
        return Response(ser.validated_data, status=201)


class _MixedHandlerView(AsyncAPIView):
    """async dispatch with sync and async handlers in same class."""

    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"shape": "sync-handler"})

    async def post(self, request):
        return Response({"shape": "async-handler"}, status=201)


class _DenyView(AsyncAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"ok": True})


class _ItemListView(AsyncListAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return _StubQuerySet(_GLOBAL_ITEMS)


class _ItemRetrieveView(AsyncRetrieveAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return _StubQuerySet(_GLOBAL_ITEMS)


class _ItemListCreateView(AsyncListCreateAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return _StubQuerySet(_GLOBAL_ITEMS)

    async def aperform_create(self, serializer):
        new = _Item(pk=len(_GLOBAL_ITEMS) + 1, **serializer.validated_data)
        _GLOBAL_ITEMS.append(new)


class _ItemFullView(AsyncRetrieveUpdateDestroyAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return _StubQuerySet(_GLOBAL_ITEMS)

    async def aperform_update(self, serializer):
        instance = serializer.instance
        for k, v in serializer.validated_data.items():
            setattr(instance, k, v)

    async def aperform_destroy(self, instance):
        _GLOBAL_ITEMS.remove(instance)


class _Items(AsyncModelViewSet):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]
    action_configs = {
        "list": ActionConfig(serializer_class=_DRFItemSerializer),
    }

    def get_queryset(self):
        return _StubQuerySet(_GLOBAL_ITEMS)

    async def aperform_create(self, serializer):
        new = _Item(pk=len(_GLOBAL_ITEMS) + 1, **serializer.validated_data)
        _GLOBAL_ITEMS.append(new)

    async def aperform_update(self, serializer):
        for k, v in serializer.validated_data.items():
            setattr(serializer.instance, k, v)

    async def aperform_destroy(self, instance):
        _GLOBAL_ITEMS.remove(instance)


class _CreateOnlyView(AsyncCreateAPIView):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    async def aperform_create(self, serializer):
        new = _Item(pk=len(_GLOBAL_ITEMS) + 1, **serializer.validated_data)
        _GLOBAL_ITEMS.append(new)


urlpatterns = [
    path("ping/", _PingView.as_view()),
    path("aping/", _AsyncPingView.as_view()),
    path("mixed/", _MixedHandlerView.as_view()),
    path("deny/", _DenyView.as_view()),
    path("items/", _ItemListView.as_view()),
    path("items/<int:pk>/", _ItemRetrieveView.as_view()),
    path("items-cr/", _ItemListCreateView.as_view()),
    path("items-full/<int:pk>/", _ItemFullView.as_view()),
    path(
        "vs/",
        _Items.as_view({"get": "list", "post": "create"}),
    ),
    path(
        "vs/<int:pk>/",
        _Items.as_view(
            {"get": "retrieve", "put": "update", "delete": "destroy"}
        ),
    ),
    path("create-only/", _CreateOnlyView.as_view()),
]


@pytest.fixture(autouse=True)
def _reset_items():
    _GLOBAL_ITEMS.clear()
    yield
    _GLOBAL_ITEMS.clear()


@pytest.fixture(autouse=True)
def _urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


def test_sync_apiview_get_round_trip():
    from django.test import Client

    response = Client().get("/ping/")
    assert response.status_code == 200
    assert response.json() == {"sync": True}


def test_sync_apiview_post_round_trip():
    from django.test import Client

    response = Client().post(
        "/ping/", data=json.dumps({"value": 5}), content_type="application/json"
    )
    assert response.status_code == 201
    assert response.json() == {"value": 5}


def test_sync_apiview_post_invalid_returns_400():
    from django.test import Client

    response = Client().post(
        "/ping/", data=json.dumps({"value": "x"}), content_type="application/json"
    )
    assert response.status_code == 400


def test_async_apiview_get_round_trip():
    response = _run(AsyncAPIClient().get("/aping/"))
    assert response.status_code == 200
    assert response.json() == {"async": True}


def test_async_apiview_post_with_restflow_serializer():
    response = _run(
        AsyncAPIClient().post("/aping/", data={"value": 7}, format="json")
    )
    assert response.status_code == 201
    assert response.json() == {"value": 7}


def test_async_apiview_post_invalid_returns_400():
    response = _run(
        AsyncAPIClient().post("/aping/", data={"value": "x"}, format="json")
    )
    assert response.status_code == 400


def test_mixed_handler_async_view_serves_both_sync_and_async_handlers():
    client = AsyncAPIClient()
    get_resp = _run(client.get("/mixed/"))
    assert get_resp.status_code == 200
    assert get_resp.json() == {"shape": "sync-handler"}
    post_resp = _run(client.post("/mixed/", data={}, format="json"))
    assert post_resp.status_code == 201
    assert post_resp.json() == {"shape": "async-handler"}


def test_async_apiview_method_not_allowed_returns_405():
    response = _run(
        AsyncAPIClient().delete("/aping/", data={}, format="json")
    )
    assert response.status_code == 405


def test_async_apiview_options_round_trip():
    response = _run(AsyncAPIClient().options("/aping/"))
    assert response.status_code == 200


def test_async_apiview_head_round_trip():
    response = _run(AsyncAPIClient().head("/aping/"))
    assert response.status_code == 200


def test_async_view_returns_403_on_unauthenticated():
    response = _run(AsyncAPIClient().get("/deny/"))
    assert response.status_code in (401, 403)


def test_async_view_authenticated_via_force_authenticate():
    client = AsyncAPIClient()
    user = MagicMock()
    user.is_authenticated = True
    client.force_authenticate(user=user)
    response = _run(client.get("/deny/"))
    assert response.status_code == 200


def test_async_list_view_round_trip():
    _GLOBAL_ITEMS.extend([_Item(pk=1, value=10), _Item(pk=2, value=20)])
    response = _run(AsyncAPIClient().get("/items/"))
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_async_retrieve_view_round_trip():
    _GLOBAL_ITEMS.append(_Item(pk=42, value=999))
    response = _run(AsyncAPIClient().get("/items/42/"))
    assert response.status_code == 200
    assert response.json()["value"] == 999


def test_async_retrieve_view_404():
    response = _run(AsyncAPIClient().get("/items/999/"))
    assert response.status_code == 404


def test_async_list_create_round_trip_post_then_list():
    client = AsyncAPIClient()
    create = _run(client.post("/items-cr/", data={"value": 7}, format="json"))
    assert create.status_code == 201
    listing = _run(client.get("/items-cr/"))
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_async_full_round_trip_get_put_patch_delete():
    _GLOBAL_ITEMS.append(_Item(pk=1, value=1))
    client = AsyncAPIClient()
    get_resp = _run(client.get("/items-full/1/"))
    assert get_resp.status_code == 200
    put_resp = _run(
        client.put("/items-full/1/", data={"value": 99}, format="json")
    )
    assert put_resp.status_code == 200
    patch_resp = _run(
        client.patch("/items-full/1/", data={"value": 33}, format="json")
    )
    assert patch_resp.status_code == 200
    delete_resp = _run(client.delete("/items-full/1/", data={}, format="json"))
    assert delete_resp.status_code == 204
    assert _GLOBAL_ITEMS == []


def test_viewset_list_and_create_round_trip():
    client = AsyncAPIClient()
    create = _run(client.post("/vs/", data={"value": 5}, format="json"))
    assert create.status_code == 201
    listing = _run(client.get("/vs/"))
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_viewset_retrieve_update_destroy_round_trip():
    _GLOBAL_ITEMS.append(_Item(pk=99, value=100))
    client = AsyncAPIClient()
    get_resp = _run(client.get("/vs/99/"))
    assert get_resp.status_code == 200
    put_resp = _run(client.put("/vs/99/", data={"value": 1}, format="json"))
    assert put_resp.status_code == 200
    delete_resp = _run(client.delete("/vs/99/", data={}, format="json"))
    assert delete_resp.status_code == 204


def test_create_only_view_get_returns_405():
    response = _run(AsyncAPIClient().get("/create-only/"))
    assert response.status_code == 405


def test_async_apiview_dispatch_invalid_method_returns_405():
    response = _run(AsyncAPIClient().get("/create-only/"))
    assert response.status_code == 405


def test_async_apiview_with_unsupported_content_type():
    factory = RequestFactory()
    raw = factory.post("/aping/", data="<x></x>", content_type="text/xml")
    response = _run(_AsyncPingView.as_view()(raw))
    assert response.status_code in (415, 400)


class _ResponseSplitView(AsyncAPIView):
    request_serializer_class = _DRFItemSerializer
    response_serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]

    async def post(self, request):
        ser = await self.avalidated_serializer()
        return await self.aserialized_response(
            type("I", (), {"value": ser.validated_data["value"], "pk": 1})()
        )


def test_request_response_split_classes_routed():
    view = _ResponseSplitView()
    factory = RequestFactory()
    view.request = view.initialize_request(
        factory.post(
            "/", data=json.dumps({"value": 5}), content_type="application/json"
        )
    )
    view.format_kwarg = None
    assert view.get_request_serializer_class() is _DRFItemSerializer
    assert view.get_response_serializer_class() is _DRFItemSerializer


class _PerActionViewSet(AsyncViewSet):
    permission_classes = [AllowAny]

    async def list(self, request):
        return Response({"act": "list"})

    async def custom_action(self, request):
        return Response({"act": "custom"})


def test_viewset_dispatches_custom_action_via_as_view():
    view = _PerActionViewSet.as_view({"get": "custom_action"})
    factory = RequestFactory()
    response = _run(view(factory.get("/")))
    assert response.status_code == 200
    assert response.data == {"act": "custom"}


class _SeparateInOutSer(RestflowSerializer):
    value: int


class _OutSer(drf_serializers.Serializer):
    value = drf_serializers.IntegerField()
    note = drf_serializers.CharField(required=False, default="ok")


class _InOutVS(AsyncViewSet):
    permission_classes = [AllowAny]
    request_serializer_class = _SeparateInOutSer
    response_serializer_class = _OutSer

    async def create(self, request):
        ser = await self.avalidated_serializer()
        instance = type("I", (), {"value": ser.validated_data["value"]})()
        return await self.aserialized_response(instance, status=201)


def test_viewset_separate_request_response_serializers():
    view = _InOutVS.as_view({"post": "create"})
    factory = RequestFactory()
    raw = factory.post(
        "/", data=json.dumps({"value": 7}), content_type="application/json"
    )
    response = _run(view(raw))
    assert response.status_code == 201
    assert response.data["value"] == 7
    assert response.data["note"] == "ok"


class _ActionScopedView(AsyncModelViewSet):
    serializer_class = _DRFItemSerializer
    permission_classes = [AllowAny]
    action_configs = {
        "list": ActionConfig(queryset=lambda self: _StubQuerySet(_GLOBAL_ITEMS)),
        "retrieve": ActionConfig(queryset=lambda self: _StubQuerySet(_GLOBAL_ITEMS)),
    }


def test_action_config_callable_queryset_resolved_per_request():
    _GLOBAL_ITEMS.append(_Item(pk=5, value=5))
    view = _ActionScopedView.as_view({"get": "list"})
    factory = RequestFactory()
    response = _run(view(factory.get("/")))
    assert response.status_code == 200
    assert len(response.data) == 1


class _AlternateAuth:
    async def aauthenticate(self, request):
        return None

    def authenticate_header(self, request):
        return "Bearer"


class _OkAuth:
    async def aauthenticate(self, request):
        user = MagicMock()
        user.is_authenticated = True
        return (user, None)

    def authenticate_header(self, request):
        return "Bearer"


def test_authenticator_chain_first_returns_none_second_succeeds():
    class V(AsyncAPIView):
        permission_classes = [AllowAny]
        authentication_classes = [_AlternateAuth, _OkAuth]
        serializer_class = _DRFItemSerializer

        async def get(self, request):
            return Response({"u": str(request.user)})

    factory = RequestFactory()
    response = _run(V.as_view()(factory.get("/")))
    assert response.status_code == 200


class _SerWithAsave(drf_serializers.Serializer):
    value = drf_serializers.IntegerField()
    pk = drf_serializers.IntegerField(required=False)

    async def asave(self, **kwargs):
        instance = type("I", (), {**self.validated_data, **kwargs, "pk": 1})()
        self._instance = instance
        return instance

    async def ais_valid(self, raise_exception=False):
        return self.is_valid(raise_exception=raise_exception)


def test_async_create_uses_serializer_async_paths():
    class V(AsyncCreateAPIView):
        serializer_class = _SerWithAsave
        permission_classes = [AllowAny]

    factory = RequestFactory()
    raw = factory.post(
        "/", data=json.dumps({"value": 9}), content_type="application/json"
    )
    response = _run(V.as_view()(raw))
    assert response.status_code == 201
    assert response.data["value"] == 9
