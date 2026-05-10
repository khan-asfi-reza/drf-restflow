import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import path
from rest_framework import generics
from rest_framework import serializers as drf_serializers
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from restflow.authentication import TokenAuthentication
from restflow.pagination import PageNumberPagination
from restflow.views import APIView
from tests.models import SampleModel


class SamplePagination(PageNumberPagination):
    page_size = 2


class SampleSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field", "choice_field"]


class SampleListCreateView(generics.ListCreateAPIView):
    serializer_class = SampleSerializer
    pagination_class = SamplePagination
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    queryset = SampleModel.objects.all().order_by("id")


class SampleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SampleSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    queryset = SampleModel.objects.all()


class HelpersView(APIView):
    serializer_class = SampleSerializer
    pagination_class = SamplePagination
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get(self, request):
        return self.paginated_response(
            SampleModel.objects.all().order_by("id")
        )

    def post(self, request):
        ser = self.validated_serializer()
        instance = SampleModel.objects.create(**ser.validated_data)
        return self.serialized_response(instance, status=201)


urlpatterns = [
    path("samples/", SampleListCreateView.as_view()),
    path("samples/<int:pk>/", SampleDetailView.as_view()),
    path("helpers/", HelpersView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.fixture
def token_auth(db):
    User = get_user_model()
    user = User.objects.create_user(username="bob", password="x", is_active=True)
    token = Token.objects.create(user=user)
    return user, token


def auth_headers(token):
    return {"HTTP_AUTHORIZATION": f"Token {token.key}"}


@pytest.mark.django_db
class TestSyncListCreate:
    def test_list_unauthenticated_returns_401(self, configured_urls):
        response = Client().get("/samples/")
        assert response.status_code == 401

    def test_list_authenticated_paginated(self, configured_urls, token_auth):
        _, token = token_auth
        for i in range(4):
            SampleModel.objects.create(integer_field=i)
        response = Client().get("/samples/", **auth_headers(token))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 4
        assert len(body["results"]) == 2

    def test_list_second_page(self, configured_urls, token_auth):
        _, token = token_auth
        for i in range(4):
            SampleModel.objects.create(integer_field=i)
        response = Client().get("/samples/?page=2", **auth_headers(token))
        body = response.json()
        assert len(body["results"]) == 2
        assert body["results"][0]["integer_field"] == 2

    def test_create_round_trip(self, configured_urls, token_auth):
        _, token = token_auth
        response = Client().post(
            "/samples/",
            data=json.dumps({"integer_field": 5, "choice_field": "a"}),
            content_type="application/json",
            **auth_headers(token),
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=5).exists()

    def test_create_invalid_returns_400(self, configured_urls, token_auth):
        _, token = token_auth
        response = Client().post(
            "/samples/",
            data=json.dumps({"choice_field": "z"}),
            content_type="application/json",
            **auth_headers(token),
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestSyncRetrieveUpdateDestroy:
    def test_retrieve(self, configured_urls, token_auth):
        _, token = token_auth
        instance = SampleModel.objects.create(integer_field=10)
        response = Client().get(
            f"/samples/{instance.pk}/", **auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["integer_field"] == 10

    def test_full_update(self, configured_urls, token_auth):
        _, token = token_auth
        instance = SampleModel.objects.create(integer_field=1)
        response = Client().put(
            f"/samples/{instance.pk}/",
            data=json.dumps(
                {"integer_field": 77, "string_field": "z", "choice_field": "a"}
            ),
            content_type="application/json",
            **auth_headers(token),
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 77

    def test_partial_update(self, configured_urls, token_auth):
        _, token = token_auth
        instance = SampleModel.objects.create(integer_field=1, string_field="a")
        response = Client().patch(
            f"/samples/{instance.pk}/",
            data=json.dumps({"integer_field": 88}),
            content_type="application/json",
            **auth_headers(token),
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 88
        assert instance.string_field == "a"

    def test_destroy(self, configured_urls, token_auth):
        _, token = token_auth
        instance = SampleModel.objects.create(integer_field=1)
        response = Client().delete(
            f"/samples/{instance.pk}/", **auth_headers(token)
        )
        assert response.status_code == 204
        assert not SampleModel.objects.filter(pk=instance.pk).exists()


@pytest.mark.django_db
class TestSyncHelpers:
    def test_paginated_response_helper(self, configured_urls, token_auth):
        _, token = token_auth
        for i in range(3):
            SampleModel.objects.create(integer_field=i)
        response = Client().get("/helpers/", **auth_headers(token))
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 3
        assert len(body["results"]) == 2

    def test_serialized_response_helper(self, configured_urls, token_auth):
        _, token = token_auth
        response = Client().post(
            "/helpers/",
            data=json.dumps({"integer_field": 9, "choice_field": "a"}),
            content_type="application/json",
            **auth_headers(token),
        )
        assert response.status_code == 201
        assert response.json()["integer_field"] == 9
