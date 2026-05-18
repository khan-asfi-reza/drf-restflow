import asyncio
import json

from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)


def _run(coro):
    return asyncio.run(coro)


async def _iter(items):
    for item in items:
        yield item


async def _drain(response):
    out = []
    async for chunk in response.streaming_content:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        out.append(text)
    return "".join(out)


def test_streaming_json_list_response_assembles_array():
    response = StreamingJSONListResponse(_iter([{"a": 1}, {"b": 2}, {"c": 3}]))
    body = _run(_drain(response))
    parsed = json.loads(body)
    assert parsed == [{"a": 1}, {"b": 2}, {"c": 3}]


def test_streaming_json_list_response_handles_empty():
    response = StreamingJSONListResponse(_iter([]))
    body = _run(_drain(response))
    assert json.loads(body) == []


def test_streaming_json_list_response_handles_single_item():
    response = StreamingJSONListResponse(_iter([{"x": 1}]))
    body = _run(_drain(response))
    assert json.loads(body) == [{"x": 1}]


def test_streaming_json_list_response_content_type():
    response = StreamingJSONListResponse(_iter([]))
    assert response["Content-Type"].startswith("application/json")


def test_ndjson_response_one_object_per_line():
    response = NDJSONResponse(_iter([{"a": 1}, {"b": 2}]))
    body = _run(_drain(response))
    lines = body.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}


def test_ndjson_response_content_type():
    response = NDJSONResponse(_iter([]))
    assert response["Content-Type"] == "application/x-ndjson"


def test_sse_response_string_event():
    response = SSEResponse(_iter(["hello", "world"]))
    body = _run(_drain(response))
    assert body == "data: hello\n\ndata: world\n\n"


def test_sse_response_dict_event_with_all_fields():
    response = SSEResponse(_iter([
        {"id": "42", "event": "ping", "retry": 5000, "data": {"ok": True}},
    ]))
    body = _run(_drain(response))
    assert "id: 42" in body
    assert "event: ping" in body
    assert "retry: 5000" in body
    assert 'data: {"ok": true}' in body
    assert body.endswith("\n\n")


def test_sse_response_dict_event_with_string_data():
    response = SSEResponse(_iter([{"event": "tick", "data": "now"}]))
    body = _run(_drain(response))
    assert "event: tick" in body
    assert "data: now" in body


def test_sse_response_handles_multiline_data():
    response = SSEResponse(_iter([{"data": "line1\nline2\nline3"}]))
    body = _run(_drain(response))
    assert "data: line1" in body
    assert "data: line2" in body
    assert "data: line3" in body


def test_sse_response_sets_buffering_headers():
    response = SSEResponse(_iter([]))
    assert response["Cache-Control"] == "no-cache"
    assert response["X-Accel-Buffering"] == "no"
    assert response["Content-Type"] == "text/event-stream"


def test_sse_response_rejects_newline_in_id():
    import pytest

    async def gen():
        yield {"id": "evt\n1", "data": "x"}

    response = SSEResponse(gen())
    with pytest.raises(ValueError, match="must not contain"):
        _run(_drain(response))


def test_sse_response_rejects_newline_in_event():
    import pytest

    async def gen():
        yield {"event": "tick\nlogout", "data": "x"}

    response = SSEResponse(gen())
    with pytest.raises(ValueError, match="must not contain"):
        _run(_drain(response))


def test_sse_response_rejects_carriage_return_in_id():
    import pytest

    async def gen():
        yield {"id": "evt\r1", "data": "x"}

    response = SSEResponse(gen())
    with pytest.raises(ValueError, match="must not contain"):
        _run(_drain(response))


def test_sse_response_normalizes_crlf_in_data():
    response = SSEResponse(_iter([{"data": "line1\r\nline2\rline3\nline4"}]))
    body = _run(_drain(response))
    assert "data: line1" in body
    assert "data: line2" in body
    assert "data: line3" in body
    assert "data: line4" in body


def test_streaming_json_list_response_closes_bracket_on_iter_error():
    import pytest

    async def gen():
        yield {"a": 1}
        msg = "boom"
        raise RuntimeError(msg)

    response = StreamingJSONListResponse(gen())
    with pytest.raises(RuntimeError, match="boom"):
        _run(_drain(response))
