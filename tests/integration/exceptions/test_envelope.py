import asyncio
import json

import pytest
from django.test import RequestFactory, override_settings
from django.urls import path
from rest_framework import exceptions as drf_exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from restflow.exceptions import (
    APIException,
    ErrorCode,
    exception_handler,
    format_error,
)
from restflow.permissions import IsAuthenticated
from restflow.test import AsyncAPIClient
from restflow.views import APIView, AsyncAPIView


def _run(coro):
    return asyncio.run(coro)


def _ctx(view=None):
    return {"view": view, "request": None, "args": (), "kwargs": {}}


def test_apiexception_default_code_is_internal_error():
    exc = APIException("boom")
    assert exc.code == ErrorCode.INTERNAL_ERROR.value


def test_apiexception_string_code_used_as_is():
    exc = APIException("boom", code="custom_oops")
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["code"] == "custom_oops"


def test_apiexception_enum_code_uses_value():
    exc = APIException("boom", code=ErrorCode.SERVICE_UNAVAILABLE)
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["code"] == "service_unavailable"


def test_apiexception_status_code_override():
    exc = APIException("boom", status_code=418)
    response = exception_handler(exc, _ctx())
    assert response.status_code == 418


def test_format_error_with_dict_details_unchanged():
    env = format_error("x", "msg", {"a": 1, "b": [2, 3]})
    assert env["error"]["details"] == {"a": 1, "b": [2, 3]}


def test_handler_validation_error_with_list_of_strings_maps_to_non_field():
    exc = drf_exceptions.ValidationError(["err1", "err2"])
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"] == {
        "non_field_errors": ["err1", "err2"]
    }


def test_handler_validation_error_with_mixed_types_in_dict():
    exc = drf_exceptions.ValidationError(
        {"a": ["err1"], "b": "single", "c": {"nested": ["deep"]}}
    )
    response = exception_handler(exc, _ctx())
    details = response.data["error"]["details"]
    assert details["a"] == ["err1"]
    assert details["b"] == "single"
    assert details["c"] == {"nested": ["deep"]}


def test_handler_throttled_with_zero_wait():
    exc = drf_exceptions.Throttled(wait=0)
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["details"]["retry_after_seconds"] == 0


def test_handler_throttled_with_float_wait_returns_int():
    exc = drf_exceptions.Throttled(wait=1.7)
    response = exception_handler(exc, _ctx())
    assert isinstance(
        response.data["error"]["details"]["retry_after_seconds"], int
    )


def test_handler_django_validation_error_string():
    from django.core.exceptions import ValidationError as DjangoValidationError

    exc = DjangoValidationError("just-a-string")
    response = exception_handler(exc, _ctx())
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_handler_django_validation_error_list():
    from django.core.exceptions import ValidationError as DjangoValidationError

    exc = DjangoValidationError(["err1", "err2"])
    response = exception_handler(exc, _ctx())
    assert response.data["error"]["code"] == "validation_error"


def test_handler_returns_none_for_unmapped():
    response = exception_handler(KeyError("unknown"), _ctx())
    assert response is None


class _ConflictException(APIException):
    status_code = 409
    default_detail = "Already exists."
    code = ErrorCode.CONFLICT.value


def test_custom_apiexception_subclass():
    response = exception_handler(_ConflictException(), _ctx())
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


class _Sync400View(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raise drf_exceptions.ValidationError({"x": ["bad"]})


class _Async404View(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        raise drf_exceptions.NotFound("not here")


class _Async403View(AsyncAPIView):
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"ok": True})


class _AsyncCustomView(AsyncAPIView):
    permission_classes = [AllowAny]

    async def get(self, request):
        raise APIException(
            "payment required",
            code="payment_required",
            details={"plan": "pro"},
            status_code=402,
        )


urlpatterns = [
    path("sync400/", _Sync400View.as_view()),
    path("async404/", _Async404View.as_view()),
    path("async403/", _Async403View.as_view()),
    path("async-custom/", _AsyncCustomView.as_view()),
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


def test_sync_view_validation_error_envelope(envelope_urls):
    factory = RequestFactory()
    request = factory.get("/sync400/")
    response = _Sync400View.as_view()(request)
    response.render()
    body = json.loads(response.content)
    assert response.status_code == 400
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["x"] == ["bad"]


def test_async_view_404_envelope(envelope_urls):
    response = _run(AsyncAPIClient().get("/async404/"))
    body = response.json()
    assert response.status_code == 404
    assert body["error"]["code"] == "not_found"


def test_async_view_403_envelope(envelope_urls):
    response = _run(AsyncAPIClient().get("/async403/"))
    body = response.json()
    assert response.status_code in (401, 403)
    assert body["error"]["code"] in ("not_authenticated", "permission_denied")


def test_async_view_custom_apiexception_envelope(envelope_urls):
    response = _run(AsyncAPIClient().get("/async-custom/"))
    body = response.json()
    assert response.status_code == 402
    assert body["error"]["code"] == "payment_required"
    assert body["error"]["details"]["plan"] == "pro"


def test_format_error_with_no_details_yields_empty_dict():
    env = format_error(ErrorCode.NOT_FOUND, "missing")
    assert env["error"]["details"] == {}


def test_format_error_with_none_details_yields_empty_dict():
    env = format_error(ErrorCode.NOT_FOUND, "missing", None)
    assert env["error"]["details"] == {}
