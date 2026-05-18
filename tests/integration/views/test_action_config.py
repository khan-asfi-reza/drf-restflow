import asyncio
import json
from unittest.mock import MagicMock

from django.test import RequestFactory
from rest_framework import serializers as drf_serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from restflow.views import (
    ActionConfig,
    AsyncModelViewSet,
    AsyncViewSet,
)


def _run(coro):
    return asyncio.run(coro)


class _ListSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    name = drf_serializers.CharField()


class _DetailSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    name = drf_serializers.CharField()
    bio = drf_serializers.CharField(required=False, default="")


class _CreateSer(drf_serializers.Serializer):
    name = drf_serializers.CharField()
    password = drf_serializers.CharField(write_only=True)


class _DefaultSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    name = drf_serializers.CharField()


class _Item:
    def __init__(self, pk, name):
        self.pk = pk
        self.name = name


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


def _bind(viewset_cls, action, **extra):
    view = viewset_cls(**extra)
    view.action = action
    factory = RequestFactory()
    view.request = factory.get("/")
    view.format_kwarg = None
    return view


def test_action_config_picks_serializer_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(serializer_class=_ListSer),
            "retrieve": ActionConfig(serializer_class=_DetailSer),
            "create": ActionConfig(serializer_class=_CreateSer),
        }

    assert _bind(VS, "list").get_serializer_class() is _ListSer
    assert _bind(VS, "retrieve").get_serializer_class() is _DetailSer
    assert _bind(VS, "create").get_serializer_class() is _CreateSer


def test_unmapped_action_falls_through_to_serializer_class():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(serializer_class=_ListSer),
        }

    assert _bind(VS, "destroy").get_serializer_class() is _DefaultSer


def test_mapped_action_with_none_serializer_class_falls_through():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(permission_classes=[AllowAny]),
        }

    assert _bind(VS, "list").get_serializer_class() is _DefaultSer


def test_action_config_picks_permissions_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        permission_classes = [IsAuthenticated]
        action_configs = {
            "list": ActionConfig(permission_classes=[AllowAny]),
        }

    list_perms = _bind(VS, "list").get_permissions()
    assert len(list_perms) == 1
    assert isinstance(list_perms[0], AllowAny)

    create_perms = _bind(VS, "create").get_permissions()
    assert len(create_perms) == 1
    assert isinstance(create_perms[0], IsAuthenticated)


def test_action_config_picks_throttles_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        throttle_classes = [UserRateThrottle]
        action_configs = {
            "create": ActionConfig(throttle_classes=[AnonRateThrottle]),
        }

    list_throttles = _bind(VS, "list").get_throttles()
    assert any(isinstance(t, UserRateThrottle) for t in list_throttles)

    create_throttles = _bind(VS, "create").get_throttles()
    assert any(isinstance(t, AnonRateThrottle) for t in create_throttles)


def test_action_config_picks_parsers_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "upload": ActionConfig(parser_classes=[MultiPartParser]),
        }

    upload_parsers = _bind(VS, "upload").get_parsers()
    assert any(isinstance(p, MultiPartParser) for p in upload_parsers)

    list_parsers = _bind(VS, "list").get_parsers()
    assert any(isinstance(p, JSONParser) for p in list_parsers)


def test_action_config_picks_renderers_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(renderer_classes=[JSONRenderer]),
        }

    list_renderers = _bind(VS, "list").get_renderers()
    assert len(list_renderers) == 1
    assert isinstance(list_renderers[0], JSONRenderer)

    create_renderers = _bind(VS, "create").get_renderers()
    assert any(isinstance(r, BrowsableAPIRenderer) for r in create_renderers)


def test_action_none_falls_back_to_class_attributes():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        permission_classes = [IsAuthenticated]
        action_configs = {
            "list": ActionConfig(
                serializer_class=_ListSer,
                permission_classes=[AllowAny],
            ),
        }

    view = VS()
    factory = RequestFactory()
    view.request = factory.get("/")

    assert view.get_serializer_class() is _DefaultSer
    perms = view.get_permissions()
    assert len(perms) == 1
    assert isinstance(perms[0], IsAuthenticated)


def test_custom_action_name_as_config_key():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "archive": ActionConfig(serializer_class=_ListSer),
        }

    assert _bind(VS, "archive").get_serializer_class() is _ListSer


def test_helpers_pick_serializer_via_action_config():
    items = [_Item(pk=1, name="a"), _Item(pk=2, name="b")]

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(serializer_class=_ListSer),
        }

        def get_queryset(self):
            return _StubQuerySet(items)

    view = VS.as_view({"get": "list"})
    factory = RequestFactory()
    raw = factory.get("/")
    response = _run(view(raw))

    assert response.status_code == 200
    assert len(response.data) == 2
    assert "name" in response.data[0]


def test_helpers_pick_create_serializer_via_action_config():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "create": ActionConfig(serializer_class=_CreateSer),
        }

        def get_queryset(self):
            return _StubQuerySet([])

        async def aperform_create(self, serializer):
            pass

    view = VS.as_view({"post": "create"})
    factory = RequestFactory()
    raw = factory.post(
        "/",
        data=json.dumps({"name": "x", "password": "secret"}),
        content_type="application/json",
    )
    response = _run(view(raw))
    assert response.status_code == 201


