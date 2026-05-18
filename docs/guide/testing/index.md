# Testing

`restflow.test` provides async-aware test utilities for views and view
sets that run on Django's ASGI stack. The module mirrors the surface
of DRF's `rest_framework.test` but every entry point speaks ASGI and
returns awaitable responses, so async views can be exercised end to
end without bridging through `async_to_sync`.

restflow's async views run on the ASGI request cycle. DRF's stock
`APIClient` builds WSGI requests and synchronous responses, which
means hitting an async view from those tests forces a sync-to-async
bridge that can deadlock when middleware or signal handlers also run
in the loop. `AsyncAPIClient` builds ASGI requests directly and
returns awaitable responses, so async view code is exercised in its
real environment.

Three things distinguish this module from Django's `AsyncClient`:

- **DRF format encoding.** `data=` plus `format="json"` (or any
  format registered in `TEST_REQUEST_RENDERER_CLASSES`) is rendered
  through DRF's renderers, so the body and `Content-Type` match what
  a real DRF client would send.
- **Force-auth handler.** Calling `client.force_authenticate(user)`
  injects the user onto every outgoing request via a custom async
  client handler, so authenticator chains can be skipped during unit
  tests.
- **ASGI request factory.** `AsyncAPIRequestFactory` produces raw
  ASGI requests that can be passed straight into
  `await view(request)` without a URL conf.

The four test case bases (`AsyncAPISimpleTestCase`, `AsyncAPITestCase`,
`AsyncAPITransactionTestCase`, `AsyncAPILiveServerTestCase`) wire
`AsyncAPIClient` as `client_class` so `self.client` is the async
variant out of the box.

## AsyncAPIClient

`AsyncAPIClient` is a drop-in replacement for `rest_framework.test.APIClient`
in async test suites.

### Constructor

```python
from restflow.test import AsyncAPIClient


client = AsyncAPIClient(enforce_csrf_checks=False, HTTP_HOST="api.example.com")
```

- `enforce_csrf_checks` toggles CSRF enforcement for session-auth
  tests. Off by default, matching DRF.
- Any extra keyword arguments are forwarded to Django's
  `AsyncClient` and used as default WSGI environ keys for every
  request issued by the client.

### Request methods

Every HTTP verb is exposed as an async method that returns an
awaitable response:

```python
response = await client.get("/api/products/")
response = await client.post("/api/products/", data={"name": "Phone"}, format="json")
response = await client.put("/api/products/1/", data={"name": "Phone v2"}, format="json")
response = await client.patch("/api/products/1/", data={"price": 999}, format="json")
response = await client.delete("/api/products/1/")
response = await client.options("/api/products/")
response = await client.head("/api/products/")
```

The verbs that accept a body (`post`, `put`, `patch`, `delete`,
`options`) take `data=`, `format=`, and `content_type=` arguments.
`format=` and `content_type=` are mutually exclusive and an
assertion fires if both are passed:

```python
await client.post("/api/", data={...}, format="json")            # ok
await client.post("/api/", data=raw_bytes, content_type="text/plain")  # ok
await client.post("/api/", data={...}, format="json", content_type="x")  # AssertionError
```

`get` and `head` do not encode bodies; pass query arguments through
`data=` and they are appended to the URL as a query string, matching
Django's behaviour.

### Persistent headers

`credentials()` sets headers used on every subsequent request. Keys
must follow Django's WSGI environ convention and start with `HTTP_`
or `CONTENT_`:

```python
client.credentials(HTTP_AUTHORIZATION="Bearer abc.def.ghi")
response = await client.get("/api/products/")
client.credentials()  # reset
```

### login, logout, force_login

For session-based authentication the client mirrors Django's API:

```python
await client.alogin(username="khan", password="secret")
response = await client.get("/api/orders/")
await client.alogout()
```

`force_login(user)` skips the password-check round trip and seeds
the session directly:

```python
await client.aforce_login(user)
response = await client.get("/api/orders/")
```

