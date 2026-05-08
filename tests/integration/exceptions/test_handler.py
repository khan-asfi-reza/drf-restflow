import asyncio

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import path
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response

from restflow.exceptions import (
    APIException,
    ErrorCode,
    format_error,
    exception_handler,
)
from restflow.views import APIView, AsyncAPIView


def _run(coro):
    return asyncio.run(coro)


def _ctx(view=None):
    return {"view": view, "request": None, "args": (), "kwargs": {}}


def test_envelope_shape():
    env = format_error(ErrorCode.NOT_FOUND, "x")
    assert env == {
        "error": {"code": "not_found", "message": "x", "details": {}}
    }


def test_envelope_accepts_string_code():
    env = format_error("custom_code", "msg", {"k": 1})
    assert env == {
        "error": {"code": "custom_code", "message": "msg", "details": {"k": 1}}
    }


def test_handler_maps_not_authenticated():
    response = exception_handler(drf_exceptions.NotAuthenticated(), _ctx())
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"


def test_handler_maps_authentication_failed():
    response = exception_handler(drf_exceptions.AuthenticationFailed("bad"), _ctx())
    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"
    assert "bad" in response.data["error"]["message"]


def test_handler_maps_drf_permission_denied():
    response = exception_handler(drf_exceptions.PermissionDenied(), _ctx())
    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"


def test_handler_maps_django_permission_denied():
    response = exception_handler(DjangoPermissionDenied("denied"), _ctx())
    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"
    assert response.data["error"]["message"] == "denied"


def test_handler_maps_django_permission_denied_no_message():
    response = exception_handler(DjangoPermissionDenied(), _ctx())
    assert response.data["error"]["message"] == "Permission denied."


def test_handler_maps_drf_not_found():
    response = exception_handler(drf_exceptions.NotFound(), _ctx())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_handler_maps_http404():
    response = exception_handler(Http404("missing"), _ctx())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"
    assert response.data["error"]["message"] == "Resource not found."


def test_handler_maps_object_does_not_exist():
    response = exception_handler(ObjectDoesNotExist(), _ctx())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_handler_maps_method_not_allowed():
    response = exception_handler(drf_exceptions.MethodNotAllowed("POST"), _ctx())
    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"


def test_handler_maps_not_acceptable():
    response = exception_handler(drf_exceptions.NotAcceptable(), _ctx())
    assert response.status_code == 406
    assert response.data["error"]["code"] == "not_acceptable"


def test_handler_maps_unsupported_media_type():
    response = exception_handler(
        drf_exceptions.UnsupportedMediaType("application/x-foo"), _ctx()
    )
    assert response.status_code == 415
    assert response.data["error"]["code"] == "unsupported_media_type"


def test_handler_maps_parse_error():
    response = exception_handler(drf_exceptions.ParseError(), _ctx())
    assert response.status_code == 400
    assert response.data["error"]["code"] == "parse_error"


def test_handler_maps_throttled_with_wait():
    exc = drf_exceptions.Throttled(wait=12)
    response = exception_handler(exc, _ctx())
    assert response.status_code == 429
    assert response.data["error"]["code"] == "throttled"
    assert response.data["error"]["details"] == {"retry_after_seconds": 12}


def test_handler_maps_throttled_without_wait():
    exc = drf_exceptions.Throttled()
    exc.wait = None
    response = exception_handler(exc, _ctx())
    assert response.status_code == 429
    assert response.data["error"]["details"] == {}


def test_handler_validation_error_dict():
    exc = drf_exceptions.ValidationError({"name": ["Required."]})
    response = exception_handler(exc, _ctx())
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["message"] == "Request validation failed."
    assert response.data["error"]["details"] == {"name": ["Required."]}


def test_handler_validation_error_list_becomes_non_field():
    exc = drf_exceptions.ValidationError(["Bad input"])
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"] == {
        "non_field_errors": ["Bad input"]
    }


def test_handler_validation_error_nested():
    exc = drf_exceptions.ValidationError(
        {"address": {"city": ["Required."]}}
    )
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"] == {
        "address": {"city": ["Required."]}
    }


def test_handler_django_validation_error():
    exc = DjangoValidationError({"email": ["Invalid."]})
    response = exception_handler(exc, _ctx())
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "email" in response.data["error"]["details"]


def test_handler_custom_apiexception_uses_code_and_details():
    class _PaymentRequired(APIException):
        status_code = 402
        default_detail = "Payment required."
        code = "payment_required"

    exc = _PaymentRequired(details={"hint": "subscribe"})
    response = exception_handler(exc, _ctx())
    assert response.status_code == 402
    assert response.data["error"]["code"] == "payment_required"
    assert response.data["error"]["details"] == {"hint": "subscribe"}


def test_handler_apiexception_constructor_overrides():
    exc = APIException(
        "boom", code=ErrorCode.CONFLICT, details={"k": 1}, status_code=409
    )
    response = exception_handler(exc, _ctx())
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"
    assert response.data["error"]["details"] == {"k": 1}


def test_handler_falls_through_to_drf_for_unmapped():
    class _Custom(drf_exceptions.APIException):
        status_code = 418
        default_detail = "I am a teapot."
        default_code = "teapot"

    response = exception_handler(_Custom(), _ctx())
    assert response.status_code == 418
    assert response.data["error"]["code"] == "internal_error"


def test_handler_returns_none_for_unmapped_exception():
    response = exception_handler(RuntimeError("boom"), _ctx())
    assert response is None


_NOT_FOUND_MSG = "nope"


class _AsyncRaisingView(AsyncAPIView):
    async def get(self, request):
        raise drf_exceptions.NotFound(_NOT_FOUND_MSG)


class _SyncValidationView(APIView):
    def post(self, request):
        raise drf_exceptions.ValidationError({"field": ["Bad."]})


urlpatterns = [
    path("missing/", _AsyncRaisingView.as_view(), name="missing"),
    path("validate/", _SyncValidationView.as_view(), name="validate"),
]


@pytest.fixture
def envelope_urls():
    with override_settings(
        ROOT_URLCONF=__name__,
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "restflow.exceptions.exception_handler"
        },
    ):
        yield


def test_async_view_round_trips_through_handler(envelope_urls):
    from restflow.test import AsyncAPIClient

    client = AsyncAPIClient()
    response = _run(client.get("/missing/"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_sync_view_round_trips_through_handler(envelope_urls):
    factory = RequestFactory()
    request = factory.post(
        "/validate/", data='{"x": 1}', content_type="application/json"
    )
    response = _SyncValidationView.as_view()(request)
    response.render()
    assert response.status_code == 400
    body = response.content
    assert b'"validation_error"' in body
    assert b'"field"' in body


def test_handler_handles_exception_with_async_user_handler():
    async def custom_handler(exc, context):
        await asyncio.sleep(0)
        return Response({"async": True}, status=599)

    boom = "boom"

    class _V(AsyncAPIView):
        def get_exception_handler(self):
            return custom_handler

        async def get(self, request):
            raise RuntimeError(boom)

    factory = RequestFactory()
    raw = factory.get("/")
    response = _run(_V.as_view()(raw))
    assert response.status_code == 599
    assert response.data == {"async": True}


def test_normalize_handles_scalar_detail():
    from rest_framework.exceptions import ErrorDetail

    exc = drf_exceptions.ValidationError(ErrorDetail("oops"))
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"] == {"non_field_errors": ["oops"]}


def test_normalize_handles_scalar_value_in_dict():
    from rest_framework.exceptions import ErrorDetail

    exc = drf_exceptions.ValidationError(
        {"name": ErrorDetail("required")}
    )
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"] == {"name": "required"}
