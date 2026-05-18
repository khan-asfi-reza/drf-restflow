import asyncio
import json

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework import generics
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.pagination import PageNumberPagination
from restflow.serializers import ModelSerializer as RestflowModelSerializer
from restflow.serializers import Serializer as RestflowSerializer
from restflow.test import AsyncAPIClient
from restflow.views import (
    APIView,
    AsyncAPIView,
    AsyncCreateAPIView,
    AsyncDestroyAPIView,
    AsyncGenericAPIView,
    AsyncListAPIView,
    AsyncListCreateAPIView,
    AsyncRetrieveAPIView,
    AsyncRetrieveDestroyAPIView,
    AsyncRetrieveUpdateAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
    AsyncUpdateAPIView,
)
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class StandardPagination(PageNumberPagination):
    page_size = 50


class DRFSampleSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class RestflowSampleSerializer(RestflowModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class SyncAllVerbsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"verb": "GET"})

    def post(self, request):
        return Response({"verb": "POST"}, status=201)

    def put(self, request):
        return Response({"verb": "PUT"})

    def patch(self, request):
        return Response({"verb": "PATCH"})

    def delete(self, request):
        return Response({"verb": "DELETE"}, status=204)


class AsyncAllVerbsView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        return Response({"verb": "GET"})

    async def post(self, request):
        return Response({"verb": "POST"}, status=201)

    async def put(self, request):
        return Response({"verb": "PUT"})

    async def patch(self, request):
        return Response({"verb": "PATCH"})

    async def delete(self, request):
        return Response({"verb": "DELETE"}, status=204)


class MixedVerbsView(AsyncAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"verb": "GET", "shape": "sync"})

    async def post(self, request):
        return Response({"verb": "POST", "shape": "async"}, status=201)

    def put(self, request):
        return Response({"verb": "PUT", "shape": "sync"})

    async def patch(self, request):
        return Response({"verb": "PATCH", "shape": "async"})

    async def delete(self, request):
        return Response({"verb": "DELETE", "shape": "async"}, status=204)


