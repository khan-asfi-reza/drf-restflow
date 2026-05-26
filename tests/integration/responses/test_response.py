import asyncio
import json

import pytest
from rest_framework.renderers import JSONRenderer

from restflow.responses import Response


def _run(coro):
    return asyncio.run(coro)


def _make_response(data):
    response = Response(data)
    response.accepted_renderer = JSONRenderer()
    response.accepted_media_type = "application/json"
    response.renderer_context = {}
    return response


def test_arender_renders_content_and_sets_is_rendered():
    response = _make_response({"x": 1})
    result = _run(response.arender())
    assert result is response
    assert response.is_rendered is True
    assert json.loads(response.content) == {"x": 1}


def test_arender_runs_sync_and_async_callbacks_in_registration_order():
    response = _make_response({"x": 1})
    order = []

    def cb_sync(resp):
        order.append("sync")

    async def cb_async(resp):
        order.append("async")

    response.add_post_render_callback(cb_sync)
    response.add_post_render_callback(cb_async)

    _run(response.arender())

    assert order == ["sync", "async"]


def test_arender_awaits_async_callback():
    response = _make_response({"x": 1})
    flag = {"awaited": False}

    async def cb_async(resp):
        await asyncio.sleep(0)
        flag["awaited"] = True

    response.add_post_render_callback(cb_async)

    _run(response.arender())

    assert flag["awaited"] is True


def test_arender_callback_can_replace_retval():
    response = _make_response({"x": 1})
    replacement = _make_response({"y": 2})

    async def cb_async(resp):
        return replacement

    response.add_post_render_callback(cb_async)

    result = _run(response.arender())

    assert result is replacement


def test_arender_is_idempotent():
    response = _make_response({"x": 1})
    calls = []

    async def cb(resp):
        calls.append(resp)

    response.add_post_render_callback(cb)

    _run(response.arender())
    _run(response.arender())

    assert len(calls) == 1


def test_sync_render_still_works_with_sync_callback():
    response = _make_response({"x": 1})
    fired = {"called": False}

    def cb(resp):
        fired["called"] = True

    response.add_post_render_callback(cb)
    response.render()

    assert fired["called"] is True
    assert response.is_rendered is True
    assert json.loads(response.content) == {"x": 1}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
