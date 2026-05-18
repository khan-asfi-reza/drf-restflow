import asyncio
import json
from unittest.mock import MagicMock

from django.test import RequestFactory
from rest_framework import serializers as drf_serializers

from restflow.views import (
    AsyncCreateAPIView,
    AsyncDestroyAPIView,
    AsyncListAPIView,
    AsyncRetrieveAPIView,
    AsyncUpdateAPIView,
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

    def filter(self, *args, **kwargs):
        filtered = [
            i
            for i in self._items
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


class _ItemSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


def _request(method, path="/", data=None):
    factory = RequestFactory()
    if data is not None:
        return getattr(factory, method)(
            path, data=json.dumps(data), content_type="application/json"
        )
    return getattr(factory, method)(path)


def test_async_list_apiview_returns_records():
    items = [_Item(pk=i, value=i * 10) for i in range(3)]

    class View(AsyncListAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

    view = View.as_view()
    response = _run(view(_request("get")))
    assert response.status_code == 200
    assert len(response.data) == 3


def test_async_retrieve_apiview_returns_record():
    item = _Item(pk=1, value=42)

    class View(AsyncRetrieveAPIView):
        serializer_class = _ItemSerializer
        lookup_field = "pk"

        def get_queryset(self):
            return _StubQuerySet([item])

    view = View.as_view()
    response = _run(view(_request("get"), pk=1))
    assert response.status_code == 200
    assert response.data["value"] == 42


def test_async_retrieve_apiview_404_for_missing():
    class View(AsyncRetrieveAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet([])

    view = View.as_view()
    response = _run(view(_request("get"), pk=99))
    assert response.status_code == 404


def test_async_create_apiview_returns_201_and_calls_aperform_create():
    seen = {}

    class View(AsyncCreateAPIView):
        serializer_class = _ItemSerializer

        async def aperform_create(self, serializer):
            seen["data"] = serializer.validated_data

    response = _run(View.as_view()(_request("post", data={"value": 7})))
    assert response.status_code == 201
    assert seen["data"]["value"] == 7


def test_async_update_apiview_calls_aperform_update():
    item = _Item(pk=1, value=1)
    seen = {}

    class View(AsyncUpdateAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

        async def aperform_update(self, serializer):
            seen["data"] = serializer.validated_data

    response = _run(
        View.as_view()(_request("put", data={"value": 99}), pk=1)
    )
    assert response.status_code == 200
    assert seen["data"]["value"] == 99


def test_async_update_apiview_patch_calls_partial_update():
    item = _Item(pk=1, value=1)

    class View(AsyncUpdateAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

        async def aperform_update(self, serializer):
            for k, v in serializer.validated_data.items():
                setattr(item, k, v)

    response = _run(
        View.as_view()(_request("patch", data={"value": 12}), pk=1)
    )
    assert response.status_code == 200
    assert item.value == 12


def test_async_destroy_apiview_calls_aperform_destroy():
    item = _Item(pk=1, value=1)
    seen = {}

    class View(AsyncDestroyAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

        async def aperform_destroy(self, instance):
            seen["instance"] = instance

    response = _run(View.as_view()(_request("delete"), pk=1))
    assert response.status_code == 204
    assert seen["instance"] is item


from restflow.views import (
    AsyncGenericAPIView,
    AsyncListCreateAPIView,
    AsyncRetrieveDestroyAPIView,
    AsyncRetrieveUpdateAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
)


class _AsyncFilterBackend:
    async def afilter_queryset(self, request, queryset, view):
        return queryset


class _SyncFilterBackend:
    def filter_queryset(self, request, queryset, view):
        return queryset


def test_afilter_queryset_calls_async_backend():
    items = [_Item(pk=i, value=i) for i in range(2)]

    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        filter_backends = [_AsyncFilterBackend]

        def get_queryset(self):
            return _StubQuerySet(items)

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {}
    out = _run(view.afilter_queryset(view.get_queryset()))
    assert list(out) == items


def test_afilter_queryset_falls_back_to_sync_backend():
    items = [_Item(pk=i, value=i) for i in range(2)]

    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        filter_backends = [_SyncFilterBackend]

        def get_queryset(self):
            return _StubQuerySet(items)

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {}
    out = _run(view.afilter_queryset(view.get_queryset()))
    assert list(out) == items


def test_apaginate_queryset_returns_none_when_paginator_is_none():
    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        pagination_class = None

        def get_queryset(self):
            return _StubQuerySet([])

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {}
    assert _run(view.apaginate_queryset(view.get_queryset())) is None


def test_aget_object_raises_404_for_value_error():
    msg = "bad type"

    class _ValueErrorQuerySet(_StubQuerySet):
        async def aget(self, **filter_kwargs):
            raise ValueError(msg)

    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        lookup_field = "pk"

        def get_queryset(self):
            return _ValueErrorQuerySet([])

    from django.http import Http404

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {"pk": "abc"}
    with __import__("pytest").raises(Http404):
        _run(view.aget_object())


class _DoesNotExistError(Exception):
    pass


class _ModelStub:
    DoesNotExist = _DoesNotExistError


class _DoesNotExistQuerySet(_StubQuerySet):
    model = _ModelStub

    async def aget(self, **filter_kwargs):
        raise _DoesNotExistError


def test_aget_object_raises_404_for_does_not_exist():
    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        lookup_field = "pk"

        def get_queryset(self):
            return _DoesNotExistQuerySet([])

    from django.http import Http404

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {"pk": 99}
    with __import__("pytest").raises(Http404):
        _run(view.aget_object())


class _SyncPaginator:
    page_size = 2

    def paginate_queryset(self, queryset, request, view=None):
        return list(queryset)[: self.page_size]

    def get_paginated_response(self, data):
        from rest_framework.response import Response

        return Response({"results": data, "count": len(data)})


def test_apaginate_queryset_falls_back_to_sync_paginator():
    items = [_Item(pk=i, value=i) for i in range(3)]

    class View(AsyncGenericAPIView):
        serializer_class = _ItemSerializer
        pagination_class = _SyncPaginator

        def get_queryset(self):
            return _StubQuerySet(items)

    factory = RequestFactory()
    view = View()
    view.request = view.initialize_request(factory.get("/"))
    view.format_kwarg = None
    view.kwargs = {}
    page = _run(view.apaginate_queryset(view.get_queryset()))
    assert len(page) == 2


def test_async_list_create_apiview_get_and_post():
    items = [_Item(pk=1, value=1)]

    class View(AsyncListCreateAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

        async def aperform_create(self, serializer):
            items.append(_Item(pk=2, **serializer.validated_data))

    list_response = _run(View.as_view()(_request("get")))
    assert list_response.status_code == 200
    assert len(list_response.data) == 1
    create_response = _run(
        View.as_view()(_request("post", data={"value": 9}))
    )
    assert create_response.status_code == 201
    assert len(items) == 2


def test_async_retrieve_update_apiview_handles_get_put_patch():
    item = _Item(pk=1, value=1)

    class View(AsyncRetrieveUpdateAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

        async def aperform_update(self, serializer):
            for k, v in serializer.validated_data.items():
                setattr(item, k, v)

    get_response = _run(View.as_view()(_request("get"), pk=1))
    assert get_response.status_code == 200
    put_response = _run(
        View.as_view()(_request("put", data={"value": 5}), pk=1)
    )
    assert put_response.status_code == 200
    assert item.value == 5
    patch_response = _run(
        View.as_view()(_request("patch", data={"value": 9}), pk=1)
    )
    assert patch_response.status_code == 200
    assert item.value == 9


def test_async_retrieve_destroy_apiview_handles_get_delete():
    item = _Item(pk=1, value=1)
    items = [item]

    class View(AsyncRetrieveDestroyAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

        async def aperform_destroy(self, instance):
            items.remove(instance)

    get_response = _run(View.as_view()(_request("get"), pk=1))
    assert get_response.status_code == 200
    delete_response = _run(View.as_view()(_request("delete"), pk=1))
    assert delete_response.status_code == 204
    assert items == []


class _AsyncSaveSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()

    async def asave(self, **kwargs):
        self._instance = type(
            "I", (), {**self.validated_data, **kwargs}
        )()
        return self._instance

    def save(self, **kwargs):
        self._instance = type(
            "I", (), {**self.validated_data, **kwargs}
        )()
        return self._instance


def test_async_create_uses_default_aperform_create_with_async_save():
    class View(AsyncCreateAPIView):
        serializer_class = _AsyncSaveSerializer

    response = _run(
        View.as_view()(_request("post", data={"value": 7}))
    )
    assert response.status_code == 201


class _SyncOnlySaveSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()

    def save(self, **kwargs):
        self._instance = type(
            "I", (), {**self.validated_data, **kwargs}
        )()
        return self._instance


def test_async_create_falls_back_to_sync_save_when_no_asave():
    class View(AsyncCreateAPIView):
        serializer_class = _SyncOnlySaveSerializer

    response = _run(
        View.as_view()(_request("post", data={"value": 8}))
    )
    assert response.status_code == 201


class _SyncIsValidSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


def test_async_list_falls_back_to_sync_filter_queryset():
    items = [_Item(pk=1, value=1)]

    class View(AsyncListAPIView):
        serializer_class = _SyncIsValidSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

        afilter_queryset = None

    response = _run(View.as_view()(_request("get")))
    assert response.status_code == 200
    assert len(response.data) == 1


def test_async_list_returns_paginated_response_when_page_is_not_none():
    items = [_Item(pk=i, value=i) for i in range(3)]

    class View(AsyncListAPIView):
        serializer_class = _SyncIsValidSerializer
        pagination_class = _SyncPaginator

        def get_queryset(self):
            return _StubQuerySet(items)

    response = _run(View.as_view()(_request("get")))
    assert response.status_code == 200
    assert "results" in response.data
    assert response.data["count"] == 2


def test_async_update_default_aperform_update_invokes_save():
    saved = {}

    class _Ser(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField(required=False)
        value = drf_serializers.IntegerField()

        async def asave(self, **kwargs):
            saved["called"] = True
            return self.instance

    item = _Item(pk=1, value=1)

    class View(AsyncUpdateAPIView):
        serializer_class = _Ser

        def get_queryset(self):
            return _StubQuerySet([item])

    response = _run(
        View.as_view()(_request("put", data={"value": 4}), pk=1)
    )
    assert response.status_code == 200
    assert saved["called"] is True


class _PrefetchableQuerySet(_StubQuerySet):
    pass


class _PrefetchedItem:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value
        self._prefetched_objects_cache = {"some": "thing"}


def test_async_update_resets_prefetched_objects_cache():
    item = _PrefetchedItem(pk=1, value=1)

    class View(AsyncUpdateAPIView):
        serializer_class = _SyncIsValidSerializer

        def get_queryset(self):
            return _PrefetchableQuerySet([item])

        async def aperform_update(self, serializer):
            for k, v in serializer.validated_data.items():
                setattr(item, k, v)

    response = _run(
        View.as_view()(_request("put", data={"value": 4}), pk=1)
    )
    assert response.status_code == 200
    assert item._prefetched_objects_cache == {}


class _AdeleteItem:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value
        self.deleted = False

    async def adelete(self):
        self.deleted = True


def test_async_destroy_default_uses_adelete_when_available():
    item = _AdeleteItem(pk=1, value=1)

    class View(AsyncDestroyAPIView):
        serializer_class = _SyncIsValidSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

    response = _run(View.as_view()(_request("delete"), pk=1))
    assert response.status_code == 204
    assert item.deleted is True


class _SyncDeleteItem:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value
        self.deleted = False

    def delete(self):
        self.deleted = True


def test_async_destroy_default_falls_back_to_sync_delete():
    item = _SyncDeleteItem(pk=1, value=1)

    class View(AsyncDestroyAPIView):
        serializer_class = _SyncIsValidSerializer

        def get_queryset(self):
            return _StubQuerySet([item])

    response = _run(View.as_view()(_request("delete"), pk=1))
    assert response.status_code == 204
    assert item.deleted is True


class _AsyncIsValidSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()

    async def ais_valid(self, raise_exception=False):
        return self.is_valid(raise_exception=raise_exception)


def test_async_create_uses_async_ais_valid_when_present():
    item_holder = []

    class View(AsyncCreateAPIView):
        serializer_class = _AsyncIsValidSerializer

        async def aperform_create(self, serializer):
            item_holder.append(serializer.validated_data)

    response = _run(
        View.as_view()(_request("post", data={"value": 22}))
    )
    assert response.status_code == 201
    assert item_holder[0]["value"] == 22


def test_async_retrieve_update_destroy_apiview_handles_all_verbs():
    item = _Item(pk=1, value=1)
    items = [item]

    class View(AsyncRetrieveUpdateDestroyAPIView):
        serializer_class = _ItemSerializer

        def get_queryset(self):
            return _StubQuerySet(items)

        async def aperform_update(self, serializer):
            for k, v in serializer.validated_data.items():
                setattr(item, k, v)

        async def aperform_destroy(self, instance):
            items.remove(instance)

    get_response = _run(View.as_view()(_request("get"), pk=1))
    assert get_response.status_code == 200
    put_response = _run(
        View.as_view()(_request("put", data={"value": 7}), pk=1)
    )
    assert put_response.status_code == 200
    assert item.value == 7
    patch_response = _run(
        View.as_view()(_request("patch", data={"value": 11}), pk=1)
    )
    assert patch_response.status_code == 200
    assert item.value == 11
    delete_response = _run(View.as_view()(_request("delete"), pk=1))
    assert delete_response.status_code == 204