`force_authenticate(user)` is more aggressive and bypasses
authentication entirely, including session and authenticator
classes (see [force_authenticate](#force_authenticate) below).
`logout()` clears stored credentials, force-auth state, and the
active session in one call.

## AsyncAPIRequestFactory

`AsyncAPIRequestFactory` builds raw ASGI requests for tests that
bind a request directly to a view. Use it when the goal is to test
the view's logic without involving URL routing or middleware.

```python
from restflow.test import AsyncAPIRequestFactory
from products.views import ProductListView


factory = AsyncAPIRequestFactory()
request = factory.get("/api/products/", {"category": "phones"})
response = await ProductListView.as_view()(request)
```

The factory mirrors DRF's `APIRequestFactory`: each verb supports
`data=`, `format=`, and `content_type=` and uses the same encoding
rules as the client. The big difference vs the client is that the
factory does not run middleware. That makes the factory ideal for
unit tests that should focus on the view, but unsuitable for end-to-end
tests where middleware behaviour matters.

```python
factory = AsyncAPIRequestFactory()
request = factory.post(
    "/api/products/", data={"name": "Phone"}, format="json",
)
response = await ProductCreateView.as_view()(request)
```

Pair the factory with `force_authenticate` when authentication
should be short-circuited:

```python
from restflow.test import force_authenticate


request = factory.get("/api/orders/")
force_authenticate(request, user=khan)
response = await OrderListView.as_view()(request)
```

## force_authenticate

`force_authenticate(request, user=None, token=None)` stores the user
and token on `request._force_auth_user` and `request._force_auth_token`.
DRF's authentication classes detect those attributes during
`Request.user` resolution and skip the authenticator chain entirely.
The typical use case is unit tests that should not exercise token
issuance or JWT signature checks.

```python
factory = AsyncAPIRequestFactory()
request = factory.get("/api/orders/")
force_authenticate(request, user=khan, token="dummy-token")
response = await OrderListView.as_view()(request)
```

For the client, the same effect is achieved through
`client.force_authenticate(user)`. Internally that stores the user
on the client's handler so every subsequent request is force-authed
until reset:

```python
client = AsyncAPIClient()
client.force_authenticate(user=khan)
response = await client.get("/api/orders/")  # khan
client.force_authenticate()                  # clear
response = await client.get("/api/orders/")  # anonymous
```

## Test case bases

Four base classes wrap Django's standard test cases with
`AsyncAPIClient` already wired as `self.client`. Pick the base by
the kind of database access the test needs.

### AsyncAPISimpleTestCase

```python
from restflow.test import AsyncAPISimpleTestCase


class HealthCheckTests(AsyncAPISimpleTestCase):
    async def test_health_endpoint_returns_ok(self):
        response = await self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
```

No database transaction. Use it for tests that do not touch the
database, such as health checks, schema endpoints, or pure-function
view logic.

### AsyncAPITestCase

```python
from restflow.test import AsyncAPITestCase


class ProductListTests(AsyncAPITestCase):
    async def test_returns_active_products(self):
        await Product.objects.acreate(name="Phone", is_active=True)
        response = await self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
```

Wraps each test in a database transaction that is rolled back at
teardown. This is the default for DB-backed tests and the fastest
option, since rollback is cheap.

There is one important caveat: code that registers callbacks through
`transaction.on_commit` does not run, because the wrapping
transaction is rolled back rather than committed. Cache invalidation
rules in `restflow.caching` use `transaction.on_commit` to defer
cache busting until the data has actually been written, so they will
not fire under `AsyncAPITestCase`. See
[Cache invalidation tests](#cache-invalidation-tests) for the right
base class.

### AsyncAPITransactionTestCase

```python
from restflow.test import AsyncAPITransactionTestCase


class CacheInvalidationTests(AsyncAPITransactionTestCase):
    async def test_save_busts_cached_response(self):
        await Product.objects.acreate(name="Phone")
        first = await self.client.get("/api/products/")
        await Product.objects.acreate(name="Tablet")
        second = await self.client.get("/api/products/")
        self.assertNotEqual(first.json(), second.json())
```

Real transactions, with the database flushed between tests. Slower
than `AsyncAPITestCase`, but `transaction.on_commit` callbacks run
because the transaction actually commits. This is the right base
for any test that exercises signal-driven cache invalidation,
post-commit side effects, or anything else that depends on the
commit having happened.

### AsyncAPILiveServerTestCase

```python
from restflow.test import AsyncAPILiveServerTestCase
import httpx


class LiveProductTests(AsyncAPILiveServerTestCase):
    async def test_external_client_can_list_products(self):
        async with httpx.AsyncClient() as http:
            response = await http.get(f"{self.live_server_url}/api/products/")
        self.assertEqual(response.status_code, 200)
```

Spins up a live server in a background thread (Daphne or whichever
ASGI server is configured) so external clients such as `httpx` or
Selenium can hit the application over a real socket. Use this for
integration tests that need to exercise the full ASGI stack,
including middleware and connection handling. Slow, so reach for it
only when an in-process client is not enough.

All four bases set `client_class = AsyncAPIClient`, so `self.client`
is always the async-aware variant.

## Cache invalidation tests

restflow's caching layer attaches signal handlers that wrap their
work in `transaction.on_commit(...)` so the cache is not busted
until the database has actually committed. That design is correct
for production but interacts with Django's test infrastructure.

The framework rule is: tests that exercise signal-driven
invalidation must commit the transaction, not roll it back.

There are three common ways to satisfy that rule.

### AsyncAPITransactionTestCase

```python
from restflow.test import AsyncAPITransactionTestCase


class ProductCacheTests(AsyncAPITransactionTestCase):
    async def test_create_invalidates_cached_list(self):
        first = await self.client.get("/api/products/")
        await Product.objects.acreate(name="Phone")
        second = await self.client.get("/api/products/")
        self.assertNotEqual(first.json(), second.json())
```

`AsyncAPITransactionTestCase` runs each test in a real transaction
that actually commits, so `transaction.on_commit` callbacks fire as
intended.

### pytest-django with transaction=True

For pytest suites, mark the test so pytest-django uses a real
transaction:

```python
import pytest


@pytest.mark.django_db(transaction=True)
async def test_create_invalidates_cached_list(async_client):
    first = await async_client.get("/api/products/")
    await Product.objects.acreate(name="Phone")
    second = await async_client.get("/api/products/")
    assert first.json() != second.json()
```

### captureOnCommitCallbacks

When swapping the base class is not feasible, wrap the body of the
test in `transaction.atomic()` and use Django's
`captureOnCommitCallbacks(execute=True)` helper to drain pending
callbacks at the end of the block:

```python
from django.db import transaction
from restflow.test import AsyncAPITestCase


class ProductCacheTests(AsyncAPITestCase):
    async def test_create_invalidates_cached_list(self):
        with self.captureOnCommitCallbacks(execute=True):
            await Product.objects.acreate(name="Phone")
        response = await self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
```

A common reason invalidation appears not to fire is that
`restflow.caching` is missing from `INSTALLED_APPS` in the test
settings module; without the app registered the rules never bind to
the model signals.

## Format encoding

Bodies are rendered through DRF's `TEST_REQUEST_RENDERER_CLASSES`,
which means the encoding follows whatever DRF is configured to use
in tests. Two arguments drive the behaviour:

- `data=` is the Python-shaped payload (a dict, list, etc).
- `format=` selects a renderer by short name. The default is
  `"json"`. Pass `"multipart"` for file uploads.

```python
await client.post("/api/products/", data={"name": "Phone"}, format="json")

with open("photo.jpg", "rb") as fh:
    await client.post(
        "/api/products/1/photo/",
        data={"photo": fh},
        format="multipart",
    )
```

`content_type=` is the escape hatch for tests that already have a
serialised body and want full control:

```python
await client.post(
    "/api/webhooks/stripe/",
    data=raw_payload_bytes,
    content_type="application/json",
)
```

`format=` and `content_type=` cannot both be supplied; an assertion
fires if both are passed. The set of available formats comes from
DRF's `TEST_REQUEST_RENDERER_CLASSES` setting; the default
configuration ships JSON and multipart.

## Authentication patterns

Pick the pattern that matches the layer being tested.

### Session login

```python
await User.objects.acreate_user(username="khan", password="hunter2")
await client.alogin(username="khan", password="hunter2")
response = await client.get("/api/profile/")
```

### force_login

`force_login` skips password verification and seeds the session
directly:

```python
khan = await User.objects.aget(username="khan")
await client.aforce_login(khan)
response = await client.get("/api/profile/")
```

### Authorization header

For token authentication, attach the header through `credentials()`
or as a per-request kwarg:

```python
client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
response = await client.get("/api/orders/")
```

```python
response = await client.get(
    "/api/orders/",
    HTTP_AUTHORIZATION=f"Bearer {access_token}",
)
```

### Factory plus force_authenticate

For unit tests that target the view directly without a URL conf,
combine `AsyncAPIRequestFactory` with `force_authenticate`:

```python
factory = AsyncAPIRequestFactory()
request = factory.get("/api/orders/")
force_authenticate(request, user=khan)
response = await OrderListView.as_view()(request)
```

This is the fastest pattern: no middleware, no auth chain, no URL
resolver.

## Response handling

The response object follows Django's HTTP response API with DRF's
`response.data` mixed in:

- `response.status_code` is the integer status.
- `response.data` is the deserialised payload when the response
  was rendered as JSON (or any other parsed format).
- `response.content` is the raw bytes body.
- `response.json()` parses `response.content` as JSON; useful when
  the renderer was not DRF's JSON renderer but the body still
  happens to be JSON.

For streaming responses, iterate `response.streaming_content`:

```python
response = await client.get("/api/exports/products.csv")
chunks = [chunk async for chunk in response.streaming_content]
```

## Pytest integration

`pytest-django` plus a small fixture is enough to use
`AsyncAPIClient` from pytest tests.

```python
# conftest.py
import pytest
from restflow.test import AsyncAPIClient


@pytest.fixture
def async_client():
    return AsyncAPIClient()
```

```python
# tests/test_products.py
import pytest


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_list_returns_active_products(async_client):
    await Product.objects.acreate(name="Phone", is_active=True)
    response = await async_client.get("/api/products/")
    assert response.status_code == 200
    assert len(response.data) == 1
```

For tests that exercise signal-driven invalidation, swap the marker
for `@pytest.mark.django_db(transaction=True)` so the transaction
actually commits and `transaction.on_commit` runs.

Async tests need `pytest-asyncio` (or `pytest-django`'s built-in
async support on newer versions). Configure the event-loop scope
once in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Reusing the client between tests is fine, since each test starts
from a fresh transaction.

## Common pitfalls

### Forgetting to await

`AsyncAPIClient.get(...)` returns a coroutine. Forgetting to await
returns the coroutine object as the response, which leads to
confusing assertion failures:

```python
response = client.get("/api/products/")          # bad: a coroutine
response = await client.get("/api/products/")    # good
```

### Cache rules silently not firing

If a test using `AsyncAPITestCase` saves a model and the expected
cache invalidation does not happen, the cause is almost always the
rolled-back transaction. `transaction.on_commit` callbacks run only
when the wrapping transaction commits, and `AsyncAPITestCase` rolls
it back. Switch to `AsyncAPITransactionTestCase`, mark the pytest
test with `@pytest.mark.django_db(transaction=True)`, or wrap the
body with `captureOnCommitCallbacks(execute=True)`.

### restflow.caching not in INSTALLED_APPS

Cache invalidation rules register themselves when the app loads. If
the test settings module forgets `"restflow.caching"`, no rules
bind to the model signals and the cache never gets invalidated.
Verify the app is listed in the test settings.

### Mixing format and content_type

Passing both `format=` and `content_type=` triggers an assertion
error. Use one or the other: `format=` for renderer-driven encoding,
`content_type=` for raw bodies.

### Middleware-only behaviour with the factory

`AsyncAPIRequestFactory` does not run middleware, so anything that
relies on middleware (such as `request.user` populated by a custom
auth middleware, CORS headers, or per-request locale) is absent in
factory-built requests. Tests that need middleware should use
`AsyncAPIClient` instead.

## Next steps

- [Test client and case suite API reference](../../api/testing/index.md):
  every public class and function documented from source.
- [Caching guide](../caching/index.md): the invalidation rules and
  the `transaction.on_commit` behaviour that drives the
  transaction-test requirement.
