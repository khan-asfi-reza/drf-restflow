import asyncio
import inspect
import json
from unittest.mock import MagicMock

from django.test import RequestFactory
from rest_framework import serializers as drf_serializers
from rest_framework.routers import DefaultRouter

from restflow.views import (
    AsyncModelViewSet,
    AsyncReadOnlyModelViewSet,
    AsyncViewSet,
)


def _run(coro):
    return asyncio.run(coro)


class _Item:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value


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


class _ItemSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


def _make_viewset(items=None):
    items = items or []

    class _VS(AsyncModelViewSet):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

        async def aperform_create(self, serializer):
            new = _Item(pk=len(items) + 1, **serializer.validated_data)
            items.append(new)

        async def aperform_update(self, serializer):
            for k, v in serializer.validated_data.items():
                setattr(serializer.instance, k, v)

        async def aperform_destroy(self, instance):
            items.remove(instance)

    return _VS, items


def _request(method, path="/", data=None):
    factory = RequestFactory()
    if data is not None:
        return getattr(factory, method)(
            path, data=json.dumps(data), content_type="application/json"
        )
    return getattr(factory, method)(path)


def test_as_view_with_actions_returns_coroutine():
    VS, _ = _make_viewset()
    view = VS.as_view({"get": "list"})
    assert inspect.iscoroutinefunction(view)


def test_async_modelviewset_list_action():
    VS, _ = _make_viewset(items=[_Item(pk=1, value=10), _Item(pk=2, value=20)])
    view = VS.as_view({"get": "list"})
    response = _run(view(_request("get")))
    assert response.status_code == 200
    assert len(response.data) == 2


def test_async_modelviewset_retrieve_action():
    item = _Item(pk=11, value=999)
    VS, _ = _make_viewset(items=[item])
    view = VS.as_view({"get": "retrieve"})
    response = _run(view(_request("get"), pk=11))
    assert response.status_code == 200
    assert response.data["value"] == 999


def test_async_modelviewset_create_action():
    VS, items = _make_viewset()
    view = VS.as_view({"post": "create"})
    response = _run(view(_request("post", data={"value": 5})))
    assert response.status_code == 201
    assert len(items) == 1
    assert items[0].value == 5


def test_async_modelviewset_update_action():
    item = _Item(pk=1, value=1)
    VS, _ = _make_viewset(items=[item])
    view = VS.as_view({"put": "update"})
    response = _run(view(_request("put", data={"value": 100}), pk=1))
    assert response.status_code == 200
    assert item.value == 100


def test_async_modelviewset_destroy_action():
    item = _Item(pk=1, value=1)
    VS, items = _make_viewset(items=[item])
    view = VS.as_view({"delete": "destroy"})
    response = _run(view(_request("delete"), pk=1))
    assert response.status_code == 204
    assert items == []


def test_default_router_registers_async_viewset():
    VS, _ = _make_viewset()
    router = DefaultRouter()
    router.register(r"items", VS, basename="item")
    urls = router.urls

    list_pattern = next(u for u in urls if "items" in str(u.pattern) and "<" not in str(u.pattern))
    assert inspect.iscoroutinefunction(list_pattern.callback)


def test_async_readonly_modelviewset_list_action():
    items = [_Item(pk=1, value=1)]

    class _RO(AsyncReadOnlyModelViewSet):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

    view = _RO.as_view({"get": "list"})
    response = _run(view(_request("get")))
    assert response.status_code == 200
    assert len(response.data) == 1


def test_async_viewset_dispatches_action():
    seen = {}

    class _VS(AsyncViewSet):
        async def list(self, request, *args, **kwargs):
            seen["called"] = True
            from rest_framework.response import Response

            return Response({"ok": True})

    view = _VS.as_view({"get": "list"})
    response = _run(view(_request("get")))
    assert seen["called"] is True
    assert response.status_code == 200


def test_as_view_without_actions_raises_typeerror():
    import pytest

    with pytest.raises(TypeError, match="actions"):
        AsyncViewSet.as_view()


def test_as_view_with_http_method_kwarg_raises_typeerror():
    import pytest

    with pytest.raises(TypeError, match="get"):
        AsyncViewSet.as_view(actions={"get": "list"}, get="list")


def test_as_view_with_invalid_kwarg_raises_typeerror():
    import pytest

    with pytest.raises(TypeError, match="invalid keyword"):
        AsyncViewSet.as_view(actions={"get": "list"}, bogus_kwarg=True)


def test_as_view_with_name_and_suffix_raises_typeerror():
    import pytest

    with pytest.raises(TypeError, match="mutually exclusive"):
        AsyncViewSet.as_view(
            actions={"get": "list"}, name="A", suffix="B"
        )


def test_async_viewset_mixin_get_serializer_class_falls_back_to_attribute():
    from restflow.views.viewsets import AsyncViewSetMixin

    class VS(AsyncViewSetMixin):
        serializer_class = _ItemSerializer

    view = VS()
    view.action = None
    assert view.get_serializer_class() is _ItemSerializer


def test_async_viewset_mixin_get_request_serializer_class_falls_back():
    from restflow.views.viewsets import AsyncViewSetMixin

    class VS(AsyncViewSetMixin):
        serializer_class = _ItemSerializer

    view = VS()
    view.action = None
    assert view.get_request_serializer_class() is _ItemSerializer


def test_async_viewset_mixin_get_response_serializer_class_falls_back():
    from restflow.views.viewsets import AsyncViewSetMixin

    class VS(AsyncViewSetMixin):
        serializer_class = _ItemSerializer

    view = VS()
    view.action = None
    assert view.get_response_serializer_class() is _ItemSerializer


def test_async_viewset_mixin_get_pagination_class_falls_back_to_attribute():
    from rest_framework.pagination import PageNumberPagination

    from restflow.views.viewsets import AsyncViewSetMixin

    class _Pager(PageNumberPagination):
        pass

    class VS(AsyncViewSetMixin):
        pagination_class = _Pager

    view = VS()
    view.action = None
    assert view.get_pagination_class() is _Pager


def test_action_config_queryset_passthrough_when_no_all_method():
    from restflow.views import ActionConfig

    sentinel_qs = [_Item(pk=1, value=42)]

    class VS(AsyncViewSet):
        serializer_class = _ItemSerializer
        action_configs = {
            "list": ActionConfig(queryset=sentinel_qs),
        }

    factory = RequestFactory()
    view = VS()
    view.request = factory.get("/")
    view.action = "list"
    assert view.get_queryset() is sentinel_qs


def test_as_view_does_not_mutate_caller_actions_dict():
    actions = {"get": "list"}
    AsyncReadOnlyModelViewSet.as_view(actions)
    assert actions == {"get": "list"}


def test_as_view_does_not_set_class_level_attrs():
    class _VS(AsyncViewSet):
        pass

    if "name" in _VS.__dict__:
        del _VS.__dict__["name"]

    _VS.as_view({"get": "list"}, name="custom-name", basename="custom-basename")
    assert "name" not in _VS.__dict__
    assert "basename" not in _VS.__dict__
