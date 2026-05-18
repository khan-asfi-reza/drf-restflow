# Built-in authenticators

Restflow ships async-aware versions of DRF's standard authentication
classes. Behaviour mirrors DRF for synchronous code paths, so an
existing project can swap imports without changing logic. The
async varaints uses `aauthenticate` coroutine that lets `AsyncAPIView`
perform async ORM queries where possible.

Each class subclasses both restflow's `BaseAuthentication` and the
DRF class of the same name. The DRF behaviour is preserved so an
existing project can swap imports without changing logic. The
synchronous `authenticate` method is unchanged. The new
`aauthenticate` method runs natively without `sync_to_async`,
performing async ORM queries and async credential checks where
possible.

This page covers the non-JWT authenticators. For JSON Web Tokens, see
[JWT authentication](jwt.md). For djangorestframework-simplejwt, see
the [SimpleJWT adapter](simplejwt.md).

## Import paths

```python
from restflow.authentication import (
    BasicAuthentication,
    SessionAuthentication,
    TokenAuthentication,
    RemoteUserAuthentication,
)
```

## BaseAuthentication

Abstract base for every authenticator. Extends DRF's
`BaseAuthentication` and adds an `aauthenticate` method. The default
implementation wraps the sync `authenticate` so that existing DRF
authenticators work under async dispatch without modification.

Override `aauthenticate` directly in custom authenticators when the
logic can run natively async.

## BasicAuthentication

HTTP Basic authentication using a base64-encoded username and
password sent in the Authorization header.

```python
from restflow.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from restflow.views import AsyncAPIView


class HealthView(AsyncAPIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"ok": True})
```

The async surface decodes the header and resolves credentials via
`django.contrib.auth.aauthenticate`. A header like
`Authorization: Basic dXNlcjpwYXNz` decodes to `user:pass`, which is
then passed through Django's authentication backends.


## SessionAuthentication

Authenticates the request from the Django session cookie set by the
login views in `django.contrib.auth`.

```python
from restflow.authentication import SessionAuthentication

class ProfileView(AsyncAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"id": request.user.id})
```

A request with a Bearer header takes the JWT path. A browser request
with a session cookie takes the session path. A request with neither
falls through to the anonymous user.

## TokenAuthentication

Token-based authentication backed by DRF's `authtoken` model. A
client sends `Authorization: Token <key>` and the authenticator
resolves the key to a User via async ORM.

```python
from restflow.authentication import TokenAuthentication
```

To use it, install DRF's authtoken app and run migrations.

```python
INSTALLED_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
]
```

```bash
python manage.py migrate
```

Tokens are issued and revoked through DRF's standard tooling. The
restflow class only changes the lookup path:
`Token.objects.select_related("user").aget(key=key)` instead of the
synchronous version. 

### Header format

The expected header is `Authorization: Token <key>`. The keyword is
case-insensitive but must match `self.keyword`, which defaults to
"Token". Subclass and set `keyword = "Bearer"` to use a different
prefix.


## RemoteUserAuthentication

Trusts the value at `request.META[header]` (default `REMOTE_USER`)
and resolves it to a User via Django's `RemoteUserBackend` or a
comparable backend.

```python
from restflow.authentication import RemoteUserAuthentication
```

## Combining authenticators

`authentication_classes` is a list. Each class is tried in order, and
the first one to return a non-None result wins. A common pattern is
to support both browser sessions and JWT bearer tokens on the same
view.

```python
from rest_framework.permissions import IsAuthenticated

from restflow.authentication import JWTAuthentication, SessionAuthentication
from restflow.views import AsyncAPIView


class ProfileView(AsyncAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"id": request.user.id})
```

A request without an Authorization header skips
`JWTAuthentication`, falls through to `SessionAuthentication`, and
authenticates from the session cookie. A request with a Bearer
token takes the JWT path.


## Writing a custom authenticator

Subclass `BaseAuthentication` and implement `aauthenticate`. The
return value is the same as DRF: a `(user, auth)` tuple on
success, None when the request is not addressed to this
authenticator, or `AuthenticationFailed` when the header was meant
for this authenticator but is invalid.

```python
from rest_framework import exceptions

from restflow.authentication import BaseAuthentication


class HmacAuthentication(BaseAuthentication):
    async def aauthenticate(self, request):
        signature = request.headers.get("X-Signature")
        if signature is None:
            return None
        user = await self.aget_user_from_signature(request, signature)
        if user is None:
            msg = "Invalid signature."
            raise exceptions.AuthenticationFailed(msg)
        return (user, None)

    def authenticate_header(self, request):
        return 'HMAC realm="api"'

    async def aget_user_from_signature(self, request, signature):
        # Resolve the user from the signature, returning None when
        # the signature does not match any known user.
        ...
```

