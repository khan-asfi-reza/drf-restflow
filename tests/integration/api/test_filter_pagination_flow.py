import asyncio
from typing import Literal

import pytest
from django.test import override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny

from restflow.filters import FilterSet
from restflow.filters.backends import RestflowFilterBackend
from restflow.filters.fields import IntegerField, OrderField
from restflow.pagination import (
    FastPageNumberPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)
from restflow.test import AsyncAPIClient
from restflow.views import AsyncListAPIView
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class SampleSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field", "choice_field"]


class SampleFilterSet(FilterSet):
    integer_field = IntegerField(
        db_field="integer_field", lookups=["gte", "lte"]
    )
    string_field: str
    choice_field: Literal["a", "b", "c"]
    order = OrderField(
        fields=[
            ("integer_field", "integer_field"),
            ("string_field", "string_field"),
        ]
    )


class PageNumberView(AsyncListAPIView):
    serializer_class = SampleSerializer
    pagination_class = PageNumberPagination
    permission_classes = [AllowAny]
    filter_backends = [RestflowFilterBackend]
    filterset_class = SampleFilterSet

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class LimitOffsetView(AsyncListAPIView):
    serializer_class = SampleSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [AllowAny]
    filter_backends = [RestflowFilterBackend]
    filterset_class = SampleFilterSet

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class FastPageView(AsyncListAPIView):
    serializer_class = SampleSerializer
    pagination_class = FastPageNumberPagination
    permission_classes = [AllowAny]
    filter_backends = [RestflowFilterBackend]
    filterset_class = SampleFilterSet

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


urlpatterns = [
    path("page/", PageNumberView.as_view()),
    path("offset/", LimitOffsetView.as_view()),
    path("fast/", FastPageView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.fixture
def seeded(db):
    PageNumberView.pagination_class.page_size = 3
    LimitOffsetView.pagination_class.default_limit = 3
    FastPageView.pagination_class.page_size = 3
    rows = []
    for i in range(10):
        rows.append(
            SampleModel.objects.create(
                integer_field=i,
                string_field=f"name-{i}",
                choice_field="a" if i % 2 == 0 else "b",
            )
        )
    return rows


@pytest.mark.django_db(transaction=True)
class TestPageNumberView:
    def test_first_page_returns_count_and_results(
        self, configured_urls, seeded
    ):
        response = run_coro(AsyncAPIClient().get("/page/"))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 10
        assert len(body["results"]) == 3

    def test_filter_by_choice_then_paginate(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/page/?choice_field=a"))
        body = response.json()
        assert body["count"] == 5
        for row in body["results"]:
            assert row["choice_field"] == "a"

    def test_combined_filter_and_lookup_variant(
        self, configured_urls, seeded
    ):
        response = run_coro(
            AsyncAPIClient().get("/page/?integer_field__gte=5&integer_field__lte=8")
        )
        body = response.json()
        assert body["count"] == 4

    def test_order_by_descending(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/page/?order=-integer_field")
        )
        body = response.json()
        assert body["results"][0]["integer_field"] == 9

    def test_filter_then_order(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get(
                "/page/?choice_field=b&order=-integer_field"
            )
        )
        body = response.json()
        assert body["results"][0]["integer_field"] == 9
        for row in body["results"]:
            assert row["choice_field"] == "b"

    def test_no_match_returns_zero_count(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/page/?integer_field__gte=999")
        )
        body = response.json()
        assert body["count"] == 0
        assert body["results"] == []

    def test_invalid_choice_returns_400(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/page/?choice_field=z"))
        assert response.status_code == 400

    def test_negation_filter(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/page/?choice_field!=a")
        )
        body = response.json()
        assert body["count"] == 5
        for row in body["results"]:
            assert row["choice_field"] != "a"


@pytest.mark.django_db(transaction=True)
class TestLimitOffsetView:
    def test_default_limit(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/offset/"))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 10
        assert len(body["results"]) == 3

    def test_explicit_limit_offset(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/offset/?limit=4&offset=2")
        )
        body = response.json()
        assert len(body["results"]) == 4
        assert body["results"][0]["integer_field"] == 2

    def test_offset_past_end_returns_empty(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/offset/?limit=5&offset=999")
        )
        body = response.json()
        assert body["results"] == []

    def test_filter_then_paginate(self, configured_urls, seeded):
        response = run_coro(
            AsyncAPIClient().get("/offset/?choice_field=b&limit=10")
        )
        body = response.json()
        assert body["count"] == 5
        for row in body["results"]:
            assert row["choice_field"] == "b"


@pytest.mark.django_db(transaction=True)
class TestFastPageView:
    def test_first_page_has_next(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/fast/"))
        body = response.json()
        assert response.status_code == 200
        assert body["next"] is not None
        assert body["previous"] is None
        assert len(body["results"]) == 3

    def test_last_page_no_next(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/fast/?page=4"))
        body = response.json()
        assert body["next"] is None
        assert len(body["results"]) == 1

    def test_skips_count_query_in_payload(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/fast/?page=2"))
        body = response.json()
        assert "count" not in body

    def test_overshooting_page_returns_404(self, configured_urls, seeded):
        response = run_coro(AsyncAPIClient().get("/fast/?page=99"))
        assert response.status_code == 404


