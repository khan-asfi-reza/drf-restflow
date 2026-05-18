import asyncio
import base64
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import path
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.authentication import (
    AccessToken,
    BasicAuthentication,
    JWTAuthentication,
    TokenAuthentication,
)
from restflow.permissions import IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView


def run_coro(coro):
    return asyncio.run(coro)


JWT_OVERRIDES = {
    "RESTFLOW_SETTINGS": {
        "JWT": {
            "SIGNING_KEY": "test-signing-key-test-signing-key-32-chars",
            "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
            "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
            "BLACKLIST_ENABLED": True,
            "BLACKLIST_ALLOW_LOCMEM": True,
        }
    }
}


def make_sync_view(auth_classes):
    class _SyncProtected(APIView):
        permission_classes = [IsAuthenticated]
        authentication_classes = auth_classes

        def get(self, request):
            return Response({"user": str(request.user.username)})

    return _SyncProtected


def make_async_view(auth_classes):
    class _AsyncProtected(AsyncAPIView):
        permission_classes = [IsAuthenticated]
        authentication_classes = auth_classes

        async def get(self, request):
            return Response({"user": str(request.user.username)})

    return _AsyncProtected


SyncJWTView = make_sync_view([JWTAuthentication])
SyncBasicView = make_sync_view([BasicAuthentication])
SyncTokenView = make_sync_view([TokenAuthentication])
SyncMultiView = make_sync_view(
    [BasicAuthentication, TokenAuthentication, JWTAuthentication]
)

AsyncJWTView = make_async_view([JWTAuthentication])
AsyncBasicView = make_async_view([BasicAuthentication])
AsyncTokenView = make_async_view([TokenAuthentication])
AsyncMultiView = make_async_view(
    [BasicAuthentication, TokenAuthentication, JWTAuthentication]
)


urlpatterns = [
    path("sync/jwt/", SyncJWTView.as_view()),
    path("sync/basic/", SyncBasicView.as_view()),
    path("sync/token/", SyncTokenView.as_view()),
    path("sync/multi/", SyncMultiView.as_view()),
    path("async/jwt/", AsyncJWTView.as_view()),
    path("async/basic/", AsyncBasicView.as_view()),
    path("async/token/", AsyncTokenView.as_view()),
    path("async/multi/", AsyncMultiView.as_view()),
]


@pytest.fixture
def configured_urls():
    with override_settings(ROOT_URLCONF=__name__, **JWT_OVERRIDES):
        yield


@pytest.fixture
def real_user(db):
    User = get_user_model()
    return User.objects.create_user(
        username="auth-user", password="auth-pass", is_active=True
    )


@pytest.fixture
def real_token(real_user):
    return Token.objects.create(user=real_user)


def jwt_header(user):
    return f"Bearer {AccessToken.for_user(user)}"


def basic_header(username, password):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {creds}"


def token_header(token):
    return f"Token {token.key}"


