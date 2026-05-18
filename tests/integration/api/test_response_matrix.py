import asyncio
import json

import pytest
from django.test import Client, override_settings
from django.urls import path
from rest_framework import status as drf_status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


class SyncJSONResponseView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"format": "json"}, status=drf_status.HTTP_200_OK)


class SyncCreatedResponseView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        return Response({"created": True}, status=drf_status.HTTP_201_CREATED)


class SyncNoContentResponseView(APIView):
    permission_classes = [AllowAny]

    def delete(self, request):
        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class AsyncJSONResponseView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        return Response({"format": "json", "shape": "async"})


class AsyncCreatedResponseView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def post(self, request):
        return Response({"created": True}, status=drf_status.HTTP_201_CREATED)


class AsyncNoContentResponseView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def delete(self, request):
        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class AsyncStreamingJSONView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            for i in range(3):
                yield {"i": i}

        return StreamingJSONListResponse(emit())


class AsyncNDJSONView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            for i in range(3):
                yield {"i": i}

        return NDJSONResponse(emit())


class AsyncSSEView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            for i in range(3):
                yield {"event": "tick", "data": {"i": i}}

        return SSEResponse(emit())


urlpatterns = [
    path("sync-json/", SyncJSONResponseView.as_view()),
    path("sync-created/", SyncCreatedResponseView.as_view()),
    path("sync-empty/", SyncNoContentResponseView.as_view()),
    path("async-json/", AsyncJSONResponseView.as_view()),
    path("async-created/", AsyncCreatedResponseView.as_view()),
    path("async-empty/", AsyncNoContentResponseView.as_view()),
    path("stream-json/", AsyncStreamingJSONView.as_view()),
    path("ndjson/", AsyncNDJSONView.as_view()),
    path("sse/", AsyncSSEView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


async def collect_async(response):
    out = []
    async for chunk in response.streaming_content:
        out.append(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        )
    return "".join(out)


def collect(response):
    streamer = response.streaming_content
    if hasattr(streamer, "__aiter__"):
        return run_coro(collect_async(response))
    return "".join(
        chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        for chunk in streamer
    )


@pytest.mark.django_db(transaction=True)
class TestSyncResponseShapes:
    def test_sync_json_200(self, configured_urls):
        response = Client().get("/sync-json/")
        assert response.status_code == 200
        assert response.json() == {"format": "json"}
        assert response["Content-Type"].startswith("application/json")

    def test_sync_201(self, configured_urls):
        response = Client().post(
            "/sync-created/", data="{}", content_type="application/json"
        )
        assert response.status_code == 201
        assert response.json() == {"created": True}

    def test_sync_204_no_body(self, configured_urls):
        response = Client().delete("/sync-empty/")
        assert response.status_code == 204
        assert response.content == b""


@pytest.mark.django_db(transaction=True)
class TestAsyncResponseShapes:
    def test_async_json_200(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async-json/"))
        assert response.status_code == 200
        assert response.json() == {"format": "json", "shape": "async"}

    def test_async_201(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/async-created/", data={}, format="json"
            )
        )
        assert response.status_code == 201
        assert response.json() == {"created": True}

    def test_async_204(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().delete(
                "/async-empty/", data={}, format="json"
            )
        )
        assert response.status_code == 204

    def test_async_streaming_json_list(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/stream-json/"))
        body = collect(response)
        assert json.loads(body) == [{"i": 0}, {"i": 1}, {"i": 2}]

    def test_async_ndjson(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/ndjson/"))
        body = collect(response)
        lines = body.strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0]) == {"i": 0}

    def test_async_sse(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/sse/"))
        body = collect(response)
        blocks = body.strip().split("\n\n")
        assert len(blocks) == 3
        assert "event: tick" in blocks[0]


@pytest.mark.django_db(transaction=True)
class TestStreamingResponseHeaders:
    def test_streaming_json_content_type(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/stream-json/"))
        assert response.headers["Content-Type"].startswith("application/json")

    def test_ndjson_content_type(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/ndjson/"))
        assert response.headers["Content-Type"] == "application/x-ndjson"

    def test_sse_buffering_headers(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/sse/"))
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"
