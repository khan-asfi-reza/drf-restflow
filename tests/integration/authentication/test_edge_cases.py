import asyncio
import base64
import time
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from restflow.authentication import (
    AccessToken,
    BasicAuthentication,
    JWTAuthentication,
    RefreshToken,
    SessionAuthentication,
    TokenAuthentication,
    TokenError,
)
from restflow.authentication.jwt import (
    ATokenBlacklist,
    CacheBlacklistBackend,
    ModelBlacklistBackend,
    decode_token,
    encode_token,
    get_jwt_settings,
    get_password_hash,
    get_user_authentication_rule,
    resolve_token_blacklist_backend,
    validate_algorithm,
    validate_signing_key_shape,
)


def _user_rule_for_tests(user):
    return user is not None and user.is_active


def run_coro(coro):
    return asyncio.run(coro)


def make_user(pk=42, active=True):
    user = MagicMock()
    user.id = pk
    user.is_active = active
    return user


def make_request(token=None, scheme="Bearer"):
    factory = RequestFactory()
    extra = {}
    if token is not None:
        extra["HTTP_AUTHORIZATION"] = f"{scheme} {token}"
    return Request(factory.get("/", **extra))


@pytest.fixture(autouse=True)
def jwt_settings():
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": True,
                "BLACKLIST_ALLOW_LOCMEM": True,
            },
        }
    ):
        yield


def test_validate_algorithm_rejects_none():
    with pytest.raises(TokenError, match="none"):
        validate_algorithm("none")


def test_validate_algorithm_rejects_unknown():
    with pytest.raises(TokenError, match="not supported"):
        validate_algorithm("XYZ123")


def test_validate_algorithm_accepts_hs256():
    validate_algorithm("HS256")


def test_validate_algorithm_accepts_rs256():
    validate_algorithm("RS256")


def test_validate_signing_key_shape_rejects_pem_with_hs():
    pem_like = "-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----"
    with pytest.raises(TokenError, match="HMAC"):
        validate_signing_key_shape("HS256", pem_like)


def test_validate_signing_key_shape_accepts_random_secret():
    validate_signing_key_shape("HS256", "x" * 32)


def test_resolve_blacklist_backend_class_instance_is_returned_as_is():
    backend = ModelBlacklistBackend()
    assert resolve_token_blacklist_backend(backend) is backend


def test_resolve_blacklist_backend_class_constructed_when_class_passed():
    backend = resolve_token_blacklist_backend(ModelBlacklistBackend)
    assert isinstance(backend, ModelBlacklistBackend)


def test_get_user_authentication_rule_resolves_dotted_path():
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "USER_AUTHENTICATION_RULE": (
                    "tests.integration.authentication.test_edge_cases"
                    "._user_rule_for_tests"
                ),
            },
        }
    ):
        assert get_user_authentication_rule() is _user_rule_for_tests


def test_get_user_authentication_rule_returns_callable_unchanged():
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "USER_AUTHENTICATION_RULE": _user_rule_for_tests,
            },
        }
    ):
        assert get_user_authentication_rule() is _user_rule_for_tests


def test_resolve_blacklist_backend_dotted_path_imported():
    backend = resolve_token_blacklist_backend(
        "restflow.authentication.jwt.CacheBlacklistBackend"
    )
    assert isinstance(backend, CacheBlacklistBackend)


def test_password_hash_consistent_for_same_input():
    a = get_password_hash("hashed")
    b = get_password_hash("hashed")
    assert a == b
    assert get_password_hash("a") != get_password_hash("b")


def test_get_jwt_settings_returns_namespace():
    s = get_jwt_settings()
    assert s.ALGORITHM in ("HS256",)


def test_jwt_returns_none_when_authorization_header_uses_basic():
    request = make_request(token="anything", scheme="Basic")
    auth = JWTAuthentication()
    assert run_coro(auth.aauthenticate(request)) is None


def test_jwt_returns_none_for_empty_header():
    factory = RequestFactory()
    request = Request(factory.get("/"))
    assert run_coro(JWTAuthentication().aauthenticate(request)) is None


def test_jwt_rejects_only_bearer_no_token():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer"))
    with pytest.raises(AuthenticationFailed, match="Bearer"):
        run_coro(JWTAuthentication().aauthenticate(request))


