import asyncio
import inspect

from django.test import RequestFactory
from rest_framework.response import Response

from restflow.views import AsyncAPIView


def _run(coro):
    return asyncio.run(coro)


def _make_request(method="get", path="/"):
    factory = RequestFactory()
    return getattr(factory, method)(path)


def test_async_apiview_view_is_async_is_true():
    assert AsyncAPIView.view_is_async is True


def test_async_apiview_subclass_is_async():
    class MyView(AsyncAPIView):
        async def get(self, request, *args, **kwargs):
            return Response({"ok": True})

    assert MyView.view_is_async is True


def test_async_apiview_dispatch_is_coroutine():
    assert inspect.iscoroutinefunction(AsyncAPIView.dispatch)


def test_as_view_returns_coroutine_function():
    class MyView(AsyncAPIView):
        async def get(self, request, *args, **kwargs):
            return Response({"ok": True})

    view = MyView.as_view()
    raw = _make_request()
    result = view(raw)
    assert asyncio.iscoroutine(result)
    response = _run(_drive(result))
    assert response.status_code == 200


async def _drive(coro):
    return await coro


def test_dispatch_calls_async_handler():
    seen = {}

    class MyView(AsyncAPIView):
        async def get(self, request, *args, **kwargs):
            seen["called"] = True
            return Response({"ok": True})

    view = MyView.as_view()
    _run(_drive(view(_make_request())))
    assert seen["called"] is True


def test_dispatch_calls_sync_handler_via_maybe_await():
    seen = {}

    class MyView(AsyncAPIView):
        def get(self, request, *args, **kwargs):
            seen["called"] = True
            return Response({"ok": True})

    view = MyView.as_view()
    response = _run(_drive(view(_make_request())))
    assert seen["called"] is True
    assert response.status_code == 200


def test_handle_exception_async_path():
    from rest_framework import exceptions

    class MyView(AsyncAPIView):
        async def get(self, request, *args, **kwargs):
            raise exceptions.NotFound()

    view = MyView.as_view()
    response = _run(_drive(view(_make_request())))
    assert response.status_code == 404
