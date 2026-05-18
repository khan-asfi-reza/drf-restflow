import asyncio

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache as default_cache
from django.test import override_settings
from django.urls import path
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.permissions import IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)
from restflow.views import APIView, AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


class TightAnon(AnonRateThrottle):
    rate = "2/min"


class TightUser(UserRateThrottle):
    rate = "3/min"


class GreetingView(AsyncAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [TightAnon]

    async def get(self, request):
        return Response({"hello": True})


class UserScopedView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [TightUser]

    async def get(self, request):
        return Response({"user": str(request.user.username)})


class FixedKeyThrottle(SimpleRateThrottle):
    rate = "2/min"
    scope = "fixed-key"

    def get_cache_key(self, request, view):
        return "throttle:fixed:flow"


class FixedKeyView(AsyncAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [FixedKeyThrottle]

    async def get(self, request):
        return Response({"ok": True})


class SyncFixedKeyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [FixedKeyThrottle]

    def get(self, request):
        return Response({"sync": True})


urlpatterns = [
    path("greet/", GreetingView.as_view()),
    path("scoped/", UserScopedView.as_view()),
    path("fixed/", FixedKeyView.as_view()),
    path("sync-fixed/", SyncFixedKeyView.as_view()),
]


CACHES_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "throttle-flow",
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
def authed_user(db):
    User = get_user_model()
    user = User.objects.create_user(
        username="ed", password="pwd", is_active=True
    )
    return user


@pytest.mark.django_db(transaction=True)
class TestAnonThrottle:
    def test_under_limit_passes(self, configured_urls):
        client = AsyncAPIClient()
        for _ in range(2):
            response = run_coro(client.get("/greet/"))
            assert response.status_code == 200

    def test_over_limit_returns_429(self, configured_urls):
        client = AsyncAPIClient()
        for _ in range(2):
            run_coro(client.get("/greet/"))
        response = run_coro(client.get("/greet/"))
        assert response.status_code == 429

    def test_response_has_retry_after_header(self, configured_urls):
        client = AsyncAPIClient()
        for _ in range(2):
            run_coro(client.get("/greet/"))
        response = run_coro(client.get("/greet/"))
        assert "retry-after" in {h.lower() for h in response.headers.keys()}


@pytest.mark.django_db(transaction=True)
class TestUserThrottle:
    def test_authenticated_within_limit(
        self, configured_urls, authed_user
    ):
        client = AsyncAPIClient()
        client.force_authenticate(user=authed_user)
        for _ in range(3):
            response = run_coro(client.get("/scoped/"))
            assert response.status_code == 200

    def test_authenticated_over_limit_returns_429(
        self, configured_urls, authed_user
    ):
        client = AsyncAPIClient()
        client.force_authenticate(user=authed_user)
        for _ in range(3):
            run_coro(client.get("/scoped/"))
        response = run_coro(client.get("/scoped/"))
        assert response.status_code == 429

    def test_separate_users_have_separate_buckets(
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
        for _ in range(3):
            assert run_coro(c1.get("/scoped/")).status_code == 200
        assert run_coro(c1.get("/scoped/")).status_code == 429
        assert run_coro(c2.get("/scoped/")).status_code == 200


@pytest.mark.django_db(transaction=True)
class TestFixedKeyThrottle:
    def test_async_path_round_trip(self, configured_urls):
        client = AsyncAPIClient()
        assert run_coro(client.get("/fixed/")).status_code == 200
        assert run_coro(client.get("/fixed/")).status_code == 200
        assert run_coro(client.get("/fixed/")).status_code == 429

    def test_sync_path_round_trip(self, configured_urls):
        from django.test import Client

        client = Client()
        assert client.get("/sync-fixed/").status_code == 200
        assert client.get("/sync-fixed/").status_code == 200
        assert client.get("/sync-fixed/").status_code == 429
