import asyncio
import json

import pytest
from django.test import override_settings
from django.urls import path
from rest_framework.permissions import AllowAny

from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)
from restflow.test import AsyncAPIClient
from restflow.views import AsyncAPIView
from tests.models import SampleModel


def run_coro(coro):
    return asyncio.run(coro)


class StreamJSONView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            async for row in SampleModel.objects.all().order_by("id"):
                yield {"id": row.pk, "n": row.integer_field}

        return StreamingJSONListResponse(emit())


class NDJSONView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            async for row in SampleModel.objects.all().order_by("id"):
                yield {"id": row.pk, "label": row.string_field or ""}

        return NDJSONResponse(emit())


class SSEView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        async def emit():
            async for row in SampleModel.objects.all().order_by("id"):
                yield {
                    "id": str(row.pk),
                    "event": "sample",
                    "data": {"value": row.integer_field},
                }

        return SSEResponse(emit())


urlpatterns = [
    path("stream-json/", StreamJSONView.as_view()),
    path("ndjson/", NDJSONView.as_view()),
    path("sse/", SSEView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__):
        yield


@pytest.fixture
def seeded_rows(db):
    return [
        SampleModel.objects.create(integer_field=i, string_field=f"row-{i}")
        for i in range(5)
    ]


async def drain_async(response):
    out = []
    async for chunk in response.streaming_content:
        out.append(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        )
    return "".join(out)


def drain(response):
    streamer = response.streaming_content
    if hasattr(streamer, "__aiter__"):
        return run_coro(drain_async(response))
    out = []
    for chunk in streamer:
        out.append(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        )
    return "".join(out)


@pytest.mark.django_db(transaction=True)
class TestStreamingJSONListEndpoint:
    def test_returns_full_list(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/stream-json/"))
        body = drain(response)
        parsed = json.loads(body)
        assert response.status_code == 200
        assert len(parsed) == 5
        assert parsed[0]["n"] == 0

    def test_content_type(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/stream-json/"))
        assert response.headers["Content-Type"].startswith("application/json")

    def test_handles_empty_table(self, configured_urls, db):
        response = run_coro(AsyncAPIClient().get("/stream-json/"))
        body = drain(response)
        assert json.loads(body) == []


@pytest.mark.django_db(transaction=True)
class TestNDJSONEndpoint:
    def test_one_object_per_line(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/ndjson/"))
        body = drain(response)
        lines = body.strip().split("\n")
        assert len(lines) == 5
        first = json.loads(lines[0])
        assert "id" in first

    def test_content_type(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/ndjson/"))
        assert response.headers["Content-Type"] == "application/x-ndjson"


@pytest.mark.django_db(transaction=True)
class TestSSEEndpoint:
    def test_emits_event_blocks(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/sse/"))
        body = drain(response)
        blocks = body.strip().split("\n\n")
        assert len(blocks) == 5
        first = blocks[0]
        assert "event: sample" in first
        assert "data:" in first

    def test_buffering_headers(self, configured_urls, seeded_rows):
        response = run_coro(AsyncAPIClient().get("/sse/"))
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"
        assert response.headers["Content-Type"] == "text/event-stream"
