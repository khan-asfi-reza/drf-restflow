import asyncio
import itertools

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.serializers import (
    HyperlinkedModelSerializer,
    InlineSerializer,
    ModelSerializer,
    Serializer,
)
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class WriteDRF(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["integer_field", "string_field"]


class ReadDRF(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class WriteRestflow(Serializer):
    integer_field: int
    string_field: str | None


class ReadRestflowModel(ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class ReadRestflowHyperlinked(HyperlinkedModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["url", "integer_field"]
        extra_kwargs = {"url": {"view_name": "sample-detail"}}


WriteInline = InlineSerializer(
    name="WriteInline", fields={"integer_field": int, "string_field": str}
)


ReadInline = InlineSerializer(
    name="ReadInline",
    model=SampleModel,
    model_fields=["id", "integer_field", "string_field"],
)


WRITE_SERIALIZERS = {
    "drf-write": WriteDRF,
    "restflow-write": WriteRestflow,
    "inline-write": WriteInline,
}


READ_SERIALIZERS = {
    "drf-read": ReadDRF,
    "restflow-read-model": ReadRestflowModel,
    "restflow-read-hyperlinked": ReadRestflowHyperlinked,
    "inline-read": ReadInline,
}


SYNC_VIEW_REGISTRY = {}
ASYNC_VIEW_REGISTRY = {}


def make_sync_view(write_cls, read_cls, slug):
    class _SyncEndpoint(APIView):
        permission_classes = [AllowAny]
        request_serializer_class = write_cls
        response_serializer_class = read_cls

        def post(self, request):
            ser = self.validated_serializer()
            instance = SampleModel.objects.create(**ser.validated_data)
            return self.serialized_response(instance, status=201)

    _SyncEndpoint.__name__ = f"SyncEndpoint_{slug}"
    return _SyncEndpoint


def make_async_view(write_cls, read_cls, slug):
    class _AsyncEndpoint(AsyncAPIView):
        permission_classes = [AllowAny]
        request_serializer_class = write_cls
        response_serializer_class = read_cls

        async def post(self, request):
            ser = await self.avalidated_serializer()
            instance = await SampleModel.objects.acreate(
                **ser.validated_data
            )
            return await self.aserialized_response(instance, status=201)

    _AsyncEndpoint.__name__ = f"AsyncEndpoint_{slug}"
    return _AsyncEndpoint


class SampleDetailStub(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        return Response({"id": pk})


urlpatterns = [
    path(
        "samples/<int:pk>/",
        SampleDetailStub.as_view(),
        name="sample-detail",
    ),
]


COMBOS = list(
    itertools.product(WRITE_SERIALIZERS.keys(), READ_SERIALIZERS.keys())
)


for write_key, read_key in COMBOS:
    slug = f"{write_key}__{read_key}"
    sync_view = make_sync_view(
        WRITE_SERIALIZERS[write_key], READ_SERIALIZERS[read_key], slug
    )
    async_view = make_async_view(
        WRITE_SERIALIZERS[write_key], READ_SERIALIZERS[read_key], slug
    )
    SYNC_VIEW_REGISTRY[slug] = sync_view
    ASYNC_VIEW_REGISTRY[slug] = async_view
    urlpatterns.append(path(f"sync/{slug}/", sync_view.as_view()))
    urlpatterns.append(path(f"async/{slug}/", async_view.as_view()))


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db(transaction=True)
class TestSyncRequestResponseSerializerMatrix:
    @pytest.mark.parametrize("write_key,read_key", COMBOS)
    def test_post_round_trip(self, configured_urls, write_key, read_key):
        slug = f"{write_key}__{read_key}"
        response = Client().post(
            f"/sync/{slug}/",
            data='{"integer_field": 1, "string_field": "x"}',
            content_type="application/json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body
        assert SampleModel.objects.filter(integer_field=1).exists()


@pytest.mark.django_db(transaction=True)
class TestAsyncRequestResponseSerializerMatrix:
    @pytest.mark.parametrize("write_key,read_key", COMBOS)
    def test_post_round_trip(self, configured_urls, write_key, read_key):
        slug = f"{write_key}__{read_key}"
        response = run_coro(
            AsyncAPIClient().post(
                f"/async/{slug}/",
                data={"integer_field": 2, "string_field": "y"},
                format="json",
            )
        )
        assert response.status_code == 201
        body = response.json()
        assert body
        assert SampleModel.objects.filter(integer_field=2).exists()


class WriteOnlyValidator(Serializer):
    integer_field: int


class ReadOnlyResponder(Serializer):
    integer_field: int
    label: str


class ResponderViewSync(APIView):
    permission_classes = [AllowAny]
    request_serializer_class = WriteOnlyValidator
    response_serializer_class = ReadOnlyResponder

    def post(self, request):
        ser = self.validated_serializer()
        return self.serialized_response(
            type(
                "Built",
                (),
                {
                    "integer_field": ser.validated_data["integer_field"],
                    "label": "echo",
                },
            )()
        )


class ResponderViewAsync(AsyncAPIView):
    permission_classes = [AllowAny]
    request_serializer_class = WriteOnlyValidator
    response_serializer_class = ReadOnlyResponder

    async def post(self, request):
        ser = await self.avalidated_serializer()
        return await self.aserialized_response(
            type(
                "Built",
                (),
                {
                    "integer_field": ser.validated_data["integer_field"],
                    "label": "echo-async",
                },
            )()
        )


urlpatterns += [
    path("sync-echo/", ResponderViewSync.as_view()),
    path("async-echo/", ResponderViewAsync.as_view()),
]


@pytest.mark.django_db(transaction=True)
class TestExplicitWriteAndReadSeparation:
    def test_sync_write_validator_then_response_serializer(
        self, configured_urls
    ):
        response = Client().post(
            "/sync-echo/",
            data='{"integer_field": 7}',
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {"integer_field": 7, "label": "echo"}

    def test_async_write_validator_then_response_serializer(
        self, configured_urls
    ):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-echo/", data={"integer_field": 9}, format="json"
            )
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {"integer_field": 9, "label": "echo-async"}

    def test_sync_invalid_request_serializer_returns_400(
        self, configured_urls
    ):
        response = Client().post(
            "/sync-echo/",
            data='{"integer_field": "not-int"}',
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_async_invalid_request_serializer_returns_400(
        self, configured_urls
    ):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-echo/",
                data={"integer_field": "not-int"},
                format="json",
            )
        )
        assert response.status_code == 400


class SingleSerializer(Serializer):
    integer_field: int


class SingleSerializerSync(APIView):
    permission_classes = [AllowAny]
    serializer_class = SingleSerializer

    def post(self, request):
        ser = self.validated_serializer()
        return self.serialized_response(
            type("X", (), ser.validated_data)(), status=201
        )


class SingleSerializerAsync(AsyncAPIView):
    permission_classes = [AllowAny]
    serializer_class = SingleSerializer

    async def post(self, request):
        ser = await self.avalidated_serializer()
        return await self.aserialized_response(
            type("X", (), ser.validated_data)(), status=201
        )


urlpatterns += [
    path("single-sync/", SingleSerializerSync.as_view()),
    path("single-async/", SingleSerializerAsync.as_view()),
]


@pytest.mark.django_db(transaction=True)
class TestSingleSerializerForBothDirections:
    def test_sync_single_serializer_round_trip(self, configured_urls):
        response = Client().post(
            "/single-sync/",
            data='{"integer_field": 11}',
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json() == {"integer_field": 11}

    def test_async_single_serializer_round_trip(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/single-async/", data={"integer_field": 12}, format="json"
            )
        )
        assert response.status_code == 201
        assert response.json() == {"integer_field": 12}