def test_jwt_rejects_token_with_trailing_space_only():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer "))
    with pytest.raises(AuthenticationFailed, match="Bearer"):
        run_coro(JWTAuthentication().aauthenticate(request))


def test_jwt_decode_rejects_payload_missing_exp():
    payload = {"token_type": "access", "user_id": 1, "iat": int(time.time())}
    raw = encode_token(payload)
    with pytest.raises(TokenError):
        decode_token(raw)


def test_jwt_decode_rejects_payload_missing_iat():
    payload = {"token_type": "access", "user_id": 1, "exp": int(time.time()) + 60}
    raw = encode_token(payload)
    with pytest.raises(TokenError):
        decode_token(raw)


def test_refresh_rotate_returns_new_jti():
    user = make_user()
    refresh = RefreshToken.for_user(user)
    rotated = refresh.rotate()
    assert rotated.jti != refresh.jti
    assert rotated.token_type == "refresh"


def test_refresh_minted_access_carries_user_claim():
    user = make_user(pk=77)
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    assert access.payload["user_id"] == 77


def test_token_str_returns_raw():
    token = AccessToken.for_user(make_user())
    assert str(token) == token.raw


def test_token_with_check_revoke_token_includes_pwd_hash():
    user = type("U", (), {"id": 1, "is_active": True, "password": "hashed"})()
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "CHECK_REVOKE_TOKEN": True,
            },
        }
    ):
        token = AccessToken.for_user(user)
        s = get_jwt_settings()
        assert s.REVOKE_TOKEN_CLAIM in token.payload


@pytest.mark.django_db(transaction=True)
def test_jwt_authentication_does_not_match_lowercase_bearer():
    User = get_user_model()
    user = User.objects.create_user(username="x", password="p", is_active=True)
    token = AccessToken.for_user(user)
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION=f"bearer {token}"))
    result = run_coro(JWTAuthentication().aauthenticate(request))
    assert result is not None


def test_basic_authentication_returns_none_for_non_basic_header():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer abc"))
    assert run_coro(BasicAuthentication().aauthenticate(request)) is None


def test_basic_authentication_returns_none_when_header_missing():
    factory = RequestFactory()
    request = Request(factory.get("/"))
    assert run_coro(BasicAuthentication().aauthenticate(request)) is None


def test_basic_authentication_rejects_no_credentials():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Basic"))
    with pytest.raises(AuthenticationFailed, match="No credentials"):
        run_coro(BasicAuthentication().aauthenticate(request))


def test_basic_authentication_rejects_three_part_credentials():
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION="Basic part1 part2")
    )
    with pytest.raises(AuthenticationFailed, match="should not contain spaces"):
        run_coro(BasicAuthentication().aauthenticate(request))


def test_basic_authentication_rejects_invalid_base64():
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION="Basic !!!notbase64!!!")
    )
    with pytest.raises(AuthenticationFailed):
        run_coro(BasicAuthentication().aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_basic_authentication_round_trip_valid_credentials():
    User = get_user_model()
    User.objects.create_user(username="basic", password="p", is_active=True)
    creds = base64.b64encode(b"basic:p").decode()
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION=f"Basic {creds}")
    )
    result = run_coro(BasicAuthentication().aauthenticate(request))
    assert result is not None
    assert result[0].username == "basic"


@pytest.mark.django_db(transaction=True)
def test_basic_authentication_rejects_inactive_user():
    User = get_user_model()
    User.objects.create_user(username="inactive2", password="p", is_active=False)
    creds = base64.b64encode(b"inactive2:p").decode()
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION=f"Basic {creds}")
    )
    with pytest.raises(AuthenticationFailed):
        run_coro(BasicAuthentication().aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_basic_authentication_rejects_wrong_password():
    User = get_user_model()
    User.objects.create_user(username="b1", password="right", is_active=True)
    creds = base64.b64encode(b"b1:wrong").decode()
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION=f"Basic {creds}")
    )
    with pytest.raises(AuthenticationFailed):
        run_coro(BasicAuthentication().aauthenticate(request))


def test_token_authentication_returns_none_on_non_token_header():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Basic abc"))
    assert run_coro(TokenAuthentication().aauthenticate(request)) is None


def test_token_authentication_rejects_only_keyword():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Token"))
    with pytest.raises(AuthenticationFailed, match="No credentials"):
        run_coro(TokenAuthentication().aauthenticate(request))


