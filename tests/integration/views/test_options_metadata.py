import asyncio

import pytest
from django.test import override_settings
from django.urls import path

from restflow.serializers import ModelSerializer
from restflow.test import AsyncAPIClient
from restflow.views import (
    APIView,
    AsyncAPIView,
    AsyncRetrieveUpdateDestroyAPIView,
)
from tests.models import SampleModel


class _SampleSerializer(ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "string_field"]


class _DetailView(AsyncRetrieveUpdateDestroyAPIView):
    queryset = SampleModel.objects.all()
    serializer_class = _SampleSerializer


class _AsyncPlainView(AsyncAPIView):
    async def get(self, request):
        return None


class _SyncPlainView(APIView):
    def get(self, request):
        return None


urlpatterns = [
    path("detail/<int:pk>/", _DetailView.as_view()),
    path("async-plain/", _AsyncPlainView.as_view()),
    path("sync-plain/", _SyncPlainView.as_view()),
]


@pytest.fixture
def urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.mark.django_db(transaction=True)
def test_options_on_an_async_detail_view_reaches_the_database(urls):
    instance = SampleModel.objects.create(string_field="row")

    async def run():
        response = await AsyncAPIClient().options(f"/detail/{instance.pk}/")
        assert response.status_code == 200
        assert response.data["renders"]
        assert "PUT" in response.data["actions"]

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_options_on_an_async_view_without_a_serializer(urls):
    async def run():
        response = await AsyncAPIClient().options("/async-plain/")
        assert response.status_code == 200
        assert response.data["renders"]
        assert "actions" not in response.data

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_options_on_a_sync_view_without_a_serializer(urls):
    async def run():
        response = await AsyncAPIClient().options("/sync-plain/")
        assert response.status_code == 200
        assert response.data["renders"]

    asyncio.run(run())
