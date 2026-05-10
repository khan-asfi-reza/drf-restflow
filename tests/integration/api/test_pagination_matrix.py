import asyncio
import itertools

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny

from restflow.pagination import (
    CursorPagination,
    FastPageNumberPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)
from restflow.serializers import (
    HyperlinkedModelSerializer,
    ModelSerializer,
    Serializer,
)
from restflow.test import AsyncAPIClient
from restflow.views import AsyncListAPIView
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class DRFFlatSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class RestflowFlatSerializer(Serializer):
    integer_field: int
    string_field: str | None


class RestflowModelFlatSerializer(ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class RestflowHyperlinkedSerializer(HyperlinkedModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["url", "integer_field", "string_field"]
        extra_kwargs = {"url": {"view_name": "sample-detail"}}


class CursorByPK(CursorPagination):
    page_size = 3
    ordering = "id"


class PageNumberSmall(PageNumberPagination):
    page_size = 3


class LimitOffsetSmall(LimitOffsetPagination):
    default_limit = 3


class FastPageSmall(FastPageNumberPagination):
    page_size = 3


SERIALIZER_CHOICES = {
    "drf-model": DRFFlatSerializer,
    "restflow-model": RestflowModelFlatSerializer,
    "restflow-hyperlinked": RestflowHyperlinkedSerializer,
}


PAGINATION_CHOICES = {
    "page-number": PageNumberSmall,
    "limit-offset": LimitOffsetSmall,
    "fast-page": FastPageSmall,
    "cursor": CursorByPK,
}


VIEW_REGISTRY = {}


def make_listview(serializer_class, pagination_class, slug):
    class _Listing(AsyncListAPIView):
        permission_classes = [AllowAny]

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    _Listing.serializer_class = serializer_class
    _Listing.pagination_class = pagination_class
    _Listing.__name__ = f"Listing_{slug}"
    return _Listing


urlpatterns = [
    path(
        "samples/<int:pk>/",
        AsyncListAPIView.as_view(),
        name="sample-detail",
    ),
]


for ser_key, ser_cls in SERIALIZER_CHOICES.items():
    for pg_key, pg_cls in PAGINATION_CHOICES.items():
        slug = f"{ser_key}__{pg_key}"
        view_cls = make_listview(ser_cls, pg_cls, slug)
        VIEW_REGISTRY[slug] = view_cls
        urlpatterns.append(
            path(f"page/{slug}/", view_cls.as_view(), name=slug)
        )


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.fixture
def seeded(db):
    rows = []
    for i in range(8):
        rows.append(
            SampleModel.objects.create(
                integer_field=i, string_field=f"name-{i}"
            )
        )
    return rows


PAGINATION_KEYS = list(PAGINATION_CHOICES.keys())
SERIALIZER_KEYS = list(SERIALIZER_CHOICES.keys())
COMBOS = list(itertools.product(SERIALIZER_KEYS, PAGINATION_KEYS))


@pytest.mark.django_db(transaction=True)
class TestPaginationMatrix:
    @pytest.mark.parametrize("ser_key,pg_key", COMBOS)
    def test_first_page_responds_200(
        self, configured_urls, seeded, ser_key, pg_key
    ):
        slug = f"{ser_key}__{pg_key}"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/"))
        assert response.status_code == 200

    @pytest.mark.parametrize("ser_key,pg_key", COMBOS)
    def test_first_page_returns_three_items(
        self, configured_urls, seeded, ser_key, pg_key
    ):
        slug = f"{ser_key}__{pg_key}"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/"))
        body = response.json()
        if pg_key in ("page-number", "limit-offset"):
            assert len(body["results"]) == 3
        elif pg_key == "fast-page":
            assert len(body["results"]) == 3
        elif pg_key == "cursor":
            assert len(body["results"]) == 3

    @pytest.mark.parametrize("ser_key", SERIALIZER_KEYS)
    def test_page_number_second_page(
        self, configured_urls, seeded, ser_key
    ):
        slug = f"{ser_key}__page-number"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/?page=2"))
        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 3

    @pytest.mark.parametrize("ser_key", SERIALIZER_KEYS)
    def test_limit_offset_explicit_window(
        self, configured_urls, seeded, ser_key
    ):
        slug = f"{ser_key}__limit-offset"
        response = run_coro(
            AsyncAPIClient().get(f"/page/{slug}/?limit=4&offset=2")
        )
        body = response.json()
        assert response.status_code == 200
        assert len(body["results"]) == 4

    @pytest.mark.parametrize("ser_key", SERIALIZER_KEYS)
    def test_fast_page_skips_count(self, configured_urls, seeded, ser_key):
        slug = f"{ser_key}__fast-page"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/"))
        body = response.json()
        assert "count" not in body
        assert "next" in body

    @pytest.mark.parametrize("ser_key", SERIALIZER_KEYS)
    def test_cursor_pagination_returns_next_cursor(
        self, configured_urls, seeded, ser_key
    ):
        slug = f"{ser_key}__cursor"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/"))
        body = response.json()
        assert response.status_code == 200
        assert "next" in body

    @pytest.mark.parametrize("ser_key", SERIALIZER_KEYS)
    def test_page_number_overshoot_returns_404(
        self, configured_urls, seeded, ser_key
    ):
        slug = f"{ser_key}__page-number"
        response = run_coro(AsyncAPIClient().get(f"/page/{slug}/?page=999"))
        assert response.status_code == 404