class AsyncWithSyncSerializerView(AsyncCreateAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncWithRestflowSerializerView(AsyncCreateAPIView):
    serializer_class = RestflowSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class SyncDRFGenericListCreateView(generics.ListCreateAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardPagination
    queryset = SampleModel.objects.all().order_by("id")


class SyncDRFGenericDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]
    queryset = SampleModel.objects.all()


class AsyncListView(AsyncListAPIView):
    serializer_class = DRFSampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class AsyncRetrieveView(AsyncRetrieveAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncCreateView(AsyncCreateAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncUpdateView(AsyncUpdateAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncDestroyView(AsyncDestroyAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncListCreateView(AsyncListCreateAPIView):
    serializer_class = DRFSampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class AsyncRetrieveUpdateView(AsyncRetrieveUpdateAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncRetrieveDestroyView(AsyncRetrieveDestroyAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncRudView(AsyncRetrieveUpdateDestroyAPIView):
    serializer_class = DRFSampleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all()


class AsyncFilterPassThroughBackend:
    async def afilter_queryset(self, request, queryset, view):
        return queryset


class SyncFilterPassThroughBackend:
    def filter_queryset(self, request, queryset, view):
        return queryset


class AsyncListWithAsyncBackendView(AsyncListAPIView):
    serializer_class = DRFSampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    filter_backends = [AsyncFilterPassThroughBackend]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class AsyncListWithSyncBackendView(AsyncListAPIView):
    serializer_class = DRFSampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]
    filter_backends = [SyncFilterPassThroughBackend]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


class AsyncGenericAPIBareView(AsyncGenericAPIView):
    serializer_class = DRFSampleSerializer
    pagination_class = StandardPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")

    async def get(self, request):
        queryset = await self.afilter_queryset(self.get_queryset())
        page = await self.apaginate_queryset(queryset)
        ser = self.get_serializer(page, many=True)
        return self.get_paginated_response(ser.data)


urlpatterns = [
    path("sync-all/", SyncAllVerbsView.as_view()),
    path("async-all/", AsyncAllVerbsView.as_view()),
    path("mixed-all/", MixedVerbsView.as_view()),
    path("async-drf-create/", AsyncWithSyncSerializerView.as_view()),
    path("async-restflow-create/", AsyncWithRestflowSerializerView.as_view()),
    path("sync-drf-listcreate/", SyncDRFGenericListCreateView.as_view()),
    path("sync-drf-detail/<int:pk>/", SyncDRFGenericDetailView.as_view()),
    path("async-list/", AsyncListView.as_view()),
    path("async-retrieve/<int:pk>/", AsyncRetrieveView.as_view()),
    path("async-create/", AsyncCreateView.as_view()),
    path("async-update/<int:pk>/", AsyncUpdateView.as_view()),
    path("async-destroy/<int:pk>/", AsyncDestroyView.as_view()),
    path("async-listcreate/", AsyncListCreateView.as_view()),
    path("async-retrieveupdate/<int:pk>/", AsyncRetrieveUpdateView.as_view()),
    path("async-retrievedestroy/<int:pk>/", AsyncRetrieveDestroyView.as_view()),
    path("async-rud/<int:pk>/", AsyncRudView.as_view()),
    path("async-list-async-backend/", AsyncListWithAsyncBackendView.as_view()),
    path("async-list-sync-backend/", AsyncListWithSyncBackendView.as_view()),
    path("async-bare-generic/", AsyncGenericAPIBareView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db(transaction=True)
class TestSyncAPIViewVerbs:
    def test_sync_get(self, configured_urls):
        response = Client().get("/sync-all/")
        assert response.status_code == 200
        assert response.json() == {"verb": "GET"}

    def test_sync_post(self, configured_urls):
        response = Client().post(
            "/sync-all/", data="{}", content_type="application/json"
        )
        assert response.status_code == 201
        assert response.json() == {"verb": "POST"}

    def test_sync_put(self, configured_urls):
        response = Client().put(
            "/sync-all/", data="{}", content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json() == {"verb": "PUT"}

    def test_sync_patch(self, configured_urls):
        response = Client().patch(
            "/sync-all/", data="{}", content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json() == {"verb": "PATCH"}

    def test_sync_delete(self, configured_urls):
        response = Client().delete("/sync-all/")
        assert response.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestAsyncAPIViewVerbs:
    def test_async_get(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async-all/"))
        assert response.status_code == 200
        assert response.json() == {"verb": "GET"}

    def test_async_post(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post("/async-all/", data={}, format="json")
        )
        assert response.status_code == 201

    def test_async_put(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().put("/async-all/", data={}, format="json")
        )
        assert response.status_code == 200

    def test_async_patch(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().patch("/async-all/", data={}, format="json")
        )
        assert response.status_code == 200

    def test_async_delete(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().delete("/async-all/", data={}, format="json")
        )
        assert response.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestMixedHandlerView:
    def test_mixed_sync_get_in_async_dispatch(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/mixed-all/"))
        assert response.status_code == 200
        assert response.json() == {"verb": "GET", "shape": "sync"}

    def test_mixed_async_post_in_async_dispatch(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post("/mixed-all/", data={}, format="json")
        )
        assert response.status_code == 201
        assert response.json() == {"verb": "POST", "shape": "async"}

    def test_mixed_sync_put_in_async_dispatch(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().put("/mixed-all/", data={}, format="json")
        )
        assert response.status_code == 200
        assert response.json() == {"verb": "PUT", "shape": "sync"}

    def test_mixed_async_patch_in_async_dispatch(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().patch("/mixed-all/", data={}, format="json")
        )
        assert response.status_code == 200

    def test_mixed_async_delete_in_async_dispatch(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().delete("/mixed-all/", data={}, format="json")
        )
        assert response.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestAsyncViewWithSyncSerializer:
    def test_create_with_drf_sync_serializer(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-drf-create/",
                data={"integer_field": 5, "string_field": "x"},
                format="json",
            )
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=5).exists()

    def test_create_with_restflow_async_serializer(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-restflow-create/",
                data={"integer_field": 7, "string_field": "y"},
                format="json",
            )
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=7).exists()


@pytest.mark.django_db(transaction=True)
class TestSyncDRFGenericRoundTrip:
    def test_sync_listcreate_get(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)
        response = Client().get("/sync-drf-listcreate/")
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 2

    def test_sync_listcreate_post(self, configured_urls):
        response = Client().post(
            "/sync-drf-listcreate/",
            data=json.dumps({"integer_field": 9}),
            content_type="application/json",
        )
        assert response.status_code == 201

    def test_sync_detail_full_lifecycle(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = Client()
        get_resp = client.get(f"/sync-drf-detail/{instance.pk}/")
        assert get_resp.status_code == 200
        put_resp = client.put(
            f"/sync-drf-detail/{instance.pk}/",
            data=json.dumps({"integer_field": 9}),
            content_type="application/json",
        )
        assert put_resp.status_code == 200
        patch_resp = client.patch(
            f"/sync-drf-detail/{instance.pk}/",
            data=json.dumps({"integer_field": 11}),
            content_type="application/json",
        )
        assert patch_resp.status_code == 200
        delete_resp = client.delete(f"/sync-drf-detail/{instance.pk}/")
        assert delete_resp.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestAsyncGenericRoundTrip:
    def test_async_list(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)
        response = run_coro(AsyncAPIClient().get("/async-list/"))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 2

    def test_async_retrieve(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=42)
        response = run_coro(
            AsyncAPIClient().get(f"/async-retrieve/{instance.pk}/")
        )
        assert response.status_code == 200
        assert response.json()["integer_field"] == 42

    def test_async_create(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-create/",
                data={"integer_field": 99},
                format="json",
            )
        )
        assert response.status_code == 201
        assert SampleModel.objects.filter(integer_field=99).exists()

    def test_async_update_put(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().put(
                f"/async-update/{instance.pk}/",
                data={"integer_field": 88},
                format="json",
            )
        )
        assert response.status_code == 200
        instance.refresh_from_db()
        assert instance.integer_field == 88

    def test_async_update_patch(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().patch(
                f"/async-update/{instance.pk}/",
                data={"integer_field": 7},
                format="json",
            )
        )
        assert response.status_code == 200

    def test_async_destroy(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().delete(
                f"/async-destroy/{instance.pk}/", data={}, format="json"
            )
        )
        assert response.status_code == 204
        assert not SampleModel.objects.filter(pk=instance.pk).exists()

    def test_async_listcreate_get_then_post(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        list_resp = run_coro(client.get("/async-listcreate/"))
        assert list_resp.json()["count"] == 1
        create_resp = run_coro(
            client.post(
                "/async-listcreate/",
                data={"integer_field": 2},
                format="json",
            )
        )
        assert create_resp.status_code == 201

    def test_async_retrieveupdate_full_cycle(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        assert (
            run_coro(client.get(f"/async-retrieveupdate/{instance.pk}/")).status_code
            == 200
        )
        put_resp = run_coro(
            client.put(
                f"/async-retrieveupdate/{instance.pk}/",
                data={"integer_field": 9},
                format="json",
            )
        )
        assert put_resp.status_code == 200

    def test_async_retrievedestroy_full_cycle(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        assert (
            run_coro(client.get(f"/async-retrievedestroy/{instance.pk}/")).status_code
            == 200
        )
        delete_resp = run_coro(
            client.delete(
                f"/async-retrievedestroy/{instance.pk}/",
                data={},
                format="json",
            )
        )
        assert delete_resp.status_code == 204

    def test_async_rud_full_cycle(self, configured_urls):
        instance = SampleModel.objects.create(integer_field=1)
        client = AsyncAPIClient()
        assert (
            run_coro(client.get(f"/async-rud/{instance.pk}/")).status_code == 200
        )
        assert (
            run_coro(
                client.put(
                    f"/async-rud/{instance.pk}/",
                    data={"integer_field": 7},
                    format="json",
                )
            ).status_code
            == 200
        )
        assert (
            run_coro(
                client.patch(
                    f"/async-rud/{instance.pk}/",
                    data={"integer_field": 8},
                    format="json",
                )
            ).status_code
            == 200
        )
        assert (
            run_coro(
                client.delete(
                    f"/async-rud/{instance.pk}/", data={}, format="json"
                )
            ).status_code
            == 204
        )


@pytest.mark.django_db(transaction=True)
class TestAsyncFilterBackendModes:
    def test_async_list_with_async_backend(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().get("/async-list-async-backend/")
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_async_list_with_sync_backend_falls_back(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = run_coro(
            AsyncAPIClient().get("/async-list-sync-backend/")
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1


@pytest.mark.django_db(transaction=True)
class TestAsyncBareGenericView:
    def test_async_generic_with_manual_handler(self, configured_urls):
        for i in range(3):
            SampleModel.objects.create(integer_field=i)
        response = run_coro(AsyncAPIClient().get("/async-bare-generic/"))
        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 3


@pytest.mark.django_db(transaction=True)
class TestMethodNotAllowed:
    def test_sync_view_unsupported_method_returns_405(self, configured_urls):
        SampleModel.objects.create(integer_field=1)
        response = Client().delete("/sync-drf-listcreate/")
        assert response.status_code == 405

    def test_async_list_unsupported_method_returns_405(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().delete(
                "/async-list/", data={}, format="json"
            )
        )
        assert response.status_code == 405

    def test_async_create_unsupported_method_returns_405(
        self, configured_urls
    ):
        response = run_coro(AsyncAPIClient().get("/async-create/"))
        assert response.status_code == 405


@pytest.mark.django_db(transaction=True)
class TestAsyncViewSerializesRestflowAndDRFInOneSession:
    def test_consecutive_calls_to_drf_and_restflow_views(self, configured_urls):
        client = AsyncAPIClient()
        drf_resp = run_coro(
            client.post(
                "/async-drf-create/",
                data={"integer_field": 11, "string_field": "drf"},
                format="json",
            )
        )
        restflow_resp = run_coro(
            client.post(
                "/async-restflow-create/",
                data={"integer_field": 12, "string_field": "rf"},
                format="json",
            )
        )
        assert drf_resp.status_code == 201
        assert restflow_resp.status_code == 201
        assert SampleModel.objects.filter(string_field="drf").exists()
        assert SampleModel.objects.filter(string_field="rf").exists()