@pytest.mark.django_db(transaction=True)
class TestSyncAuthenticationMatrix:
    def test_sync_jwt_no_header_returns_401(self, configured_urls):
        response = Client().get("/sync/jwt/")
        assert response.status_code == 401

    def test_sync_jwt_valid_token(self, configured_urls, real_user):
        response = Client().get(
            "/sync/jwt/", HTTP_AUTHORIZATION=jwt_header(real_user)
        )
        assert response.status_code == 200
        assert response.json()["user"] == "auth-user"

    def test_sync_jwt_invalid_token(self, configured_urls):
        response = Client().get(
            "/sync/jwt/", HTTP_AUTHORIZATION="Bearer junk.token.value"
        )
        assert response.status_code == 401

    def test_sync_basic_no_header_returns_401(self, configured_urls):
        response = Client().get("/sync/basic/")
        assert response.status_code == 401

    def test_sync_basic_valid_credentials(self, configured_urls, real_user):
        response = Client().get(
            "/sync/basic/",
            HTTP_AUTHORIZATION=basic_header("auth-user", "auth-pass"),
        )
        assert response.status_code == 200

    def test_sync_basic_wrong_password(self, configured_urls, real_user):
        response = Client().get(
            "/sync/basic/",
            HTTP_AUTHORIZATION=basic_header("auth-user", "wrong"),
        )
        assert response.status_code == 401

    def test_sync_token_no_header_returns_401(self, configured_urls):
        response = Client().get("/sync/token/")
        assert response.status_code == 401

    def test_sync_token_valid(self, configured_urls, real_token):
        response = Client().get(
            "/sync/token/", HTTP_AUTHORIZATION=token_header(real_token)
        )
        assert response.status_code == 200

    def test_sync_token_unknown(self, configured_urls):
        response = Client().get(
            "/sync/token/", HTTP_AUTHORIZATION="Token unknown-key"
        )
        assert response.status_code == 401

    def test_sync_multi_authenticator_basic_works(
        self, configured_urls, real_user
    ):
        response = Client().get(
            "/sync/multi/",
            HTTP_AUTHORIZATION=basic_header("auth-user", "auth-pass"),
        )
        assert response.status_code == 200

    def test_sync_multi_authenticator_jwt_works(
        self, configured_urls, real_user
    ):
        response = Client().get(
            "/sync/multi/", HTTP_AUTHORIZATION=jwt_header(real_user)
        )
        assert response.status_code == 200

    def test_sync_multi_authenticator_token_works(
        self, configured_urls, real_token
    ):
        response = Client().get(
            "/sync/multi/", HTTP_AUTHORIZATION=token_header(real_token)
        )
        assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
class TestAsyncAuthenticationMatrix:
    def test_async_jwt_no_header_returns_401(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async/jwt/"))
        assert response.status_code == 401

    def test_async_jwt_valid_token(self, configured_urls, real_user):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION=jwt_header(real_user))
        response = run_coro(client.get("/async/jwt/"))
        assert response.status_code == 200
        assert response.json()["user"] == "auth-user"

    def test_async_jwt_invalid_token(self, configured_urls):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer junk.token.value")
        response = run_coro(client.get("/async/jwt/"))
        assert response.status_code == 401

    def test_async_basic_no_header_returns_401(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async/basic/"))
        assert response.status_code == 401

    def test_async_basic_valid_credentials(self, configured_urls, real_user):
        client = AsyncAPIClient()
        client.credentials(
            HTTP_AUTHORIZATION=basic_header("auth-user", "auth-pass")
        )
        response = run_coro(client.get("/async/basic/"))
        assert response.status_code == 200

    def test_async_basic_wrong_password(self, configured_urls, real_user):
        client = AsyncAPIClient()
        client.credentials(
            HTTP_AUTHORIZATION=basic_header("auth-user", "wrong")
        )
        response = run_coro(client.get("/async/basic/"))
        assert response.status_code == 401

    def test_async_token_no_header_returns_401(self, configured_urls):
        response = run_coro(AsyncAPIClient().get("/async/token/"))
        assert response.status_code == 401

    def test_async_token_valid(self, configured_urls, real_token):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION=token_header(real_token))
        response = run_coro(client.get("/async/token/"))
        assert response.status_code == 200

    def test_async_multi_authenticator_basic_works(
        self, configured_urls, real_user
    ):
        client = AsyncAPIClient()
        client.credentials(
            HTTP_AUTHORIZATION=basic_header("auth-user", "auth-pass")
        )
        response = run_coro(client.get("/async/multi/"))
        assert response.status_code == 200

    def test_async_multi_authenticator_jwt_works(
        self, configured_urls, real_user
    ):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION=jwt_header(real_user))
        response = run_coro(client.get("/async/multi/"))
        assert response.status_code == 200

    def test_async_multi_authenticator_token_works(
        self, configured_urls, real_token
    ):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION=token_header(real_token))
        response = run_coro(client.get("/async/multi/"))
        assert response.status_code == 200

    def test_async_unrelated_scheme_returns_401(self, configured_urls):
        client = AsyncAPIClient()
        client.credentials(HTTP_AUTHORIZATION="OAuth some-token")
        response = run_coro(client.get("/async/multi/"))
        assert response.status_code == 401