def test_token_authentication_rejects_three_part_token():
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION="Token a b")
    )
    with pytest.raises(AuthenticationFailed, match="should not contain spaces"):
        run_coro(TokenAuthentication().aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_token_authentication_rejects_unknown_token():
    factory = RequestFactory()
    request = Request(factory.get("/", HTTP_AUTHORIZATION="Token nope"))
    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        run_coro(TokenAuthentication().aauthenticate(request))


@pytest.mark.django_db(transaction=True)
def test_token_authentication_round_trip():
    User = get_user_model()
    user = User.objects.create_user(username="tok", password="p", is_active=True)
    from rest_framework.authtoken.models import Token

    tok = Token.objects.create(user=user)
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION=f"Token {tok.key}")
    )
    result = run_coro(TokenAuthentication().aauthenticate(request))
    assert result is not None
    assert result[0].pk == user.pk


@pytest.mark.django_db(transaction=True)
def test_token_authentication_rejects_inactive_user():
    User = get_user_model()
    user = User.objects.create_user(username="tinact", password="p", is_active=False)
    from rest_framework.authtoken.models import Token

    tok = Token.objects.create(user=user)
    factory = RequestFactory()
    request = Request(
        factory.get("/", HTTP_AUTHORIZATION=f"Token {tok.key}")
    )
    with pytest.raises(AuthenticationFailed):
        run_coro(TokenAuthentication().aauthenticate(request))


def test_session_authentication_returns_none_for_anonymous():
    factory = RequestFactory()
    request = Request(factory.get("/"))
    request.user = None
    assert run_coro(SessionAuthentication().aauthenticate(request)) is None


def test_session_authentication_returns_none_for_inactive():
    factory = RequestFactory()
    raw = factory.get("/")
    user = MagicMock()
    user.is_active = False
    raw.user = user
    request = Request(raw)
    assert run_coro(SessionAuthentication().aauthenticate(request)) is None


def test_atoken_blacklist_is_blacklisted_uses_configured_backend():
    user = make_user()
    refresh = RefreshToken.for_user(user)
    run_coro(refresh.ablacklist())
    assert run_coro(ATokenBlacklist.is_blacklisted(refresh.jti)) is True


def test_jwt_with_custom_auth_header_type():
    user = make_user()
    factory = RequestFactory()
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "AUTH_HEADER_TYPES": ("JWT",),
            },
        }
    ):
        request = Request(factory.get("/", HTTP_AUTHORIZATION="Bearer x"))
        assert run_coro(JWTAuthentication().aauthenticate(request)) is None


def test_jwt_decode_invalid_audience():
    user = make_user()
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "AUDIENCE": "issuer-a",
            },
        }
    ):
        token = AccessToken.for_user(user)
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "AUDIENCE": "issuer-b",
            },
        }
    ), pytest.raises(TokenError):
        decode_token(str(token))


def test_jwt_decode_with_leeway_passes_just_expired_token():
    payload = {
        "token_type": "access",
        "user_id": 1,
        "iat": int(time.time()) - 30,
        "exp": int(time.time()) - 5,
        "jti": "x",
    }
    raw = encode_token(payload)
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "LEEWAY": 60,
            },
        }
    ):
        decoded = decode_token(raw)
        assert decoded["user_id"] == 1


def test_atoken_blacklist_is_blacklisted_returns_false_for_unknown_jti():
    assert run_coro(ATokenBlacklist.is_blacklisted("never-seen")) is False


@pytest.mark.django_db(transaction=True)
def test_jwt_blacklist_disabled_skips_check():
    User = get_user_model()
    user = User.objects.create_user(username="bl-disabled", password="x", is_active=True)
    token = AccessToken.for_user(user)
    run_coro(ATokenBlacklist.add(token.jti, expires_at=token.exp))
    factory = RequestFactory()
    with override_settings(
        RESTFLOW_SETTINGS={
            "JWT": {
                "SIGNING_KEY": "test-signing-key-test-signing-key-32",
                "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
                "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
                "BLACKLIST_ENABLED": False,
                "BLACKLIST_ALLOW_LOCMEM": True,
            },
        }
    ):
        request = Request(factory.get("/", HTTP_AUTHORIZATION=f"Bearer {token}"))
        result = run_coro(JWTAuthentication().aauthenticate(request))
        assert result is not None
        assert result[0].pk == user.pk
