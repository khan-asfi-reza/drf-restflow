import asyncio

import pytest
from django.core.cache import cache as default_cache
from django.test import Client, override_settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.caching import (
    ArgsKeyField,
    ConstantKeyField,
    QueryParamsKeyField,
    cache_result,
)
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


HIT_COUNTER = {"sync": 0, "async": 0, "qp": 0}


@cache_result(
    key_constructor={
        "fields": {"args": ArgsKeyField("*")},
        "namespace": "view-sync",
    },
    ttl=300,
)
def expensive_sync(seed):
    HIT_COUNTER["sync"] += 1
    return {"value": seed * 2}


@cache_result(
    key_constructor={
        "fields": {"args": ArgsKeyField("*")},
        "namespace": "view-async",
    },
    ttl=300,
)
async def expensive_async(seed):
    HIT_COUNTER["async"] += 1
    return {"value": seed * 3}


@cache_result(
    key_constructor={
        "fields": {"qp": QueryParamsKeyField(["q"])},
        "namespace": "view-qp",
    },
    ttl=300,
)
async def by_query(request):
    HIT_COUNTER["qp"] += 1
    return {"q": request.query_params.get("q", "")}


class SyncCachedView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        seed = int(request.query_params.get("seed", 1))
        return Response(expensive_sync(seed))


class AsyncCachedView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        seed = int(request.query_params.get("seed", 1))
        return Response(await expensive_async(seed))


class QueryCachedView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        return Response(await by_query(request))

class CacheResponseAsyncView(AsyncAPIView):
    permission_classes = [AllowAny]

    @cache_result(key_constructor={"fields": {"key": ConstantKeyField(key="a", value="b")}})
    async def get(self, request):
        HIT_COUNTER["async"] += 1
        return Response({"value": 10})

class CacheResponseViewSync(AsyncAPIView):
    permission_classes = [AllowAny]

    @cache_result(key_constructor={"fields": {"key": ConstantKeyField(key="a", value="b")}})
    def get(self, request):
        HIT_COUNTER["sync"] += 1
        return Response({"value": 10})


urlpatterns = [
    path("sync-cached/", SyncCachedView.as_view()),
    path("async-cached/", AsyncCachedView.as_view()),
    path("by-query/", QueryCachedView.as_view()),
    path("async-response/", CacheResponseAsyncView.as_view()),
    path("sync-response/", CacheResponseViewSync.as_view()),
]


CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "caching-flow",
    }
}


@pytest.fixture
def configured_urls():
    with override_settings(
        ROOT_URLCONF=__name__, CACHES=CACHES_OVERRIDE
    ):
        default_cache.clear()
        for k in HIT_COUNTER:
            HIT_COUNTER[k] = 0
        yield
        default_cache.clear()

def test_sync_response_cache_view(configured_urls):
    client = Client()
    first = client.get("/sync-response/").json()
    second = client.get("/sync-response/").json()
    assert first == second == {"value": 10}
    assert HIT_COUNTER["sync"] == 1

def test_async_response_cache_view(configured_urls):
    client = Client()
    first = client.get("/async-response/").json()
    second = client.get("/async-response/").json()
    assert first == second == {"value": 10}
    assert HIT_COUNTER["async"] == 1


def test_sync_view_caches_repeat_calls(configured_urls):
    client = Client()
    first = client.get("/sync-cached/?seed=5").json()
    second = client.get("/sync-cached/?seed=5").json()
    assert first == second == {"value": 10}
    assert HIT_COUNTER["sync"] == 1


def test_sync_view_distinguishes_seeds(configured_urls):
    client = Client()
    client.get("/sync-cached/?seed=1")
    client.get("/sync-cached/?seed=2")
    client.get("/sync-cached/?seed=1")
    assert HIT_COUNTER["sync"] == 2


def test_async_view_caches_repeat_calls(configured_urls):
    client = AsyncAPIClient()
    first = run_coro(client.get("/async-cached/?seed=4")).json()
    second = run_coro(client.get("/async-cached/?seed=4")).json()
    assert first == second == {"value": 12}
    assert HIT_COUNTER["async"] == 1


def test_async_view_distinguishes_seeds(configured_urls):
    client = AsyncAPIClient()
    run_coro(client.get("/async-cached/?seed=1"))
    run_coro(client.get("/async-cached/?seed=3"))
    run_coro(client.get("/async-cached/?seed=1"))
    assert HIT_COUNTER["async"] == 2


def test_query_param_key_field_distinguishes_payloads(configured_urls):
    client = AsyncAPIClient()
    a1 = run_coro(client.get("/by-query/?q=apple")).json()
    a2 = run_coro(client.get("/by-query/?q=apple")).json()
    b = run_coro(client.get("/by-query/?q=banana")).json()
    assert a1 == a2 == {"q": "apple"}
    assert b == {"q": "banana"}
    assert HIT_COUNTER["qp"] == 2


def test_unrelated_query_params_share_cache_entry(configured_urls):
    client = AsyncAPIClient()
    run_coro(client.get("/by-query/?q=apple&extra=1"))
    run_coro(client.get("/by-query/?q=apple&extra=2"))
    assert HIT_COUNTER["qp"] == 1


def test_delete_cache_drops_single_entry(configured_urls):
    client = Client()
    client.get("/sync-cached/?seed=7")
    expensive_sync.delete_cache(7)
    client.get("/sync-cached/?seed=7")
    assert HIT_COUNTER["sync"] == 2


def test_refresh_recomputes_and_caches(configured_urls):
    client = Client()
    client.get("/sync-cached/?seed=8")
    expensive_sync.refresh(8)
    client.get("/sync-cached/?seed=8")
    assert HIT_COUNTER["sync"] == 2


def test_bypass_cache_skips_cache_entirely(configured_urls):
    Client().get("/sync-cached/?seed=9")
    expensive_sync.bypass_cache(9)
    expensive_sync.bypass_cache(9)
    assert HIT_COUNTER["sync"] == 3
