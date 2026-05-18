from enum import Enum
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler


class ErrorCode(str, Enum):
    """Stable error codes returned in restflow's error response."""

    NOT_AUTHENTICATED = "not_authenticated"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_ERROR = "validation_error"
    PARSE_ERROR = "parse_error"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    NOT_ACCEPTABLE = "not_acceptable"
    THROTTLED = "throttled"
    CONFLICT = "conflict"
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"


class APIException(drf_exceptions.APIException):
    """DRF APIException carrying a stable error code and structured details.

    Subclass and override `code`, `default_detail`, `status_code` to
    expose application-specific errors that render through
    `restflow.exceptions.exception_handler` as a uniform formatter.
    """

    code: str = ErrorCode.INTERNAL_ERROR.value
    details: dict[str, Any] | None = None

    def __init__(
        self,
        detail: Any = None,
        *,
        code: str | ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ):
        super().__init__(detail)
        if code is not None:
            self.code = code.value if isinstance(code, ErrorCode) else code
        if details is not None:
            self.details = details
        if status_code is not None:
            self.status_code = status_code


def format_error(
    code: str | ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical error envelope dict."""
    code_value = code.value if isinstance(code, ErrorCode) else code
    return {
        "error": {
            "code": code_value,
            "message": message,
            "details": details or {},
        }
    }


def _normalize_validation_detail(detail: Any) -> dict[str, Any]:
    if isinstance(detail, list):
        return {"non_field_errors": [_stringify(item) for item in detail]}
    if isinstance(detail, dict):
        return {k: _normalize_field(v) for k, v in detail.items()}
    # DRF always wraps ValidationError detail into a list or dict at construction
    return {"non_field_errors": [_stringify(detail)]}  # pragma: no cover


def _normalize_field(value: Any) -> Any:
    if isinstance(value, list):
        return [_stringify(item) for item in value]
    if isinstance(value, dict):
        return {k: _normalize_field(v) for k, v in value.items()}
    return _stringify(value)


def _stringify(value: Any) -> str:
    return str(value)


def _throttled_details(exc: drf_exceptions.Throttled) -> dict[str, Any]:
    if exc.wait is None:
        return {}
    return {"retry_after_seconds": int(exc.wait)}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Render every exception as restflow's error envelope.

    Used via `REST_FRAMEWORK = {"EXCEPTION_HANDLER": "restflow.exceptions.exception_handler"}`.
    Maps DRF, Django, and `restflow.exceptions.APIException` instances onto
    the error response `{error: {code, message, details}}` and falls through to
    DRF's default for anything else.
    """
    if isinstance(exc, APIException):
        return Response(
            format_error(exc.code, str(exc.detail), exc.details),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.NotAuthenticated):
        return Response(
            format_error(ErrorCode.NOT_AUTHENTICATED, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.AuthenticationFailed):
        return Response(
            format_error(ErrorCode.AUTHENTICATION_FAILED, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.PermissionDenied):
        return Response(
            format_error(ErrorCode.PERMISSION_DENIED, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            format_error(
                ErrorCode.PERMISSION_DENIED,
                str(exc) or _("Permission denied."),
            ),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, drf_exceptions.NotFound):
        return Response(
            format_error(ErrorCode.NOT_FOUND, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return Response(
            format_error(ErrorCode.NOT_FOUND, _("Resource not found.")),
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, drf_exceptions.MethodNotAllowed):
        return Response(
            format_error(ErrorCode.METHOD_NOT_ALLOWED, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.NotAcceptable):
        return Response(
            format_error(ErrorCode.NOT_ACCEPTABLE, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.UnsupportedMediaType):
        return Response(
            format_error(ErrorCode.UNSUPPORTED_MEDIA_TYPE, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.ParseError):
        return Response(
            format_error(ErrorCode.PARSE_ERROR, str(exc.detail)),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.Throttled):
        return Response(
            format_error(
                ErrorCode.THROTTLED,
                str(exc.detail),
                _throttled_details(exc),
            ),
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.ValidationError):
        return Response(
            format_error(
                ErrorCode.VALIDATION_ERROR,
                _("Request validation failed."),
                _normalize_validation_detail(exc.detail),
            ),
            status=exc.status_code,
        )

    if isinstance(exc, DjangoValidationError):
        wrapped = drf_exceptions.ValidationError(
            detail=as_serializer_error(exc)
        )
        return Response(
            format_error(
                ErrorCode.VALIDATION_ERROR,
                _("Request validation failed."),
                _normalize_validation_detail(wrapped.detail),
            ),
            status=wrapped.status_code,
        )

    drf_response = drf_exception_handler(exc, context)
    if drf_response is not None:
        return Response(
            format_error(
                ErrorCode.INTERNAL_ERROR,
                _stringify(drf_response.data),
            ),
            status=drf_response.status_code,
        )
    return None


__all__ = [
    "APIException",
    "ErrorCode",
    "exception_handler",
    "format_error",
]
