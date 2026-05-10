import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from restflow.authentication import (
    BaseAuthentication,
    BasicAuthentication,
    RemoteUserAuthentication,
    SessionAuthentication,
    TokenAuthentication,
)


def _run(coro):
    return asyncio.run(coro)


def _make_request(headers=None):
    factory = RequestFactory()
    extras = headers or {}
    return Request(factory.get("/", **extras))


def _stub_token_model(token=None, raise_does_not_exist=False):
    model = MagicMock()
    model.DoesNotExist = type("DoesNotExist", (Exception,), {})

    qs = MagicMock()
    if raise_does_not_exist:
        qs.aget = AsyncMock(side_effect=model.DoesNotExist())
    else:
        qs.aget = AsyncMock(return_value=token)

    model.objects.select_related = MagicMock(return_value=qs)
    return model


def _user(active=True):
    user = MagicMock()
    user.is_active = active
    return user


def test_token_aauthenticate_returns_user_for_valid_token():
    user = _user()
    token = MagicMock(user=user)
    auth = TokenAuthentication()
    auth.model = _stub_token_model(token=token)

    request = _make_request({"HTTP_AUTHORIZATION": "Token deadbeef"})
    result = _run(auth.aauthenticate(request))

    assert result == (user, token)


def test_token_aauthenticate_raises_for_invalid_token():
    auth = TokenAuthentication()
    auth.model = _stub_token_model(raise_does_not_exist=True)

    request = _make_request({"HTTP_AUTHORIZATION": "Token notreal"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_token_aauthenticate_raises_for_inactive_user():
    user = _user(active=False)
    token = MagicMock(user=user)
    auth = TokenAuthentication()
    auth.model = _stub_token_model(token=token)

    request = _make_request({"HTTP_AUTHORIZATION": "Token x"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_token_aauthenticate_returns_none_without_header():
    auth = TokenAuthentication()
    assert _run(auth.aauthenticate(_make_request())) is None


def test_token_aauthenticate_raises_on_empty_token():
    auth = TokenAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": "Token"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_token_aauthenticate_raises_on_extra_token_parts():
    auth = TokenAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": "Token a b"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_basic_aauthenticate_returns_none_without_basic_prefix():
    request = _make_request({"HTTP_AUTHORIZATION": "Token abc"})
    auth = BasicAuthentication()
    assert _run(auth.aauthenticate(request)) is None


def test_basic_aauthenticate_raises_on_malformed_credentials():
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": "Basic !!!"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_basic_aauthenticate_returns_none_for_empty_basic():
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": "Basic"})
    with pytest.raises(AuthenticationFailed):
        _run(auth.aauthenticate(request))


def test_session_aauthenticate_returns_none_for_anonymous():
    factory = RequestFactory()
    raw = factory.get("/")
    raw.user = None
    request = Request(raw)
    auth = SessionAuthentication()
    assert _run(auth.aauthenticate(request)) is None


def test_session_aauthenticate_returns_user_when_logged_in():
    user = _user()
    factory = RequestFactory()
    raw = factory.get("/")
    raw.user = user
    request = Request(raw)
    auth = SessionAuthentication()
    auth.enforce_csrf = MagicMock()
    result = _run(auth.aauthenticate(request))
    assert result == (user, None)


def test_base_aauthenticate_falls_back_to_sync_authenticate():
    class CustomSync(BaseAuthentication):
        def authenticate(self, request):
            return ("sync-user", "sync-token")

    request = _make_request()
    result = _run(CustomSync().aauthenticate(request))
    assert result == ("sync-user", "sync-token")


def test_basic_aauthenticate_raises_when_credentials_have_spaces():
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": "Basic abc def"})
    with pytest.raises(AuthenticationFailed, match="should not contain spaces"):
        _run(auth.aauthenticate(request))


def test_basic_aauthenticate_falls_back_to_latin1(monkeypatch):
    raw = "us\xe9r:pw"
    encoded = base64.b64encode(raw.encode("latin-1")).decode("ascii")

    captured = {}

    async def fake_aauth(self, userid, password, request=None):
        captured["userid"] = userid
        captured["password"] = password
        return ("ok-user", None)

    monkeypatch.setattr(
        BasicAuthentication, "aauthenticate_credentials", fake_aauth
    )

    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": f"Basic {encoded}"})
    result = _run(auth.aauthenticate(request))

    assert result == ("ok-user", None)
    assert captured["userid"] == "us\xe9r"
    assert captured["password"] == "pw"


def test_basic_aauthenticate_credentials_returns_user(monkeypatch):
    user = _user(active=True)

    async def fake_django_auth(request=None, **credentials):
        return user

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    encoded = base64.b64encode(b"khan:secret").decode("ascii")
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": f"Basic {encoded}"})
    result = _run(auth.aauthenticate(request))
    assert result == (user, None)


def test_basic_aauthenticate_credentials_invalid_raises(monkeypatch):
    async def fake_django_auth(request=None, **credentials):
        return None

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    encoded = base64.b64encode(b"khan:wrong").decode("ascii")
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": f"Basic {encoded}"})
    with pytest.raises(AuthenticationFailed, match="Invalid username/password"):
        _run(auth.aauthenticate(request))


def test_basic_aauthenticate_credentials_inactive_raises(monkeypatch):
    user = _user(active=False)

    async def fake_django_auth(request=None, **credentials):
        return user

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    encoded = base64.b64encode(b"khan:secret").decode("ascii")
    auth = BasicAuthentication()
    request = _make_request({"HTTP_AUTHORIZATION": f"Basic {encoded}"})
    with pytest.raises(AuthenticationFailed, match="inactive"):
        _run(auth.aauthenticate(request))


def test_session_aauthenticate_uses_callable_auser():
    user = _user(active=True)
    factory = RequestFactory()
    raw = factory.get("/")
    raw.user = None

    async def fake_auser():
        return user

    raw.auser = fake_auser
    request = Request(raw)
    auth = SessionAuthentication()
    auth.enforce_csrf = MagicMock()
    result = _run(auth.aauthenticate(request))
    assert result == (user, None)


def test_token_aauthenticate_raises_on_invalid_unicode():
    auth = TokenAuthentication()
    factory = RequestFactory()
    raw = factory.get("/")
    raw.META["HTTP_AUTHORIZATION"] = b"Token \xff\xfe"
    request = Request(raw)
    with pytest.raises(AuthenticationFailed, match="invalid characters"):
        _run(auth.aauthenticate(request))


def test_remote_user_aauthenticate_returns_user(monkeypatch):
    user = _user(active=True)

    async def fake_django_auth(request=None, remote_user=None):
        return user

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    auth = RemoteUserAuthentication()
    request = _make_request({"REMOTE_USER": "khan"})
    result = _run(auth.aauthenticate(request))
    assert result == (user, None)


def test_remote_user_aauthenticate_returns_none_when_inactive(monkeypatch):
    user = _user(active=False)

    async def fake_django_auth(request=None, remote_user=None):
        return user

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    auth = RemoteUserAuthentication()
    request = _make_request({"REMOTE_USER": "khan"})
    assert _run(auth.aauthenticate(request)) is None


def test_remote_user_aauthenticate_returns_none_when_no_user(monkeypatch):
    async def fake_django_auth(request=None, remote_user=None):
        return None

    monkeypatch.setattr(
        "restflow.authentication.authentication.django_aauthenticate",
        fake_django_auth,
    )

    auth = RemoteUserAuthentication()
    request = _make_request()
    assert _run(auth.aauthenticate(request)) is None
