import asyncio
import itertools

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache as default_cache
from django.test import Client, override_settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.permissions import IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.throttling import (
    AnonRateThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)
from restflow.views import APIView, AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


class TightAnon(AnonRateThrottle):
    rate = "2/min"


class TightUser(UserRateThrottle):
    rate = "2/min"


class TightFixed(SimpleRateThrottle):
    rate = "2/min"
    scope = "fixed-bucket"

    def get_cache_key(self, request, view):
        return "throttle:fixed:matrix"


class TightScoped(ScopedRateThrottle):
    THROTTLE_RATES = {"matrix-scope": "2/min"}


THROTTLE_CHOICES = {
    "anon": TightAnon,
    "fixed": TightFixed,
}


THROTTLE_AUTH_CHOICES = {
    "user": TightUser,
}


SYNC_VIEW_REGISTRY = {}
ASYNC_VIEW_REGISTRY = {}


def make_sync_view(throttle_cls, anon=True):
    class _Sync(APIView):
        permission_classes = [AllowAny] if anon else [IsAuthenticated]
        throttle_classes = [throttle_cls]

        def get(self, request):
            return Response({"hit": True})

    return _Sync


def make_async_view(throttle_cls, anon=True):
    class _Async(AsyncAPIView):
        permission_classes = [AllowAny] if anon else [IsAuthenticated]
        throttle_classes = [throttle_cls]

        async def get(self, request):
            return Response({"hit": True})

    return _Async


urlpatterns = []


for slug, cls in THROTTLE_CHOICES.items():
    sync_view = make_sync_view(cls)
    async_view = make_async_view(cls)
    SYNC_VIEW_REGISTRY[slug] = sync_view
    ASYNC_VIEW_REGISTRY[slug] = async_view
    urlpatterns.append(path(f"sync/{slug}/", sync_view.as_view()))
    urlpatterns.append(path(f"async/{slug}/", async_view.as_view()))


for slug, cls in THROTTLE_AUTH_CHOICES.items():
    sync_view = make_sync_view(cls, anon=False)
    async_view = make_async_view(cls, anon=False)
    SYNC_VIEW_REGISTRY[slug] = sync_view
    ASYNC_VIEW_REGISTRY[slug] = async_view
    urlpatterns.append(path(f"sync/{slug}/", sync_view.as_view()))
    urlpatterns.append(path(f"async/{slug}/", async_view.as_view()))


class ScopedSync(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TightScoped]
    throttle_scope = "matrix-scope"

    def get(self, request):
        return Response({"hit": True})


class ScopedAsync(AsyncAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [TightScoped]
    throttle_scope = "matrix-scope"

    async def get(self, request):
        return Response({"hit": True})


urlpatterns.append(path("sync/scoped/", ScopedSync.as_view()))
urlpatterns.append(path("async/scoped/", ScopedAsync.as_view()))


CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "throttle-matrix",
    }
}


@pytest.fixture
def configured_urls():
    with override_settings(
        ROOT_URLCONF=__name__, CACHES=CACHES_OVERRIDE
    ):
        default_cache.clear()
        yield
        default_cache.clear()


@pytest.fixture
def regular_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="thr-user", password="x", is_active=True
    )


@pytest.mark.django_db(transaction=True)
class TestSyncThrottleMatrix:
    @pytest.mark.parametrize("slug", list(THROTTLE_CHOICES.keys()))
    def test_sync_under_limit(self, configured_urls, slug):
        for _ in range(2):
            response = Client().get(f"/sync/{slug}/")
            assert response.status_code == 200

    @pytest.mark.parametrize("slug", list(THROTTLE_CHOICES.keys()))
    def test_sync_over_limit_returns_429(self, configured_urls, slug):
        client = Client()
        for _ in range(2):
            client.get(f"/sync/{slug}/")
        response = client.get(f"/sync/{slug}/")
        assert response.status_code == 429

    def test_sync_user_throttle_segregates_users(
        self, configured_urls, db
    ):
        User = get_user_model()
        u1 = User.objects.create_user(
            username="u1", password="x", is_active=True
        )
        u2 = User.objects.create_user(
            username="u2", password="x", is_active=True
        )
        c1 = Client()
        c1.force_login(u1)
        c2 = Client()
        c2.force_login(u2)
        for _ in range(2):
            assert c1.get("/sync/user/").status_code == 200
        assert c1.get("/sync/user/").status_code == 429
        assert c2.get("/sync/user/").status_code == 200

    def test_sync_scoped_throttle(self, configured_urls):
        client = Client()
        assert client.get("/sync/scoped/").status_code == 200
        assert client.get("/sync/scoped/").status_code == 200
        assert client.get("/sync/scoped/").status_code == 429


@pytest.mark.django_db(transaction=True)
class TestAsyncThrottleMatrix:
    @pytest.mark.parametrize("slug", list(THROTTLE_CHOICES.keys()))
    def test_async_under_limit(self, configured_urls, slug):
        client = AsyncAPIClient()
        for _ in range(2):
            response = run_coro(client.get(f"/async/{slug}/"))
            assert response.status_code == 200

    @pytest.mark.parametrize("slug", list(THROTTLE_CHOICES.keys()))
    def test_async_over_limit_returns_429(self, configured_urls, slug):
        client = AsyncAPIClient()
        for _ in range(2):
            run_coro(client.get(f"/async/{slug}/"))
        response = run_coro(client.get(f"/async/{slug}/"))
        assert response.status_code == 429

    def test_async_user_throttle_segregates_users(
        self, configured_urls, db
    ):
        User = get_user_model()
        u1 = User.objects.create_user(
            username="u1", password="x", is_active=True
        )
        u2 = User.objects.create_user(
            username="u2", password="x", is_active=True
        )
        c1 = AsyncAPIClient()
        c1.force_authenticate(user=u1)
        c2 = AsyncAPIClient()
        c2.force_authenticate(user=u2)
        for _ in range(2):
            assert run_coro(c1.get("/async/user/")).status_code == 200
        assert run_coro(c1.get("/async/user/")).status_code == 429
        assert run_coro(c2.get("/async/user/")).status_code == 200

