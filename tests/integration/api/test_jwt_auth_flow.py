import asyncio
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import path
from rest_framework.response import Response

from restflow.authentication import JWTAuthentication
from restflow.authentication.jwt_views import (
    TokenBlacklistView,
    TokenObtainView,
    TokenRefreshView,
)
from restflow.permissions import IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.views import AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


class WhoAmIView(AsyncAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"username": request.user.username})


urlpatterns = [
    path("auth/obtain/", TokenObtainView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/blacklist/", TokenBlacklistView.as_view()),
    path("whoami/", WhoAmIView.as_view()),
]


JWT_OVERRIDES = {
    "RESTFLOW_SETTINGS": {
        "JWT": {
            "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
            "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
            "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
            "BLACKLIST_ENABLED": True,
            "BLACKLIST_ALLOW_LOCMEM": True,
            "ROTATE_REFRESH_TOKENS": False,
        }
    }
}


JWT_ROTATE_OVERRIDES = {
    "RESTFLOW_SETTINGS": {
        "JWT": {
            "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
            "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
            "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
            "BLACKLIST_ENABLED": True,
            "BLACKLIST_ALLOW_LOCMEM": True,
            "ROTATE_REFRESH_TOKENS": True,
        }
    }
}


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__, **JWT_OVERRIDES):
        yield


@pytest.fixture
def configured_urls_with_rotation():
    with override_settings(ROOT_URLCONF=__name__, **JWT_ROTATE_OVERRIDES):
        yield


@pytest.fixture
def created_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="carol", password="carol-pass-1", is_active=True
    )


@pytest.mark.django_db(transaction=True)
class TestObtainTokens:
    def test_obtain_with_valid_credentials_returns_pair(
        self, configured_urls, created_user
    ):
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        body = response.json()
        assert response.status_code == 200
        assert "access" in body
        assert "refresh" in body

    def test_obtain_with_wrong_password_returns_401(
        self, configured_urls, created_user
    ):
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/obtain/",
                data={"username": "carol", "password": "wrong"},
                format="json",
            )
        )
        assert response.status_code == 401

    def test_obtain_with_unknown_user_returns_401(
        self, configured_urls
    ):
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/obtain/",
                data={"username": "ghost", "password": "x"},
                format="json",
            )
        )
        assert response.status_code == 401

    def test_obtain_with_inactive_user_returns_401(
        self, configured_urls, db
    ):
        User = get_user_model()
        User.objects.create_user(
            username="dave", password="d", is_active=False
        )
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/obtain/",
                data={"username": "dave", "password": "d"},
                format="json",
            )
        )
        assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
class TestUseAccessToken:
    def test_access_token_grants_access_to_protected_view(
        self, configured_urls, created_user
    ):
        client = AsyncAPIClient()
        obtain = run_coro(
            client.post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        access = obtain.json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = run_coro(client.get("/whoami/"))
        assert response.status_code == 200
        assert response.json()["username"] == "carol"

    def test_access_without_header_returns_401(
        self, configured_urls
    ):
        response = run_coro(AsyncAPIClient().get("/whoami/"))
        assert response.status_code == 401

    def test_garbage_token_returns_401(self, configured_urls):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer garbage.token.value")
        response = run_coro(client.get("/whoami/"))
        assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
class TestRefreshFlow:
    def test_refresh_returns_new_access(
        self, configured_urls, created_user
    ):
        client = AsyncAPIClient()
        obtain = run_coro(
            client.post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        refresh = obtain.json()["refresh"]
        response = run_coro(
            client.post(
                "/auth/refresh/",
                data={"refresh": refresh},
                format="json",
            )
        )
        body = response.json()
        assert response.status_code == 200
        assert "access" in body
        assert "refresh" not in body

    def test_refresh_with_rotation_returns_new_pair(
        self, configured_urls_with_rotation, created_user
    ):
        client = AsyncAPIClient()
        obtain = run_coro(
            client.post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        refresh = obtain.json()["refresh"]
        response = run_coro(
            client.post(
                "/auth/refresh/",
                data={"refresh": refresh},
                format="json",
            )
        )
        body = response.json()
        assert response.status_code == 200
        assert "access" in body
        assert "refresh" in body
        assert body["refresh"] != refresh

    def test_refresh_with_blacklisted_token_returns_401(
        self, configured_urls, created_user
    ):
        client = AsyncAPIClient()
        obtain = run_coro(
            client.post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        refresh = obtain.json()["refresh"]
        run_coro(
            client.post(
                "/auth/blacklist/",
                data={"refresh": refresh},
                format="json",
            )
        )
        response = run_coro(
            client.post(
                "/auth/refresh/",
                data={"refresh": refresh},
                format="json",
            )
        )
        assert response.status_code == 401

    def test_refresh_with_garbage_returns_401(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/refresh/",
                data={"refresh": "garbage"},
                format="json",
            )
        )
        assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
class TestBlacklistFlow:
    def test_blacklist_returns_204(self, configured_urls, created_user):
        client = AsyncAPIClient()
        obtain = run_coro(
            client.post(
                "/auth/obtain/",
                data={"username": "carol", "password": "carol-pass-1"},
                format="json",
            )
        )
        refresh = obtain.json()["refresh"]
        response = run_coro(
            client.post(
                "/auth/blacklist/",
                data={"refresh": refresh},
                format="json",
            )
        )
        assert response.status_code == 204

    def test_blacklist_garbage_returns_401(self, configured_urls):
        response = run_coro(
            AsyncAPIClient().post(
                "/auth/blacklist/",
                data={"refresh": "garbage"},
                format="json",
            )
        )
        assert response.status_code == 401
