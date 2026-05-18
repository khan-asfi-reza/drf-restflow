import asyncio
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import path
from rest_framework.permissions import AllowAny

from restflow.authentication import AccessToken, JWTAuthentication
from restflow.pagination import PageNumberPagination
from restflow.permissions import IsAuthenticated
from restflow.serializers import ModelSerializer
from restflow.test import AsyncAPIClient
from restflow.views import (
    AsyncListCreateAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
)
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class SamplePagination(PageNumberPagination):
    page_size = 3


class SampleSerializer(ModelSerializer):
    class Meta:
        model = SampleModel
        fields = [
            "id",
            "integer_field",
            "string_field",
            "boolean_field",
            "choice_field",
        ]


class SampleListCreateView(AsyncListCreateAPIView):
    serializer_class = SampleSerializer
    pagination_class = SamplePagination
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class SampleDetailView(AsyncRetrieveUpdateDestroyAPIView):
    serializer_class = SampleSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        return SampleModel.objects.all()


class SampleAnonListView(AsyncListCreateAPIView):
    serializer_class = SampleSerializer
    pagination_class = SamplePagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


urlpatterns = [
    path("samples/", SampleListCreateView.as_view(), name="samples"),
    path("samples/<int:pk>/", SampleDetailView.as_view(), name="sample-detail"),
    path("anon/", SampleAnonListView.as_view(), name="anon"),
]


JWT_OVERRIDES = {
    "RESTFLOW_SETTINGS": {
        "JWT": {
            "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
            "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
            "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
            "BLACKLIST_ENABLED": True,
            "BLACKLIST_ALLOW_LOCMEM": True,
        }
    }
}


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__, **JWT_OVERRIDES):
        yield


@pytest.fixture
def authenticated_user(db):
    User = get_user_model()
    user = User.objects.create_user(
        username="khan", password="khan-password", is_active=True
    )
    return user


def bearer(user):
    token = AccessToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.mark.django_db(transaction=True)
class TestAsyncListCreate:
    def test_list_unauthenticated_returns_401(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/samples/"))
        assert response.status_code == 401

    def test_list_authenticated_returns_paginated_payload(
        self, configured_urls, authenticated_user
    ):
        for i in range(5):
            SampleModel.objects.create(integer_field=i, string_field=f"s{i}")
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(client.get("/samples/"))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 5
        assert len(body["results"]) == 3
        assert body["results"][0]["integer_field"] == 0

    def test_list_second_page(self, configured_urls, authenticated_user):
        for i in range(5):
            SampleModel.objects.create(integer_field=i, string_field=f"s{i}")
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(client.get("/samples/?page=2"))
        body = response.json()
        assert response.status_code == 200
        assert len(body["results"]) == 2
        assert body["results"][0]["integer_field"] == 3

    def test_list_invalid_page_returns_404(
        self, configured_urls, authenticated_user
    ):
        SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(client.get("/samples/?page=999"))
        assert response.status_code == 404

    def test_create_authenticated_round_trip(
        self, configured_urls, authenticated_user
    ):
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.post(
                "/samples/",
                data={
                    "integer_field": 42,
                    "string_field": "created",
                    "boolean_field": True,
                    "choice_field": "a",
                },
                format="json",
            )
        )
        assert response.status_code == 201
        assert response.json()["integer_field"] == 42
        assert SampleModel.objects.filter(integer_field=42).exists()

    def test_create_invalid_choice_returns_400(
        self, configured_urls, authenticated_user
    ):
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.post(
                "/samples/",
                data={"integer_field": 1, "choice_field": "z"},
                format="json",
            )
        )
        assert response.status_code == 400

    def test_create_missing_required_field_uses_blank(
        self, configured_urls, authenticated_user
    ):
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.post("/samples/", data={"integer_field": 7}, format="json")
        )
        assert response.status_code == 201

    def test_method_not_allowed_for_put_on_collection(
        self, configured_urls, authenticated_user
    ):
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.put("/samples/", data={"integer_field": 1}, format="json")
        )
        assert response.status_code == 405

    def test_anon_endpoint_allows_unauthenticated(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = run_coro(AsyncAPIClient().get("/anon/"))
        assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
class TestAsyncRetrieveUpdateDestroy:
    def test_retrieve_authenticated(self, configured_urls, authenticated_user):
        instance = SampleModel.objects.create(integer_field=11, string_field="x")
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(client.get(f"/samples/{instance.pk}/"))
        assert response.status_code == 200
        assert response.json()["integer_field"] == 11

    def test_retrieve_missing_returns_404(
        self, configured_urls, authenticated_user
    ):
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(client.get("/samples/99999/"))
        assert response.status_code == 404

    def test_full_update_replaces_fields(
        self, configured_urls, authenticated_user
    ):
        instance = SampleModel.objects.create(integer_field=1, string_field="old")
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.put(
                f"/samples/{instance.pk}/",
                data={
                    "integer_field": 99,
                    "string_field": "new",
                    "boolean_field": False,
                    "choice_field": "b",
                },
                format="json",
            )
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 99
        assert instance.string_field == "new"

    def test_partial_update_keeps_unchanged_fields(
        self, configured_urls, authenticated_user
    ):
        instance = SampleModel.objects.create(
            integer_field=1, string_field="keep"
        )
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.patch(
                f"/samples/{instance.pk}/",
                data={"integer_field": 88},
                format="json",
            )
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 88
        assert instance.string_field == "keep"

    def test_destroy_removes_instance(
        self, configured_urls, authenticated_user
    ):
        instance = SampleModel.objects.create(integer_field=5)
        client = AsyncAPIClient()
        client.credentials(**bearer(authenticated_user))
        response = run_coro(
            client.delete(
                f"/samples/{instance.pk}/", data={}, format="json"
            )
        )
        assert response.status_code == 204
        assert not SampleModel.objects.filter(pk=instance.pk).exists()

    def test_destroy_unauthenticated_returns_401(
        self, configured_urls
    ):
        instance = SampleModel.objects.create(integer_field=5)
        response = run_coro(
            AsyncAPIClient().delete(
                f"/samples/{instance.pk}/", data={}, format="json"
            )
        )
        assert response.status_code == 401
        assert SampleModel.objects.filter(pk=instance.pk).exists()
