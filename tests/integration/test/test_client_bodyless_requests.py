import asyncio

import pytest
from django.test import override_settings
from django.urls import path
from rest_framework.response import Response

from restflow.test import AsyncAPIClient
from restflow.views import AsyncAPIView


class _MethodEchoView(AsyncAPIView):
    async def delete(self, request):
        return Response({"method": request.method, "body": request.data})

    async def post(self, request):
        return Response({"method": request.method, "body": request.data})

    async def options(self, request, *args, **kwargs):
        return Response({"method": request.method})


urlpatterns = [path("resource/", _MethodEchoView.as_view())]


@pytest.fixture
def urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


def test_delete_without_a_body(urls):
    async def run():
        response = await AsyncAPIClient().delete("/resource/")
        assert response.status_code == 200
        assert response.data["method"] == "DELETE"

    asyncio.run(run())


def test_post_without_a_body(urls):
    async def run():
        response = await AsyncAPIClient().post("/resource/")
        assert response.status_code == 200
        assert response.data["method"] == "POST"

    asyncio.run(run())


def test_options_without_a_body(urls):
    async def run():
        response = await AsyncAPIClient().options("/resource/")
        assert response.status_code == 200

    asyncio.run(run())


def test_delete_with_a_body_still_encodes_json(urls):
    async def run():
        response = await AsyncAPIClient().delete(
            "/resource/", {"reason": "cleanup"}, format="json"
        )
        assert response.status_code == 200
        assert response.data["body"] == {"reason": "cleanup"}

    asyncio.run(run())
