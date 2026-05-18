# Exception handler

The exception handler renders every error as a uniform envelope so
clients can branch on a stable code instead of parsing varying
shapes from DRF, Django, and application-level exceptions.


DRF ships an exception handler that returns slightly different
shapes depending on which DRF exception fired and falls through to
Django for everything else. That makes client-side error handling
inconsistent. Restflow's `exception_handler` collapses every
error into a single shape with three fields: a stable `code`, a
human-readable `message`, and a `details` dict that is always
present (empty when there is nothing to add).

The handler is an explicit drop-in: it replaces DRF's
`rest_framework.views.exception_handler` through DRF's settings
hook. Existing DRF behaviour (status codes, WWW-Authenticate
headers, throttle wait times) is preserved.

## Wiring the handler

```python
# settings.py
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "restflow.exceptions.exception_handler",
}
```

No further setup is required. Both sync and async views, including
restflow's `AsyncAPIView` and viewsets, route exceptions through
this hook.

## Error envelope shape

Every response that came from the handler has this shape:

```json
{
  "error": {
    "code": "<stable_string>",
    "message": "<human-readable>",
    "details": {}
  }
}
```

`code` is the stable string clients should branch on. `message` is
the human-readable summary. `details` is always present (an empty
object when the error has nothing to add). The HTTP status code is
preserved from the underlying exception.

Build envelopes manually with the helper:

```python
from restflow.exceptions import format_error, ErrorCode


payload = format_error(
    ErrorCode.CONFLICT,
    "The record is locked.",
    {"locked_by": user_id},
)
```

The first argument accepts either an `ErrorCode` enum value or a
plain string.

## ErrorCode enum

`ErrorCode` is a string enum with stable values. Clients should
match against these strings; the enum is convenient for callers in
Python.

| Member | Value |
| --- | --- |
| `NOT_AUTHENTICATED` | `"not_authenticated"` |
| `AUTHENTICATION_FAILED` | `"authentication_failed"` |
| `PERMISSION_DENIED` | `"permission_denied"` |
| `VALIDATION_ERROR` | `"validation_error"` |
| `PARSE_ERROR` | `"parse_error"` |
| `NOT_FOUND` | `"not_found"` |
| `METHOD_NOT_ALLOWED` | `"method_not_allowed"` |
| `UNSUPPORTED_MEDIA_TYPE` | `"unsupported_media_type"` |
| `NOT_ACCEPTABLE` | `"not_acceptable"` |
| `THROTTLED` | `"throttled"` |
| `CONFLICT` | `"conflict"` |
| `INTERNAL_ERROR` | `"internal_error"` |
| `SERVICE_UNAVAILABLE` | `"service_unavailable"` |

Adding new codes is a one-line change in `ErrorCode`. Old clients
keep working because the existing values are stable strings.

## Built-in mapping

The handler walks through these checks in order and returns on the
first match:

| Exception | Code | Status |
| --- | --- | --- |
| `restflow.exceptions.APIException` (and subclasses) | the instance's `code` | the instance's `status_code` |
| `rest_framework.exceptions.NotAuthenticated` | `not_authenticated` | 401 |
| `rest_framework.exceptions.AuthenticationFailed` | `authentication_failed` | 401 |
| `rest_framework.exceptions.PermissionDenied` | `permission_denied` | 403 |
| `django.core.exceptions.PermissionDenied` | `permission_denied` | 403 |
| `rest_framework.exceptions.NotFound` | `not_found` | 404 |
| `django.http.Http404` and `django.core.exceptions.ObjectDoesNotExist` | `not_found` | 404 |
| `rest_framework.exceptions.MethodNotAllowed` | `method_not_allowed` | 405 |
| `rest_framework.exceptions.NotAcceptable` | `not_acceptable` | 406 |
| `rest_framework.exceptions.UnsupportedMediaType` | `unsupported_media_type` | 415 |
| `rest_framework.exceptions.ParseError` | `parse_error` | 400 |
| `rest_framework.exceptions.Throttled` | `throttled` | 429 |
| `rest_framework.exceptions.ValidationError` | `validation_error` | 400 |
| `django.core.exceptions.ValidationError` | `validation_error` | 400 |
| anything else | `internal_error` (only when DRF's default handler returned a response) | the DRF default's status |

Anything DRF cannot handle (uncaught Python exceptions) bubbles up
to Django's standard 500 handling and does not produce a wrapped
envelope.

## APIException

`restflow.exceptions.APIException` is a thin subclass of
`rest_framework.exceptions.APIException` that carries a stable code
and a structured details payload.

```python
from restflow.exceptions import APIException, ErrorCode


class ProductLockedException(APIException):
    code = ErrorCode.CONFLICT.value
    status_code = 409
    default_detail = "The product is locked for editing."


raise ProductLockedException(details={"locked_by": user.id})
```

The `__init__` signature accepts:

- `detail` -- positional, the message (also accepts a dict or list,
  treated as DRF does).
- `code` -- string or `ErrorCode`. Overrides the class attribute.
- `details` -- dict. Overrides the class attribute.
- `status_code` -- int. Overrides the class attribute.

```python
raise APIException(
    "Custom error",
    code=ErrorCode.VALIDATION_ERROR,
    details={"field": ["bad value"]},
    status_code=422,
)
```

Subclassing patterns:

```python
class TenantQuotaExceeded(APIException):
    code = "tenant_quota_exceeded"
    status_code = 402
    default_detail = "Quota exceeded for this tenant."


class StaleResource(APIException):
    code = ErrorCode.CONFLICT.value
    status_code = 409
    default_detail = "Resource has changed since it was loaded."
```

Subclasses that share `ErrorCode.CONFLICT` are still distinguishable
to the client because the `details` payload can carry the precise
sub-reason (`{"reason": "stale_resource"}`).

## Validation errors

DRF's `ValidationError` carries either a list (for top-level
errors) or a dict (for field-keyed errors). The handler normalises
both shapes into a dict under `details`.