def test_action_config_is_frozen_dataclass():
    cfg = ActionConfig(serializer_class=_DefaultSer)
    try:
        cfg.serializer_class = _ListSer
    except Exception:
        return
    msg = "ActionConfig should be frozen but allowed reassignment"
    raise AssertionError(msg)


def test_action_config_preserves_dataclass_equality():
    a = ActionConfig(serializer_class=_DefaultSer)
    b = ActionConfig(serializer_class=_DefaultSer)
    assert a == b


def test_async_viewset_without_generic_can_use_action_configs():
    class VS(AsyncViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "custom": ActionConfig(serializer_class=_ListSer),
        }

    assert _bind(VS, "custom").get_serializer_class() is _ListSer
    assert _bind(VS, "other").get_serializer_class() is _DefaultSer


# Pagination + queryset additions


from restflow.pagination import LimitOffsetPagination, PageNumberPagination  # noqa: I001


class _ClassPager(PageNumberPagination):
    page_size = 2


class _ActionPager(LimitOffsetPagination):
    default_limit = 4


def test_action_config_picks_pagination_class_per_action():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        pagination_class = _ClassPager
        action_configs = {
            "list": ActionConfig(pagination_class=_ActionPager),
        }

    assert _bind(VS, "list").get_pagination_class() is _ActionPager
    assert _bind(VS, "retrieve").get_pagination_class() is _ClassPager


def test_unmapped_action_falls_through_to_pagination_class():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        pagination_class = _ClassPager
        action_configs = {
            "list": ActionConfig(serializer_class=_ListSer),
        }

    assert _bind(VS, "list").get_pagination_class() is _ClassPager


def test_paginator_property_honors_action_config():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        pagination_class = _ClassPager
        action_configs = {
            "list": ActionConfig(pagination_class=_ActionPager),
        }

    list_view = _bind(VS, "list")
    assert isinstance(list_view.paginator, _ActionPager)

    retrieve_view = _bind(VS, "retrieve")
    assert isinstance(retrieve_view.paginator, _ClassPager)


def test_apaginated_response_uses_action_config_paginator():
    items = [_Item(pk=i, name=f"u{i}") for i in range(6)]

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        pagination_class = _ClassPager  # page_size=2 default
        action_configs = {
            "list": ActionConfig(pagination_class=_ActionPager),  # limit=4 default
        }

        def get_queryset(self):
            return _StubQuerySet(items)

    view = VS.as_view({"get": "list"})
    factory = RequestFactory()
    response = _run(view(factory.get("/")))
    assert response.status_code == 200
    assert "results" in response.data
    assert len(response.data["results"]) == 4


def test_action_config_picks_static_queryset_per_action():
    archived = [_Item(pk=1, name="archived")]
    active = [_Item(pk=2, name="active"), _Item(pk=3, name="other")]

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        queryset = _StubQuerySet(active)
        action_configs = {
            "archive": ActionConfig(queryset=_StubQuerySet(archived)),
        }

    archive_view = _bind(VS, "archive")
    assert list(archive_view.get_queryset()) == archived

    list_view = _bind(VS, "list")
    assert list(list_view.get_queryset()) == active


def test_action_config_picks_callable_queryset_with_self():
    captured = {}

    def queryset_fn(self):
        captured["view"] = self
        return _StubQuerySet([_Item(pk=99, name="custom")])

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        queryset = _StubQuerySet([])
        action_configs = {
            "list": ActionConfig(queryset=queryset_fn),
        }

    view = _bind(VS, "list")
    qs = view.get_queryset()
    assert captured["view"] is view
    assert next(iter(qs)).pk == 99


def test_callable_queryset_can_read_request_and_kwargs():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        queryset = _StubQuerySet([])
        action_configs = {
            "list": ActionConfig(
                queryset=lambda self: _StubQuerySet(
                    [_Item(pk=1, name=self.request.method)]
                ),
            ),
        }

    view = _bind(VS, "list")
    qs = view.get_queryset()
    assert next(iter(qs)).name == "GET"


def test_unmapped_action_falls_through_to_class_queryset():
    items = [_Item(pk=7, name="default")]

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        queryset = _StubQuerySet(items)
        action_configs = {
            "archive": ActionConfig(
                queryset=_StubQuerySet([_Item(pk=99, name="archived")]),
            ),
        }

    view = _bind(VS, "list")
    assert list(view.get_queryset()) == items


def test_static_queryset_is_cloned_via_all_on_each_call():
    calls = {"count": 0}
    base_items = [_Item(pk=1, name="x")]

    class _CountingQuerySet(_StubQuerySet):
        def all(self):
            calls["count"] += 1
            return _CountingQuerySet(self._items)

    counting = _CountingQuerySet(base_items)

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        queryset = _StubQuerySet([])
        action_configs = {
            "list": ActionConfig(queryset=counting),
        }

    view = _bind(VS, "list")
    view.get_queryset()
    view.get_queryset()
    assert calls["count"] == 2


def test_get_queryset_raises_when_no_queryset_anywhere():
    import pytest

    class VS(AsyncViewSet):
        serializer_class = _DefaultSer
        action_configs = {}

    view = _bind(VS, "list")
    with pytest.raises(AssertionError, match="queryset"):
        view.get_queryset()
