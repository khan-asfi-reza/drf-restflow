import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination

from restflow.views import APIView


class _ItemSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    value = drf_serializers.IntegerField()


class _AltSerializer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False)
    name = drf_serializers.CharField()


class _Item:
    def __init__(self, pk, value):
        self.pk = pk
        self.value = value


def _bind(view_cls, method="get", path="/", data=None):
    view = view_cls()
    factory = RequestFactory()
    if data is not None:
        import json

        raw = getattr(factory, method)(
            path, data=json.dumps(data), content_type="application/json"
        )
    else:
        raw = getattr(factory, method)(path)
    view.request = view.initialize_request(raw)
    view.format_kwarg = None
    return view


def test_get_serializer_uses_class_attribute():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    ser = view.get_serializer(_Item(pk=1, value=42))
    assert isinstance(ser, _ItemSerializer)
    assert ser.context["request"] is view.request
    assert ser.context["view"] is view


def test_get_serializer_kwarg_overrides_class_default():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    ser = view.get_serializer(serializer_class=_AltSerializer)
    assert isinstance(ser, _AltSerializer)


def test_get_serializer_raises_when_unset():
    view = _bind(APIView)
    with pytest.raises(ImproperlyConfigured, match="serializer_class"):
        view.get_serializer()


def test_validated_serializer_validates_and_returns():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V, method="post", data={"value": 7})
    ser = view.validated_serializer()
    assert ser.validated_data == {"value": 7}


def test_validated_serializer_raises_on_invalid_data():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V, method="post", data={"value": "not-int"})
    with pytest.raises(ValidationError):
        view.validated_serializer()


def test_serialized_response_returns_200_with_data():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    response = view.serialized_response(_Item(pk=1, value=42))
    assert response.status_code == 200
    assert response.data["value"] == 42


def test_serialized_response_supports_many_and_status():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    items = [_Item(pk=1, value=10), _Item(pk=2, value=20)]
    response = view.serialized_response(items, many=True, status=201)
    assert response.status_code == 201
    assert len(response.data) == 2


def test_serialized_response_serializer_class_kwarg():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    response = view.serialized_response(
        type("N", (), {"name": "x", "pk": 1})(),
        serializer_class=_AltSerializer,
    )
    assert response.data["name"] == "x"


def test_paginated_response_without_pagination_class():
    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V)
    items = [_Item(pk=1, value=1), _Item(pk=2, value=2)]
    response = view.paginated_response(items)
    assert response.status_code == 200
    assert len(response.data) == 2


def test_paginated_response_with_pagination_class():
    class _Page(PageNumberPagination):
        page_size = 2

    class V(APIView):
        serializer_class = _ItemSerializer
        pagination_class = _Page

    view = _bind(V, path="/?page=1")
    items = [_Item(pk=i, value=i) for i in range(5)]
    response = view.paginated_response(items)
    assert response.status_code == 200
    assert response.data["count"] == 5
    assert len(response.data["results"]) == 2


def test_paginated_response_pagination_kwarg_override():
    class _Page(PageNumberPagination):
        page_size = 3

    class V(APIView):
        serializer_class = _ItemSerializer

    view = _bind(V, path="/?page=1")
    items = [_Item(pk=i, value=i) for i in range(5)]
    response = view.paginated_response(items, pagination_class=_Page)
    assert response.data["count"] == 5
    assert len(response.data["results"]) == 3


class _StubFetcher:
    def __init__(self, key="extra", value="enriched"):
        self.key = key
        self.value = value

    def fetch(self, items):
        for item in items:
            if isinstance(item, dict):
                item[self.key] = self.value
            else:
                setattr(item, self.key, self.value)
        return items


def test_serialized_response_applies_post_fetches_for_many():
    class _S(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        extra = drf_serializers.CharField()

    class V(APIView):
        serializer_class = _S

    view = _bind(V)
    items = [_Item(pk=1, value=1), _Item(pk=2, value=2)]
    response = view.serialized_response(
        items, many=True, post_fetches=[_StubFetcher()]
    )
    assert all(d["extra"] == "enriched" for d in response.data)


def test_serialized_response_applies_post_fetches_for_single():
    class _S(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        extra = drf_serializers.CharField()

    class V(APIView):
        serializer_class = _S

    view = _bind(V)
    response = view.serialized_response(
        _Item(pk=1, value=1), post_fetches=[_StubFetcher()]
    )
    assert response.data["extra"] == "enriched"


def test_paginated_response_applies_post_fetches():
    class _Page(PageNumberPagination):
        page_size = 2

    class _S(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        extra = drf_serializers.CharField()

    class V(APIView):
        serializer_class = _S
        pagination_class = _Page

    view = _bind(V, path="/?page=1")
    items = [_Item(pk=i, value=i) for i in range(5)]
    response = view.paginated_response(items, post_fetches=[_StubFetcher()])
    assert all(d["extra"] == "enriched" for d in response.data["results"])


class _NonePaginator:
    def paginate_queryset(self, queryset, request, view=None):
        return None


def test_paginated_response_returns_unpaginated_when_paginator_returns_none():
    class V(APIView):
        serializer_class = _ItemSerializer
        pagination_class = _NonePaginator

    view = _bind(V)
    items = [_Item(pk=1, value=1), _Item(pk=2, value=2)]
    response = view.paginated_response(items)
    assert response.status_code == 200
    assert len(response.data) == 2
