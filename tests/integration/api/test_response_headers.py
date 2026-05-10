import asyncio
import json

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny

from restflow.pagination import PageNumberPagination
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class StandardPagination(PageNumberPagination):
    page_size = 50


class SampleSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field"]


class SyncSerializedHeaderView(APIView):
    serializer_class = SampleSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        instance = SampleModel.objects.create(integer_field=1)
        return self.serialized_response(
            instance,
            headers={"X-Custom": "yes", "X-Trace": "abc"},
        )


class SyncPaginatedHeaderView(APIView):
    serializer_class = SampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    def get(self, request):
        return self.paginated_response(
            SampleModel.objects.all().order_by("id"),
            headers={"X-Page-Hint": "first"},
        )


class SyncPaginatedNoPagClassHeaderView(APIView):
    serializer_class = SampleSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        return self.paginated_response(
            SampleModel.objects.all().order_by("id"),
            headers={"X-No-Pagination": "ok"},
        )


class AsyncSerializedHeaderView(AsyncAPIView):
    serializer_class = SampleSerializer
    permission_classes = [AllowAny]

    async def get(self, request):
        instance = await SampleModel.objects.acreate(integer_field=2)
        return await self.aserialized_response(
            instance,
            headers={"X-Async": "header", "X-Trace": "xyz"},
        )


class AsyncPaginatedHeaderView(AsyncAPIView):
    serializer_class = SampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    async def get(self, request):
        return await self.apaginated_response(
            SampleModel.objects.all().order_by("id"),
            headers={"X-Async-Page": "yes"},
        )


urlpatterns = [
    path("sync-ser/", SyncSerializedHeaderView.as_view()),
    path("sync-pag/", SyncPaginatedHeaderView.as_view()),
    path("sync-pag-empty/", SyncPaginatedNoPagClassHeaderView.as_view()),
    path("async-ser/", AsyncSerializedHeaderView.as_view()),
    path("async-pag/", AsyncPaginatedHeaderView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db(transaction=True)
class TestSyncSerializedResponseHeaders:
    def test_serialized_response_carries_headers(self, configured_urls):
        response = Client().get("/sync-ser/")
        assert response.status_code == 200
        assert response["X-Custom"] == "yes"
        assert response["X-Trace"] == "abc"

    def test_paginated_response_carries_headers(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = Client().get("/sync-pag/")
        assert response.status_code == 200
        assert response["X-Page-Hint"] == "first"

    def test_paginated_response_without_paginator_carries_headers(
        self, configured_urls
    ):
        SampleModel.objects.create(integer_field=1)
        response = Client().get("/sync-pag-empty/")
        assert response.status_code == 200
        assert response["X-No-Pagination"] == "ok"


@pytest.mark.django_db(transaction=True)
class TestAsyncSerializedResponseHeaders:
    def test_aserialized_response_carries_headers(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async-ser/"))
        assert response.status_code == 200
        assert response["X-Async"] == "header"
        assert response["X-Trace"] == "xyz"

    def test_apaginated_response_carries_headers(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = run_coro(AsyncAPIClient().get("/async-pag/"))
        assert response.status_code == 200
        assert response["X-Async-Page"] == "yes"


class CreateOnlyView(APIView):
    serializer_class = SampleSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        ser = self.validated_serializer()
        instance = SampleModel.objects.create(**ser.validated_data)
        return self.serialized_response(
            instance,
            status=201,
            headers={"Location": f"/items/{instance.pk}/"},
        )


urlpatterns.append(path("create-with-location/", CreateOnlyView.as_view()))


@pytest.mark.django_db
class TestLocationHeaderFlowFromHelper:
    def test_explicit_location_header_passed_through(self, configured_urls):
        response = Client().post(
            "/create-with-location/",
            data=json.dumps({"integer_field": 9}),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response["Location"].startswith("/items/")
