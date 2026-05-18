import asyncio
import json

import pytest
from django.test import RequestFactory
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from restflow.serializers import Serializer as RestflowSerializer
from restflow.views import AsyncAPIView


def _run(coro):
    return asyncio.run(coro)


class _DRFItemSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


class _RestflowItemSerializer(RestflowSerializer):
    value: int


class _Item:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value


def _bind(view_cls, method="get", path="/", data=None):
    view = view_cls()
    factory = RequestFactory()
    if data is not None:
        raw = getattr(factory, method)(
            path, data=json.dumps(data), content_type="application/json"
        )
    else:
        raw = getattr(factory, method)(path)
    view.request = view.initialize_request(raw)
    view.format_kwarg = None
    return view


def test_avalidated_serializer_with_restflow_serializer_uses_ais_valid():
    class V(AsyncAPIView):
        serializer_class = _RestflowItemSerializer

    view = _bind(V, method="post", data={"value": 7})
    ser = _run(view.avalidated_serializer())
    assert ser.validated_data == {"value": 7}


def test_avalidated_serializer_with_drf_serializer_falls_back_to_sync():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

    view = _bind(V, method="post", data={"value": 9})
    ser = _run(view.avalidated_serializer())
    assert ser.validated_data == {"value": 9}


def test_avalidated_serializer_raises_on_invalid_data():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

    view = _bind(V, method="post", data={"value": "not-int"})
    with pytest.raises(ValidationError):
        _run(view.avalidated_serializer())


def test_aserialized_response_returns_200():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

    view = _bind(V)
    response = _run(view.aserialized_response(_Item(pk=1, value=42)))
    assert response.status_code == 200
    assert response.data["value"] == 42


def test_aserialized_response_with_many_and_status():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

    view = _bind(V)
    items = [_Item(pk=1, value=10), _Item(pk=2, value=20)]
    response = _run(view.aserialized_response(items, many=True, status=201))
    assert response.status_code == 201
    assert len(response.data) == 2


class _StubAsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


class _StubQuerySet:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self

    def order_by(self, *_):
        return self

    async def acount(self):
        return len(self._items)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return _StubQuerySet(self._items[key])
        return self._items[key]

    def __aiter__(self):
        return _StubAsyncIter(self._items).__aiter__()

    def __iter__(self):
        return iter(self._items)


def test_apaginated_response_without_pagination_class():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

    view = _bind(V)
    items = [_Item(pk=i, value=i) for i in range(3)]
    response = _run(view.apaginated_response(items))
    assert response.status_code == 200
    assert len(response.data) == 3


def test_apaginated_response_with_async_paginator():
    from restflow.pagination import (
        PageNumberPagination as AsyncPageNumberPagination,
    )

    class _Page(AsyncPageNumberPagination):
        page_size = 2

    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer
        pagination_class = _Page

    view = _bind(V, path="/?page=1")
    qs = _StubQuerySet([_Item(pk=i, value=i) for i in range(5)])
    response = _run(view.apaginated_response(qs))
    assert response.data["count"] == 5
    assert len(response.data["results"]) == 2


def test_apaginated_response_with_sync_paginator_falls_back():
    class _Page(PageNumberPagination):
        page_size = 2

    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer
        pagination_class = _Page

    view = _bind(V, path="/?page=1")
    items = [_Item(pk=i, value=i) for i in range(4)]
    response = _run(view.apaginated_response(items))
    assert response.data["count"] == 4
    assert len(response.data["results"]) == 2


class _AsyncStubFetcher:
    def __init__(self, key="extra", value="enriched"):
        self.key = key
        self.value = value

    async def afetch(self, items):
        for item in items:
            setattr(item, self.key, self.value)
        return items