Field-keyed example:

```python
serializer.is_valid(raise_exception=True)
# raises rest_framework.exceptions.ValidationError({
#     "email": ["Enter a valid email."],
#     "age": ["Ensure this value is greater than 0."],
# })
```

Response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {
      "email": ["Enter a valid email."],
      "age": ["Ensure this value is greater than 0."]
    }
  }
}
```

Top-level (non-field) errors:

```python
raise rest_framework.exceptions.ValidationError(
    ["Account is locked."],
)
```

Response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {"non_field_errors": ["Account is locked."]}
  }
}
```

Django's `ValidationError` is wrapped through DRF's
`as_serializer_error` first, then normalised the same way. Nested
errors (a serializer field that itself raises a structured error)
preserve nesting in `details`.

Every value inside `details` is stringified, so DRF's `ErrorDetail`
instances become plain strings -- safe for `json.dumps`.

## Throttling errors

`Throttled` carries a `wait` attribute (seconds until retry is
allowed). The handler exposes that as
`details.retry_after_seconds`:

```json
{
  "error": {
    "code": "throttled",
    "message": "Request was throttled. Expected available in 30 seconds.",
    "details": {"retry_after_seconds": 30}
  }
}
```

When `wait` is `None`, `details` is empty. The HTTP response also
keeps DRF's `Retry-After` header (set by DRF's view handling, not
by the exception handler).

## Authentication and permission errors

`NotAuthenticated` returns 401 with code `not_authenticated`.
`AuthenticationFailed` returns 401 with code
`authentication_failed`. `PermissionDenied` returns 403 with code
`permission_denied`. Django's `PermissionDenied` exception (raised
through `@permission_required` decorators or middleware) is mapped
to the same envelope.

When the request had no credentials at all, DRF raises
`NotAuthenticated`. When credentials were provided but invalid,
DRF raises `AuthenticationFailed`. Both produce 401 but with
different `code`s, so clients can distinguish "log in" from "fix
the credentials".

The `WWW-Authenticate` header is still set by the view's exception
handling pipeline, not by the exception handler -- restflow's
handler only changes the body shape.

## 404 and missing resources

`NotFound`, `Http404`, and `ObjectDoesNotExist` all collapse to:

```json
{
  "error": {
    "code": "not_found",
    "message": "Resource not found.",
    "details": {}
  }
}
```

The message comes from the exception's `detail` attribute when
present, otherwise the literal `"Resource not found."` is used (for
`Http404` and `ObjectDoesNotExist` instances raised directly from
view code).

## Custom application errors

There are two common shapes:

### Subclass APIException with a stable code

```python
from restflow.exceptions import APIException


class TenantSuspendedException(APIException):
    code = "tenant_suspended"
    status_code = 403
    default_detail = "Tenant is suspended."


@api_view(["POST"])
def create_order(request):
    if request.user.tenant.is_suspended:
        raise TenantSuspendedException(
            details={"tenant_id": request.user.tenant.id},
        )
    ...
```

### Raise APIException directly

```python
from restflow.exceptions import APIException, ErrorCode


def transfer(request):
    if not enough_balance(request.user):
        raise APIException(
            "Insufficient balance.",
            code="insufficient_balance",
            status_code=402,
            details={"required": 100, "available": 25},
        )
```

Both produce the same envelope shape; the subclass approach is
preferred when the same error is raised from multiple places.

## Customising the handler

The simplest customisation is to add a project-specific code
mapping in front of restflow's handler:

```python
# myproject/exceptions.py
from restflow.exceptions import (
    APIException, format_error, exception_handler as base_handler,
)
from rest_framework.response import Response


class TimeoutException(Exception):
    """Raised by an internal subsystem on operation timeout."""


def exception_handler(exc, context):
    if isinstance(exc, TimeoutException):
        return Response(
            format_error(
                "operation_timeout",
                "Operation timed out.",
                {"timeout_seconds": int(getattr(exc, "seconds", 0))},
            ),
            status=504,
        )
    return base_handler(exc, context)
```

```python
# settings.py
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "myproject.exceptions.exception_handler",
}
```

Project handlers should call back into the restflow handler for
unknown exceptions so the envelope contract still applies to DRF
and Django errors.

## Working with the async dispatch loop

`AsyncAPIView.ahandle_exception` calls the configured exception
handler from DRF settings. The handler runs synchronously inside
`ahandle_exception`; nothing in restflow's exception logic blocks
on I/O, so a sync handler is appropriate even on the async path.



## Settings interaction

The handler reads no restflow-specific settings. The only setting
that matters is DRF's `REST_FRAMEWORK["EXCEPTION_HANDLER"]`. 

When `DEBUG=True`, Django still renders its default debug page for
exceptions. Inside the DRF pipeline, the handler always
takes precedence.

## Next steps

- [Exception handler API reference](../../api/exception-handler/index.md)
  for the autogenerated API surface.
