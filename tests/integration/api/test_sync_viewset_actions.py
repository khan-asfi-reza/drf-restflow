import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache as default_cache
from django.test import Client, override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import AnonRateThrottle

from restflow.pagination import PageNumberPagination
from restflow.views import (
    ActionConfig,
    GenericViewSet,
    ModelViewSet,
    ReadOnlyModelViewSet,
    ViewSet,
)
from tests.models import SampleModel


class StandardPagination(PageNumberPagination):
    page_size = 50


class ListSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field"]


class DetailSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field", "choice_field"]


class WriteSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["integer_field", "string_field", "choice_field"]


class StrictAnonThrottle(AnonRateThrottle):
    rate = "1/min"


class SyncSampleViewSet(ModelViewSet):
    serializer_class = DetailSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")
    action_configs = {
        "list": ActionConfig(serializer_class=ListSerializer),
        "create": ActionConfig(
            serializer_class=WriteSerializer,
            permission_classes=[IsAuthenticated],
        ),
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
        "retrieve": ActionConfig(throttle_classes=[StrictAnonThrottle]),
    }


class SyncReadOnlyViewSet(ReadOnlyModelViewSet):
    serializer_class = DetailSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")


class SyncBareViewSet(ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        from rest_framework.response import Response
        return Response({"action": "list"})

    def custom(self, request):
        from rest_framework.response import Response
        return Response({"action": "custom"})


class SyncGenericViewSet(GenericViewSet):
    serializer_class = DetailSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all().order_by("id")
    action_configs = {
        "list_only": ActionConfig(serializer_class=ListSerializer),
    }

    def list_only(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        ser = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(ser.data)
        from rest_framework.response import Response
        return Response(ser.data)


router = DefaultRouter()
router.register("samples", SyncSampleViewSet, basename="sync-sample")
router.register(
    "samples-readonly", SyncReadOnlyViewSet, basename="sync-readonly"
)


urlpatterns = list(router.urls) + [
    path("bare/list/", SyncBareViewSet.as_view({"get": "list"})),
    path("bare/custom/", SyncBareViewSet.as_view({"get": "custom"})),
    path(
        "generic/", SyncGenericViewSet.as_view({"get": "list_only"})
    ),
]


CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sync-viewset-actions",
    }
}


@pytest.fixture
def configured_urls():
    with override_settings(
        ROOT_URLCONF=__name__, CACHES=CACHES_OVERRIDE
    ):
        default_cache.clear()
        yield
        default_cache.clear()


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="sync-admin", password="x", is_active=True, is_staff=True
    )


@pytest.fixture
def regular_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="sync-reg", password="x", is_active=True
    )


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestSyncActionScopedSerializers:
    def test_list_uses_minimal_serializer(self, configured_urls):
        SampleModel.objects.create(
            integer_field=1, string_field="hidden", choice_field="a"
        )
        response = Client().get("/samples/")
        body = response.json()
        assert response.status_code == 200
        first = body["results"][0]
        assert "string_field" not in first
        assert "integer_field" in first

    def test_retrieve_uses_full_serializer(self, configured_urls):
        instance = SampleModel.objects.create(
            integer_field=2, string_field="visible", choice_field="b"
        )
        response = Client().get(f"/samples/{instance.pk}/")
        body = response.json()
        assert response.status_code == 200
        assert body["string_field"] == "visible"


@pytest.mark.django_db
class TestSyncActionScopedPermissions:
    def test_create_requires_authentication(self, configured_urls):
        response = Client().post(
            "/samples/",
            data=json.dumps(
                {
                    "integer_field": 1,
                    "string_field": "x",
                    "choice_field": "a",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code in (401, 403)

    def test_create_succeeds_when_authenticated(
        self, configured_urls, regular_user
    ):
        client = login(regular_user)
        response = client.post(
            "/samples/",
            data=json.dumps(
                {
                    "integer_field": 9,
                    "string_field": "y",
                    "choice_field": "a",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=9).exists()

    def test_destroy_requires_admin(
        self, configured_urls, regular_user
    ):
        instance = SampleModel.objects.create(integer_field=4)
        client = login(regular_user)
        response = client.delete(f"/samples/{instance.pk}/")
        assert response.status_code == 403

    def test_destroy_succeeds_when_admin(
        self, configured_urls, admin_user
    ):
        instance = SampleModel.objects.create(integer_field=4)
        client = login(admin_user)
        response = client.delete(f"/samples/{instance.pk}/")
        assert response.status_code == 204


@pytest.mark.django_db
class TestSyncActionScopedThrottle:
    def test_retrieve_throttled_after_limit(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = Client()
        first = client.get(f"/samples/{instance.pk}/")
        assert first.status_code == 200
        second = client.get(f"/samples/{instance.pk}/")
        assert second.status_code == 429

    def test_list_not_throttled(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        client = Client()
        for _ in range(5):
            assert client.get("/samples/").status_code == 200


@pytest.mark.django_db
class TestSyncRouterRegistration:
    def test_router_routes_list(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)
        response = Client().get("/samples/")
        assert response.status_code == 200
        assert response.json()["count"] == 2

    def test_router_routes_detail(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=99)
        response = Client().get(f"/samples/{instance.pk}/")
        assert response.status_code == 200
        assert response.json()["integer_field"] == 99

    def test_method_not_allowed_on_detail(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        response = Client().post(
            f"/samples/{instance.pk}/",
            data=json.dumps({"integer_field": 2}),
            content_type="application/json",
        )
        assert response.status_code == 405


@pytest.mark.django_db
class TestSyncUpdateActions:
    def test_full_update_via_put(self, configured_urls, regular_user):
        instance = SampleModel.objects.create(integer_field=1)
        client = login(regular_user)
        response = client.put(
            f"/samples/{instance.pk}/",
            data=json.dumps(
                {
                    "integer_field": 5,
                    "string_field": "b",
                    "choice_field": "b",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 5

    def test_partial_update_via_patch(
        self, configured_urls, regular_user
    ):
        instance = SampleModel.objects.create(
            integer_field=1, string_field="keep"
        )
        client = login(regular_user)
        response = client.patch(
            f"/samples/{instance.pk}/",
            data=json.dumps({"integer_field": 7}),
            content_type="application/json",
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 7
        assert instance.string_field == "keep"


@pytest.mark.django_db
class TestSyncReadOnlyViewSet:
    def test_list_works(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = Client().get("/samples-readonly/")
        assert response.status_code == 200

    def test_create_method_not_allowed(self, configured_urls):
        response = Client().post(
            "/samples-readonly/",
            data=json.dumps({"integer_field": 1}),
            content_type="application/json",
        )
        assert response.status_code == 405


@pytest.mark.django_db
class TestSyncBareViewSet:
    def test_list_action(self, configured_urls):
        response = Client().get("/bare/list/")
        assert response.status_code == 200
        assert response.json() == {"action": "list"}

    def test_custom_action(self, configured_urls):
        response = Client().get("/bare/custom/")
        assert response.status_code == 200
        assert response.json() == {"action": "custom"}


@pytest.mark.django_db
class TestSyncGenericViewSet:
    def test_action_config_serializer_used(self, configured_urls):
        SampleModel.objects.create(
            integer_field=1, string_field="hidden", choice_field="a"
        )
        response = Client().get("/generic/")
        body = response.json()
        assert response.status_code == 200
        first = body["results"][0]
        assert "string_field" not in first
