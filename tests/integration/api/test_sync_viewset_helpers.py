import json

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from restflow.pagination import PageNumberPagination
from restflow.views import (
    ActionConfig,
    ModelViewSet,
)
from tests.models import SampleModel


class StandardPagination(PageNumberPagination):
    page_size = 50


class WriteSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["integer_field", "string_field"]


class ReadSerializer(drf_serializers.ModelSerializer):
    label = drf_serializers.SerializerMethodField()

    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field", "label"]

    def get_label(self, obj):
        return f"sample-{obj.pk}"


class EnrichingFetcher:
    def fetch(self, items):
        for item in items:
            item.string_field = (item.string_field or "") + "!post"
        return items


class SplitSerializerViewSet(ModelViewSet):
    request_serializer_class = WriteSerializer
    response_serializer_class = ReadSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")


class ActionScopedSplitViewSet(ModelViewSet):
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")
    action_configs = {
        "list": ActionConfig(
            request_serializer_class=WriteSerializer,
            response_serializer_class=ReadSerializer,
        ),
        "create": ActionConfig(
            request_serializer_class=WriteSerializer,
            response_serializer_class=ReadSerializer,
        ),
        "retrieve": ActionConfig(
            response_serializer_class=ReadSerializer,
        ),
        "update": ActionConfig(
            request_serializer_class=WriteSerializer,
            response_serializer_class=ReadSerializer,
        ),
    }


class PostFetchViewSet(ModelViewSet):
    serializer_class = ReadSerializer
    request_serializer_class = WriteSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.paginated_response(
            queryset, post_fetches=[EnrichingFetcher()]
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return self.serialized_response(
            instance, post_fetches=[EnrichingFetcher()]
        )


router = DefaultRouter()
router.register("split", SplitSerializerViewSet, basename="split")
router.register("scoped", ActionScopedSplitViewSet, basename="scoped")
router.register("postfetch", PostFetchViewSet, basename="postfetch")


urlpatterns = list(router.urls)


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db
class TestRequestResponseSplitOnSyncViewSet:
    def test_create_validates_with_write_serializer_then_returns_read(
        self, configured_urls
    ):
        response = Client().post(
            "/split/",
            data=json.dumps(
                {"integer_field": 7, "string_field": "input"}
            ),
            content_type="application/json",
        )
        body = response.json()
        assert response.status_code == 201
        assert body["integer_field"] == 7
        assert body["string_field"] == "input"
        assert body["label"] == f"sample-{body['id']}"

    def test_list_uses_response_serializer_with_label(self, configured_urls):
        SampleModel.objects.create(integer_field=1, string_field="x")
        response = Client().get("/split/")
        body = response.json()
        assert response.status_code == 200
        first = body["results"][0]
        assert "label" in first
        assert first["label"].startswith("sample-")

    def test_retrieve_uses_response_serializer(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=2)
        response = Client().get(f"/split/{instance.pk}/")
        body = response.json()
        assert response.status_code == 200
        assert body["label"] == f"sample-{instance.pk}"

    def test_update_validates_via_write_then_returns_read(
        self, configured_urls
    ):
        instance = SampleModel.objects.create(integer_field=1)
        response = Client().put(
            f"/split/{instance.pk}/",
            data=json.dumps(
                {"integer_field": 5, "string_field": "after"}
            ),
            content_type="application/json",
        )
        body = response.json()
        assert response.status_code == 200
        assert body["integer_field"] == 5
        assert body["label"] == f"sample-{instance.pk}"

    def test_partial_update_via_patch(self, configured_urls):
        instance = SampleModel.objects.create(
            integer_field=1, string_field="keep"
        )
        response = Client().patch(
            f"/split/{instance.pk}/",
            data=json.dumps({"integer_field": 9}),
            content_type="application/json",
        )
        body = response.json()
        assert response.status_code == 200
        assert body["integer_field"] == 9
        assert body["string_field"] == "keep"


@pytest.mark.django_db
class TestActionScopedSplitOnSyncViewSet:
    def test_list_action_uses_scoped_response_serializer(
        self, configured_urls
    ):
        SampleModel.objects.create(integer_field=1, string_field="x")
        response = Client().get("/scoped/")
        first = response.json()["results"][0]
        assert "label" in first

    def test_create_action_uses_scoped_serializers(self, configured_urls):
        response = Client().post(
            "/scoped/",
            data=json.dumps(
                {"integer_field": 3, "string_field": "y"}
            ),
            content_type="application/json",
        )
        body = response.json()
        assert response.status_code == 201
        assert body["label"] == f"sample-{body['id']}"

    def test_retrieve_action_uses_scoped_response(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=4)
        response = Client().get(f"/scoped/{instance.pk}/")
        assert response.json()["label"] == f"sample-{instance.pk}"


@pytest.mark.django_db
class TestPostFetchOnSyncViewSet:
    def test_list_runs_post_fetch_on_each_item(self, configured_urls):
        SampleModel.objects.create(integer_field=1, string_field="row")
        response = Client().get("/postfetch/")
        body = response.json()
        first = body["results"][0]
        assert first["string_field"].endswith("!post")

    def test_retrieve_runs_post_fetch_on_single_instance(
        self, configured_urls
    ):
        instance = SampleModel.objects.create(
            integer_field=1, string_field="solo"
        )
        response = Client().get(f"/postfetch/{instance.pk}/")
        body = response.json()
        assert body["string_field"].endswith("!post")


@pytest.mark.django_db
class TestPaginationViaHelpers:
    def test_pagination_class_resolved_through_helper_surface(
        self, configured_urls
    ):
        for i in range(3):
            SampleModel.objects.create(integer_field=i)
        response = Client().get("/split/")
        body = response.json()
        assert "count" in body
        assert "results" in body
        assert body["count"] == 3