def test_aserialized_response_applies_post_fetches():
    class _S(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        extra = drf_serializers.CharField()

    class V(AsyncAPIView):
        serializer_class = _S

    view = _bind(V)
    items = [_Item(pk=1, value=1)]
    response = _run(
        view.aserialized_response(
            items, many=True, post_fetches=[_AsyncStubFetcher()]
        )
    )
    assert response.data[0]["extra"] == "enriched"


class _SyncStubFetcher:
    def fetch(self, items):
        for item in items:
            item.extra = "sync-enriched"
        return items


def test_aserialized_response_post_fetches_falls_back_to_sync_fetch():
    class _S(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        extra = drf_serializers.CharField()

    class V(AsyncAPIView):
        serializer_class = _S

    view = _bind(V)
    items = [_Item(pk=1, value=1)]
    response = _run(
        view.aserialized_response(
            items, many=True, post_fetches=[_SyncStubFetcher()]
        )
    )
    assert response.data[0]["extra"] == "sync-enriched"


class _AsyncNonePaginator:
    async def apaginate_queryset(self, queryset, request, view=None):
        return None


def test_apaginated_response_returns_unpaginated_when_paginator_returns_none():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer
        pagination_class = _AsyncNonePaginator

    view = _bind(V)
    items = [_Item(pk=i, value=i) for i in range(2)]
    response = _run(view.apaginated_response(items))
    assert response.status_code == 200
    assert len(response.data) == 2


def test_async_dispatch_method_not_in_http_method_names():
    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer
        http_method_names = ["get"]

    view = V.as_view()
    factory = RequestFactory()
    raw = factory.post("/", data="{}", content_type="application/json")
    response = _run(view(raw))
    assert response.status_code == 405


class _AsyncAuthRaises:
    async def aauthenticate(self, request):
        from rest_framework import exceptions

        msg = "nope"
        raise exceptions.AuthenticationFailed(msg)

    def authenticate_header(self, request):
        return "Bearer"


def test_async_authentication_apiexception_calls_not_authenticated_and_reraises():
    class V(AsyncAPIView):
        authentication_classes = [_AsyncAuthRaises]
        serializer_class = _DRFItemSerializer

        async def get(self, request, *args, **kwargs):
            from rest_framework.response import Response

            return Response({"ok": True})

    view = V.as_view()
    factory = RequestFactory()
    raw = factory.get("/")
    response = _run(view(raw))
    assert response.status_code == 401


class _AsyncAuthOk:
    async def aauthenticate(self, request):
        return ("user", "auth")

    def authenticate_header(self, request):
        return None


def test_async_authentication_aauthenticate_success_assigns_user():
    class V(AsyncAPIView):
        authentication_classes = [_AsyncAuthOk]
        serializer_class = _DRFItemSerializer

        async def get(self, request, *args, **kwargs):
            from rest_framework.response import Response

            return Response({"u": str(request.user)})

    view = V.as_view()
    factory = RequestFactory()
    raw = factory.get("/")
    response = _run(view(raw))
    assert response.status_code == 200
    assert response.data["u"] == "user"


class _AsyncDenyPermission:
    message = "no"
    code = "denied"

    async def ahas_permission(self, request, view):
        return False


def test_acheck_permissions_denies_with_async_permission():
    class V(AsyncAPIView):
        permission_classes = [_AsyncDenyPermission]
        serializer_class = _DRFItemSerializer

        async def get(self, request, *args, **kwargs):
            from rest_framework.response import Response

            return Response({"ok": True})

    view = V.as_view()
    factory = RequestFactory()
    raw = factory.get("/")
    response = _run(view(raw))
    assert response.status_code == 403


class _DenyObjectPermission:
    message = "no obj"

    def has_permission(self, request, view):
        return True

    async def ahas_object_permission(self, request, view, obj):
        return False


def test_acheck_object_permissions_denies():
    import asyncio as _asyncio

    from rest_framework import exceptions

    class V(AsyncAPIView):
        permission_classes = [_DenyObjectPermission]
        serializer_class = _DRFItemSerializer

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    with pytest.raises(
        (exceptions.PermissionDenied, exceptions.NotAuthenticated)
    ):
        _asyncio.run(
            view.acheck_object_permissions(view.request, object())
        )


class _AsyncBlockingThrottle:
    async def aallow_request(self, request, view):
        return False

    def wait(self):
        return 1.5


def test_acheck_throttles_throttled_with_wait_duration():
    from rest_framework.exceptions import Throttled

    class V(AsyncAPIView):
        throttle_classes = [_AsyncBlockingThrottle]
        serializer_class = _DRFItemSerializer

        async def get(self, request, *args, **kwargs):
            from rest_framework.response import Response

            return Response({"ok": True})

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    with pytest.raises(Throttled):
        _run(view.acheck_throttles(view.request))


class _NoneWaitThrottle:
    async def aallow_request(self, request, view):
        return False

    def wait(self):
        return None


def test_acheck_throttles_with_none_wait_uses_default():
    from rest_framework.exceptions import Throttled

    class V(AsyncAPIView):
        throttle_classes = [_NoneWaitThrottle]
        serializer_class = _DRFItemSerializer

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    with pytest.raises(Throttled):
        _run(view.acheck_throttles(view.request))


class _SyncAllowThrottle:
    def allow_request(self, request, view):
        return True

    def wait(self):
        return None


def test_acheck_throttles_with_sync_throttle_falls_back():
    class V(AsyncAPIView):
        throttle_classes = [_SyncAllowThrottle]
        serializer_class = _DRFItemSerializer

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    _run(view.acheck_throttles(view.request))


def test_async_handle_exception_uncaught_reraises():
    msg = "boom"

    class V(AsyncAPIView):
        serializer_class = _DRFItemSerializer

        async def get(self, request, *args, **kwargs):
            raise RuntimeError(msg)

    view = V()
    factory = RequestFactory()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.headers = {}
    with pytest.raises(RuntimeError, match="boom"):
        _run(view.ahandle_exception(RuntimeError(msg)))


class _SyncOnlyPermission:
    def has_permission(self, request, view):
        return True


def test_call_has_permission_falls_back_to_sync():
    class V(AsyncAPIView):
        permission_classes = [_SyncOnlyPermission]
        serializer_class = _DRFItemSerializer

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    _run(view.acheck_permissions(view.request))


class _SyncOnlyObjectPermission:
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return True


def test_call_has_object_permission_falls_back_to_sync():
    class V(AsyncAPIView):
        permission_classes = [_SyncOnlyObjectPermission]
        serializer_class = _DRFItemSerializer

    factory = RequestFactory()
    view = V()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    _run(view.acheck_object_permissions(view.request, object()))
