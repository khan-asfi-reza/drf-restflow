import asyncio

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache as default_cache
from django.test import override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from restflow.pagination import PageNumberPagination
from restflow.permissions import IsAdminUser, IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.throttling import AnonRateThrottle
from restflow.views import ActionConfig, AsyncModelViewSet
from tests.models import SampleModel


class StandardPagination(PageNumberPagination):
    page_size = 50


def run_coro(coro):
    return asyncio.run(coro)


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


class SampleViewSet(AsyncModelViewSet):
    serializer_class = DetailSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    action_configs = {
        "list": ActionConfig(
            serializer_class=ListSerializer,
        ),
        "create": ActionConfig(
            serializer_class=WriteSerializer,
            permission_classes=[IsAuthenticated],
        ),
        "destroy": ActionConfig(
            permission_classes=[IsAdminUser],
        ),
        "retrieve": ActionConfig(
            throttle_classes=[StrictAnonThrottle],
        ),
    }

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


router = DefaultRouter()
router.register("samples", SampleViewSet, basename="sample")

urlpatterns = list(router.urls) + [
    path("samples-base/", SampleViewSet.as_view({"get": "list"})),
]


CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "viewset-actions",
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
        username="admin", password="x", is_active=True, is_staff=True
    )


@pytest.fixture
def regular_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="reg", password="x", is_active=True
    )


@pytest.mark.django_db(transaction=True)
class TestActionScopedSerializers:
    def test_list_uses_minimal_serializer(self, configured_urls):
        SampleModel.objects.create(
            integer_field=1, string_field="hidden", choice_field="a"
        )
        response = run_coro(AsyncAPIClient().get("/samples/"))
        body = response.json()
        assert response.status_code == 200
        first = body["results"][0]
        assert "string_field" not in first
        assert "integer_field" in first

    def test_retrieve_uses_full_serializer(self, configured_urls):
        instance = SampleModel.objects.create(
            integer_field=2, string_field="visible", choice_field="b"
        )
        response = run_coro(AsyncAPIClient().get(f"/samples/{instance.pk}/"))
        body = response.json()
        assert response.status_code == 200
        assert body["string_field"] == "visible"
        assert body["choice_field"] == "b"


@pytest.mark.django_db(transaction=True)
class TestActionScopedPermissions:
    def test_create_requires_authentication(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/samples/",
                data={
                    "integer_field": 1,
                    "string_field": "x",
                    "choice_field": "a",
                },
                format="json",
            )
        )
        assert response.status_code in (401, 403)

    def test_create_succeeds_when_authenticated(
        self, configured_urls, regular_user
    ):
        client = AsyncAPIClient()
        client.force_authenticate(user=regular_user)
        response = run_coro(
            client.post(
                "/samples/",
                data={
                    "integer_field": 9,
                    "string_field": "y",
                    "choice_field": "a",
                },
                format="json",
            )
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=9).exists()

    def test_destroy_requires_admin(
        self, configured_urls, regular_user
    ):
        instance = SampleModel.objects.create(integer_field=4)
        client = AsyncAPIClient()
        client.force_authenticate(user=regular_user)
        response = run_coro(
            client.delete(
                f"/samples/{instance.pk}/", data={}, format="json"
            )
        )
        assert response.status_code == 403

    def test_destroy_succeeds_when_admin(
        self, configured_urls, admin_user
    ):
        instance = SampleModel.objects.create(integer_field=4)
        client = AsyncAPIClient()
        client.force_authenticate(user=admin_user)
        response = run_coro(
            client.delete(
                f"/samples/{instance.pk}/", data={}, format="json"
            )
        )
        assert response.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestActionScopedThrottle:
    def test_retrieve_throttled_after_limit(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        first = run_coro(client.get(f"/samples/{instance.pk}/"))
        assert first.status_code == 200
        second = run_coro(client.get(f"/samples/{instance.pk}/"))
        assert second.status_code == 429

    def test_list_not_throttled(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        for _ in range(5):
            assert run_coro(client.get("/samples/")).status_code == 200


@pytest.mark.django_db(transaction=True)
class TestRouterRegistration:
    def test_router_routes_list_action(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)
        response = run_coro(AsyncAPIClient().get("/samples/"))
        assert response.status_code == 200
        assert response.json()["count"] == 2

    def test_router_routes_detail_action(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=99)
        response = run_coro(AsyncAPIClient().get(f"/samples/{instance.pk}/"))
        assert response.status_code == 200
        assert response.json()["integer_field"] == 99

    def test_method_not_allowed_for_post_on_detail(
        self, configured_urls
    ):
        instance = SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().post(
                f"/samples/{instance.pk}/",
                data={"integer_field": 2},
                format="json",
            )
        )
        assert response.status_code == 405


@pytest.mark.django_db(transaction=True)
class TestUpdateAction:
    def test_full_update_via_put(
        self, configured_urls, regular_user
    ):
        instance = SampleModel.objects.create(
            integer_field=1, string_field="a", choice_field="a"
        )
        client = AsyncAPIClient()
        client.force_authenticate(user=regular_user)
        response = run_coro(
            client.put(
                f"/samples/{instance.pk}/",
                data={
                    "integer_field": 5,
                    "string_field": "b",
                    "choice_field": "b",
                },
                format="json",
            )
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
        client = AsyncAPIClient()
        client.force_authenticate(user=regular_user)
        response = run_coro(
            client.patch(
                f"/samples/{instance.pk}/",
                data={"integer_field": 7},
                format="json",
            )
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 7
        assert instance.string_field == "keep"