For mixed sync and async deployments, implement both the sync and
async hooks so the authenticator works under either dispatch.

```python
class HmacAuthentication(BaseAuthentication):
    def authenticate(self, request):
        # Sync path used by sync DRF views.
        ...

    async def aauthenticate(self, request):
        # Async path used by AsyncAPIView.
        ...
```

## Returning None vs raising

The dispatch loop tries the next authenticator only when an
authenticator returns None. Raising `AuthenticationFailed`
produces a 401. Use None when, The Authorization header is absent or invalid.



## Sync vs async surface

Each shipped class implements both `authenticate` (inherited from
DRF) and `aauthenticate` (added by restflow). The async hook is
preferred when present, so async views avoid the thread hop. Custom
authenticators that follow the same pattern are picked up
automatically.

| Class | Sync path | Async path |
| --- | --- | --- |
| BasicAuthentication | DRF default | django.contrib.auth.aauthenticate |
| SessionAuthentication | DRF default | request.\_request.auser, sync\_to\_async(enforce\_csrf) |
| TokenAuthentication | DRF default | Token.objects.select\_related("user").aget(...) |
| RemoteUserAuthentication | DRF default | django.contrib.auth.aauthenticate |
| JWTAuthentication | sync ORM + sync blacklist check | native async (User.objects.aget(...)) |

`JWTAuthentication` implements both surfaces natively. The sync
`authenticate` method performs the full token verification, blacklist
check, and user lookup using synchronous ORM queries. The async
`aauthenticate` method does the same via async ORM and async cache
calls. Both surfaces share the same logic and produce identical results.

## Examples

### Browser session plus JWT bearer

The browsable API uses Session, the API consumers
use JWT. Both are mounted on the same view list.

```python
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from restflow.authentication import (
    JWTAuthentication,
    SessionAuthentication,
)
from restflow.views import AsyncAPIView


class ProfileView(AsyncAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"id": request.user.id})
```

### Basic auth

Basic Authenticaiton Example:

```python
from restflow.authentication import BasicAuthentication
from restflow.permissions import IsAdminUser
from restflow.views import AsyncAPIView


class HealthView(AsyncAPIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAdminUser]

    async def get(self, request):
        return Response({"ok": True})
```

### REMOTE_USER from an SSO proxy

The proxy authenticates the user (Kerberos, SAML, OIDC) and forwards
the username in `X-Forwarded-User`. A custom subclass changes the
header name; the proxy strips client-supplied copies before
forwarding.

```python
from restflow.authentication import RemoteUserAuthentication


class ProxyRemoteUserAuthentication(RemoteUserAuthentication):
    header = "HTTP_X_FORWARDED_USER"


class DashboardView(AsyncAPIView):
    authentication_classes = [ProxyRemoteUserAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"user": request.user.username})
```

### Custom HMAC authenticator

A signature-based authenticator that reads `X-Signature`, looks up
the user by API key, verifies the HMAC, and returns the user. The
sync surface is implemented for compatibility with non-async views;
the async surface uses async ORM directly.

```python
import hmac
from hashlib import sha256

from rest_framework import exceptions

from restflow.authentication import BaseAuthentication


class HmacAuthentication(BaseAuthentication):

    def sync_lookup(self, api_key: str) -> tuple[Optional[User], Optional[str]]:
        ...
    
    def async_lookup(self, api_key: str) -> tuple[Optional[User], Optional[str]]:
        ...

    def authenticate(self, request):
        api_key, signature = self.extract(request)
        if api_key is None:
            return None
        user, secret = self.sync_lookup(api_key)
        if not user:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        self.verify(request, secret, signature)
        return (user, api_key)

    async def aauthenticate(self, request):
        api_key, signature = self.extract(request)
        if api_key is None:
            return None
        user, secret = await self.async_lookup(api_key)
        if not user:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        self.verify(request, secret, signature)
        return (user, api_key)

    def authenticate_header(self, request):
        return 'HMAC realm="api"'

    def extract(self, request):
        api_key = request.headers.get("X-Api-Key")
        signature = request.headers.get("X-Signature")
        if not api_key or not signature:
            return None, None
        return api_key, signature

    def verify(self, request, secret, signature):
        expected = hmac.new(secret.encode(), request.body, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise exceptions.AuthenticationFailed("Bad signature.")
```

The sync `sync_lookup` and the async `async_lookup` perform the
same work, one through the regular ORM and one through the async
ORM. Both versions check the API key against the database and return
a `(user, secret)` tuple.
