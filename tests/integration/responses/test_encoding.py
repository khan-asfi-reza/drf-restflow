import asyncio
import json
import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)


def run_coro(coro):
    return asyncio.run(coro)


async def aiter_items(items):
    for item in items:
        yield item


async def drain(response):
    out = []
    async for chunk in response.streaming_content:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        out.append(text)
    return "".join(out)


def test_streaming_json_list_response_handles_decimal():
    response = StreamingJSONListResponse(aiter_items([{"price": Decimal("1.5")}]))
    body = run_coro(drain(response))
    parsed = json.loads(body)
    assert parsed == [{"price": "1.5"}]


def test_streaming_json_list_response_handles_datetime():
    now = datetime(2024, 1, 1, 12, 0, 0)
    response = StreamingJSONListResponse(aiter_items([{"at": now}]))
    body = run_coro(drain(response))
    parsed = json.loads(body)
    assert parsed[0]["at"].startswith("2024-01-01")


def test_streaming_json_list_response_handles_uuid():
    u = uuid.UUID("12345678-1234-5678-1234-567812345678")
    response = StreamingJSONListResponse(aiter_items([{"id": u}]))
    body = run_coro(drain(response))
    parsed = json.loads(body)
    assert parsed[0]["id"] == str(u)


def test_streaming_json_list_response_handles_nested_objects():
    response = StreamingJSONListResponse(
        aiter_items([{"a": {"b": [1, 2, 3]}}])
    )
    body = run_coro(drain(response))
    assert json.loads(body) == [{"a": {"b": [1, 2, 3]}}]


def test_streaming_json_list_response_handles_long_iterable():
    items = [{"i": i} for i in range(100)]
    response = StreamingJSONListResponse(aiter_items(items))
    body = run_coro(drain(response))
    parsed = json.loads(body)
    assert len(parsed) == 100


def test_ndjson_handles_empty_iter():
    response = NDJSONResponse(aiter_items([]))
    body = run_coro(drain(response))
    assert body == ""


def test_ndjson_each_line_independently_parseable():
    items = [{"i": i} for i in range(5)]
    response = NDJSONResponse(aiter_items(items))
    body = run_coro(drain(response))
    lines = body.strip().split("\n")
    for i, line in enumerate(lines):
        assert json.loads(line) == {"i": i}


def test_sse_event_with_only_data_dict():
    response = SSEResponse(aiter_items([{"data": {"a": 1}}]))
    body = run_coro(drain(response))
    assert "data: " in body
    assert "{" in body


def test_sse_event_with_id_only():
    response = SSEResponse(aiter_items([{"id": "abc", "data": "x"}]))
    body = run_coro(drain(response))
    assert "id: abc" in body


def test_sse_event_with_event_type_only():
    response = SSEResponse(aiter_items([{"event": "ping", "data": "x"}]))
    body = run_coro(drain(response))
    assert "event: ping" in body


def test_sse_event_with_retry_only():
    response = SSEResponse(aiter_items([{"retry": 5000, "data": "x"}]))
    body = run_coro(drain(response))
    assert "retry: 5000" in body


def test_sse_event_terminates_with_double_newline():
    response = SSEResponse(aiter_items(["hello"]))
    body = run_coro(drain(response))
    assert body.endswith("\n\n")


def test_sse_string_event_with_newlines_normalized():
    response = SSEResponse(aiter_items(["line1\nline2"]))
    body = run_coro(drain(response))
    assert "data: line1" in body
    assert "data: line2" in body


def test_sse_rejects_newline_in_retry_value():
    async def gen():
        yield {"retry": "100\n200", "data": "x"}

    response = SSEResponse(gen())
    with pytest.raises(ValueError, match="must not contain"):
        run_coro(drain(response))


def test_streaming_json_list_with_bytes_chunks_round_trip():
    response = StreamingJSONListResponse(aiter_items([{"x": 1}, {"y": 2}]))
    body = run_coro(drain(response))
    assert json.loads(body) == [{"x": 1}, {"y": 2}]


def test_ndjson_with_complex_objects():
    response = NDJSONResponse(
        aiter_items([{"a": Decimal("1.1")}, {"b": [1, 2]}])
    )
    body = run_coro(drain(response))
    lines = body.strip().split("\n")
    assert json.loads(lines[0]) == {"a": "1.1"}
    assert json.loads(lines[1]) == {"b": [1, 2]}


def test_sse_with_dict_data_serializes_to_json():
    response = SSEResponse(aiter_items([{"data": {"k": "v"}}]))
    body = run_coro(drain(response))
    assert '"k"' in body
    assert '"v"' in body


def test_sse_response_emits_multiple_events_in_sequence():
    response = SSEResponse(aiter_items([
        {"event": "a", "data": "1"},
        {"event": "b", "data": "2"},
    ]))
    body = run_coro(drain(response))
    assert body.count("\n\n") == 2
    assert "event: a" in body
    assert "event: b" in body
