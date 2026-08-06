import asyncio

import pytest
from django.test import override_settings
from django.urls import path

from restflow.pagination import PageNumberPagination
from restflow.serializers import ModelSerializer
from restflow.test import AsyncAPIClient
from restflow.views import AsyncAPIView, AsyncListAPIView
from tests.models import RelatedModel, SampleModel


class _SampleSerializer(ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "string_field", "integer_field"]


class _RelatedItemSerializer(ModelSerializer):
    sample_model = _SampleSerializer(read_only=True)

    class Meta:
        model = RelatedModel
        fields = ["id", "name", "sample_model"]


class _SmallPagination(PageNumberPagination):
    page_size = 2


class _UnpaginatedListView(AsyncListAPIView):
    queryset = SampleModel.objects.all().order_by("id")
    serializer_class = _SampleSerializer
    pagination_class = None


class _PaginatedListView(AsyncListAPIView):
    queryset = SampleModel.objects.all().order_by("id")
    serializer_class = _SampleSerializer
    pagination_class = _SmallPagination


class _NestedRelationView(AsyncAPIView):
    serializer_class = _RelatedItemSerializer

    async def get(self, request):
        return await self.aserialized_response(
            RelatedModel.objects.all().order_by("id"), many=True
        )


urlpatterns = [
    path("unpaginated/", _UnpaginatedListView.as_view()),
    path("paginated/", _PaginatedListView.as_view()),
    path("nested/", _NestedRelationView.as_view()),
]


@pytest.fixture
def urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db(transaction=True)
def test_unpaginated_async_list_serializes_a_lazy_queryset(urls):
    for index in range(3):
        SampleModel.objects.create(string_field=f"row-{index}")

    async def run():
        response = await AsyncAPIClient().get("/unpaginated/")
        assert response.status_code == 200
        assert len(response.data) == 3

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_paginated_async_list_serializes_a_page(urls):
    for index in range(3):
        SampleModel.objects.create(string_field=f"row-{index}")

    async def run():
        response = await AsyncAPIClient().get("/paginated/")
        assert response.status_code == 200
        assert response.data["count"] == 3
        assert len(response.data["results"]) == 2

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_aserialized_response_follows_nested_relations(urls):
    parent = SampleModel.objects.create(string_field="parent")
    RelatedModel.objects.create(sample_model=parent, name="child")

    async def run():
        response = await AsyncAPIClient().get("/nested/")
        assert response.status_code == 200
        assert response.data[0]["sample_model"]["string_field"] == "parent"

    asyncio.run(run())
