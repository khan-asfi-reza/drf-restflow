import asyncio

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

simplejwt = pytest.importorskip("rest_framework_simplejwt")

from rest_framework_simplejwt.tokens import (
    AccessToken as SimpleJWTAccessToken,
)

from restflow.authentication.simplejwt import (
    SimpleJWTAuthentication,
)


def _run(coro):
    return asyncio.run(coro)


def _make_request(token=None):
    factory = RequestFactory()
    extra = {}
    if token is not None:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return Request(factory.get("/", **extra))


@pytest.mark.django_db(transaction=True)
def test_simplejwt_adapter_returns_user_for_valid_token():
    User = get_user_model()
    user = User.objects.create_user(username="adapter", password="x", is_active=True)
    raw = str(SimpleJWTAccessToken.for_user(user))

    auth = SimpleJWTAuthentication()
    request = _make_request(token=raw)
    result = _run(auth.aauthenticate(request))
    assert result is not None
    assert result[0].pk == user.pk


def test_simplejwt_adapter_returns_none_without_header():
    auth = SimpleJWTAuthentication()
    assert _run(auth.aauthenticate(_make_request())) is None


def test_simplejwt_adapter_rejects_invalid_token():
    auth = SimpleJWTAuthentication()
    request = _make_request(token="garbage.not.token")
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_simplejwt_adapter_rejects_inactive_user():
    User = get_user_model()
    user = User.objects.create_user(
        username="adapter_inactive", password="x", is_active=False
    )
    raw = str(SimpleJWTAccessToken.for_user(user))

    auth = SimpleJWTAuthentication()
    request = _make_request(token=raw)
    with pytest.raises(AuthenticationFailed, match="inactive"):
        _run(auth.aauthenticate(request))


def test_simplejwt_adapter_returns_none_when_raw_token_missing(monkeypatch):
    auth = SimpleJWTAuthentication()
    monkeypatch.setattr(auth, "get_raw_token", lambda _header: None)
    request = _make_request(token="something")
    assert _run(auth.aauthenticate(request)) is None


@pytest.mark.django_db(transaction=True)
def test_simplejwtaget_user_resolves_active_user():
    User = get_user_model()
    user = User.objects.create_user(
        username="aget_active", password="x", is_active=True
    )
    auth = SimpleJWTAuthentication()
    result = _run(auth.aget_user({"user_id": user.pk}))
    assert result.pk == user.pk


def test_simplejwtaget_user_raises_when_claim_missing():
    auth = SimpleJWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="user identification"):
        _run(auth.aget_user({}))


@pytest.mark.django_db(transaction=True)
def test_simplejwtaget_user_raises_when_user_missing():
    auth = SimpleJWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="not found"):
        _run(auth.aget_user({"user_id": 999999}))


@pytest.mark.django_db(transaction=True)
def test_simplejwtaget_user_raises_when_user_inactive():
    User = get_user_model()
    user = User.objects.create_user(
        username="aget_inactive", password="x", is_active=False
    )
    auth = SimpleJWTAuthentication()
    with pytest.raises(AuthenticationFailed, match="inactive"):
        _run(auth.aget_user({"user_id": user.pk}))
