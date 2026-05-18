# JWT authentication

`JWTAuthentication` is the built-in JSON Web Token authenticator for
Restflow. It signs and verifies tokens via
[PyJWT](https://pyjwt.readthedocs.io/), looks up users with the async
ORM, and ships with pre-built obtain, refresh, and blacklist views.


JSON Web Tokens encode the user identity and an expiry timestamp into
a signed string. Clients send the access token on every request. When
the access token expires, the client exchanges a longer-lived refresh
token for a new access token without re-entering credentials.

The built-in implementation supports both sync and async paths and depends only on PyJWT.

Basic Configuration:

- An algorithm and a key pair (HMAC secret or RSA/ECDSA/EdDSA private
  and public keys).
- Lifetimes for access and refresh tokens.
- Whether to enable the blacklist for refresh-token revocation.

Defaults are: HS256 with a five-minute access lifetime,
a one-day refresh lifetime, the cache-backed blacklist enabled, and
refresh-token rotation turned on.

## Configuration

Set the JWT block under `RESTFLOW_SETTINGS` in Django settings. Only
`SIGNING_KEY` is mandatory, every other key has a working default.

```python
# settings.py
import secrets
from datetime import timedelta

RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": "<secret-key>",
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
        "ISSUER": "https://api.example.com",
        "AUDIENCE": "example-clients",
        "BLACKLIST_ENABLED": True,
        "ROTATE_REFRESH_TOKENS": True,
    },
}
```

For asymmetric algorithms, supply both `SIGNING_KEY` (the private key)
and `VERIFYING_KEY` (the public key).

## Settings reference

All keys live under `RESTFLOW_SETTINGS["JWT"]`. The defaults are
defined in `restflow/settings.py`.

| Setting | Default | Description |
| --- | --- | --- |
| SIGNING_KEY | None | Secret used to sign tokens. Required. For HMAC, this is the shared secret. For asymmetric algorithms, this is the private key (PEM string). |
| VERIFYING_KEY | None | Public key used to verify tokens when an asymmetric algorithm is selected. Falls back to SIGNING_KEY when unset, which is correct for HMAC and wrong for RSA/EC/EdDSA. |
| ALGORITHM | "HS256" | JWT signing algorithm. Must be one of the HMAC family (HS256, HS384, HS512) or asymmetric family (RS256, RS384, RS512, PS256, PS384, PS512, ES256, ES256K, ES384, ES512, EdDSA). The literal "none" is rejected. |
| ACCESS_TOKEN_LIFETIME | timedelta(minutes=5) | How long an access token remains valid after issuance. |
| REFRESH_TOKEN_LIFETIME | timedelta(days=1) | How long a refresh token remains valid after issuance. |
| ISSUER | None | Optional iss claim. When set, encode embeds it and decode requires it to match. |
| AUDIENCE | None | Optional aud claim. When set, encode embeds it and decode requires it to match. |
| USER_ID_CLAIM | "user_id" | Name of the JWT claim that carries the user identifier. |
| USER_ID_FIELD | "id" | Attribute on the User model used to look up the user. Must appear in USER_ID_FIELD_ALLOWLIST. |
| USER_ID_FIELD_ALLOWLIST | ("id", "pk", "uuid", "username", "email") | Tuple of allowed values for USER_ID_FIELD. Guards against accidental disclosure of sensitive attributes. |
| AUTH_HEADER_TYPES | ("Bearer",) | Tuple of accepted Authorization header prefixes (case-insensitive). The first entry is used in WWW-Authenticate. |
| BLACKLIST_ENABLED | True | When True, every authenticate call checks the blacklist for the token's JTI. |
| BLACKLIST_BACKEND | "restflow.authentication.jwt.CacheBlacklistBackend" | Dotted path, class object, or BlacklistBackend instance. |
| BLACKLIST_CACHE_ALIAS | "default" | Cache alias used by CacheBlacklistBackend. |
| BLACKLIST_ALLOW_LOCMEM | False | Set True to permit LocMemCache or DummyCache with CacheBlacklistBackend. Production deployments leave this False and use a shared cache. |
| ROTATE_REFRESH_TOKENS | True | When True, TokenRefreshView issues a new refresh token alongside the new access and blacklists the old one (when blacklisting is enabled). |
| LEEWAY | 0 | Clock skew tolerance in seconds applied to exp, nbf, and iat claims during decode. |
| CHECK_USER_IS_ACTIVE | True | When True, authentication fails if the user's is_active flag is False. |
| CHECK_REVOKE_TOKEN | False | When True, tokens carry a hash of the user's password. A password change invalidates all previously issued tokens without requiring a blacklist entry. |
| REVOKE_TOKEN_CLAIM | "hash_password" | Claim name used when CHECK_REVOKE_TOKEN is True. |
| USER_AUTHENTICATION_RULE | "restflow.authentication.jwt.default_user_authentication_rule" | Dotted path or callable that takes a user instance and returns True when the user may obtain tokens. The default rejects None and inactive users. |

## Signing keys and algorithms

The library accepts the HMAC family (HS256, HS384, HS512) and the
asymmetric families (RS, PS, ES, EdDSA).

### HMAC

For HMAC, set a single secret and use it for both signing and
verification. The default `VERIFYING_KEY=None` falls back to
`SIGNING_KEY`.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": secrets.token_urlsafe(64),
        "ALGORITHM": "HS256",
    },
}
```

### Asymmetric

For RSA, ECDSA, or EdDSA, supply both keys. The signing key is the
private key, the verifying key is the public key.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "ALGORITHM": "RS256",
        "SIGNING_KEY": open("/etc/restflow/jwt-private.pem").read(),
        "VERIFYING_KEY": open("/etc/restflow/jwt-public.pem").read(),
    },
}
```

The same private key both issues and verifies, but the verifying key
can be deployed without the private key on services that only need to
verify (eg: Servers in a microservice).

### Key shape validation

The library validates that the key shape matches the algorithm. A
PEM-looking string under HS256 raises `TokenError` at encode time
with a message that points at the configuration error.

### Algorithm rejection

Any value that is not in the HMAC or asymmetric whitelist is also refused.

## Token classes

`AccessToken` and `RefreshToken` are immutable dataclasses that hold
both the decoded payload and the raw signed string.

```python
from restflow.authentication import AccessToken, RefreshToken

access = AccessToken.for_user(user)
refresh = RefreshToken.for_user(user)

str(access)        # the signed token string
access.payload     # decoded claims (a dict)
access.jti         # JTI claim
access.exp         # expiry timestamp (int, seconds since epoch)
access.token_type  # "access"
```

Two constructors are available on each class.

- `for_user(user)` generates a fresh signed token whose user-id claim is
  read from `USER_ID_FIELD` on the user instance. Returns a new
  AccessToken or RefreshToken instance.
- `verify(raw)` decodes a raw token, validates the signature,
  expiry, issuer, audience, and token_type, and returns a token
  instance. Any failure raises `TokenError`.

`RefreshToken` adds three extras.

- `access_token` -- a property that generates a fresh access token
  carrying the same user-id claim.
- `rotate()` -- returns a fresh refresh token for the same user.
- `ablacklist()` -- async method that records the refresh token's
  JTI in the configured blacklist backend with a TTL equal to the
  token's remaining lifetime.


## Token shape and claims

A freshly issued token contains the following claims:

| Claim | Source | Notes |
| --- | --- | --- |
| token_type | "access" or "refresh" | Used at decode time to ensure the right class. |
| iat | int(now.timestamp()) | Issued-at, in seconds since epoch. |
| exp | int((now + lifetime).timestamp()) | Expiry, in seconds since epoch. |
| jti | secrets.token_urlsafe(16) | Per-token unique identifier; key into the blacklist. |
| {USER_ID_CLAIM} | getattr(user, USER_ID_FIELD) | The user identifier. |
| iss | `RESTFLOW_SETTINGS["JWT"]["ISSUER"]` | Present only when ISSUER is set. |
| aud | `RESTFLOW_SETTINGS["JWT"]["AUDIENCE"]` | Present only when AUDIENCE is set. |

Custom claims are not added by the library. Subclass `AccessToken`
and override `for_user` (or call `build_jwt_payload` and `encode_token`
directly) to add extra data.

## Authentication flow

Parses Authorization header, checks prefix against AUTH_HEADER_TYPES.
Validates header has exactly two parts, decodes token as UTF-8.
Verifies token via AccessToken.verify(); maps TokenError to AuthenticationFailed.
If blacklisting enabled, rejects blacklisted JTIs.
Fetches user by ID claim, confirms active, returns (user, token).


## Pre-built views

Three async views are shipped under `restflow.authentication`. None
of them require authentication or permissions themselves.

### TokenObtainView

POST 
`{username, password}`, 
returns 
`{access, refresh}`. Resolves
the user via `django.contrib.auth.aauthenticate`, so any custom
authentication backend in `AUTHENTICATION_BACKENDS` is honoured.

```http
POST /api/auth/token/
Content-Type: application/json

{"username": "khan", "password": "s3cret"}

HTTP/1.1 200 OK
{"access": "...", "refresh": "..."}
```

A wrong password or an inactive user raises `AuthenticationFailed`
with "No active account found with the given credentials".

### TokenRefreshView

POST `{refresh}`, returns `{access}` or `{access, refresh}` depending
on `ROTATE_REFRESH_TOKENS`. The refresh token must verify and must
not be blacklisted. When rotation is on and blacklisting is on, the
old refresh token is blacklisted before the response is sent.

```http
POST /api/auth/token/refresh/
Content-Type: application/json

{"refresh": "..."}

HTTP/1.1 200 OK
{"access": "...", "refresh": "..."}
```

### TokenBlacklistView

POST `{refresh}`, returns 204 No Content after blacklisting the
token's JTI. Useful for explicit logout flows that want to invalidate
the refresh token immediately rather than waiting for it to expire.

```http
POST /api/auth/token/blacklist/
Content-Type: application/json

{"refresh": "..."}

HTTP/1.1 204 No Content
```

## URL Routing

Mount the views under desired paths so client code can hit them.

```python
# urls.py
from django.urls import path

from restflow.authentication import (
    TokenBlacklistView,
    TokenObtainView,
    TokenRefreshView,
)

urlpatterns = [
    path("api/auth/token/", TokenObtainView.as_view(), name="token-obtain"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/auth/token/blacklist/", TokenBlacklistView.as_view(), name="token-blacklist"),
]
```

Client flow.

```bash
# Obtain
curl -X POST https://api.example.com/api/auth/token/ \
    -H "Content-Type: application/json" \
    -d '{"username": "khan", "password": "s3cret"}'
# -> {"access": "...", "refresh": "..."}

# Refresh (with rotation enabled)
curl -X POST https://api.example.com/api/auth/token/refresh/ \
    -H "Content-Type: application/json" \
    -d '{"refresh": "..."}'
# -> {"access": "...", "refresh": "..."}

# Logout
curl -X POST https://api.example.com/api/auth/token/blacklist/ \
    -H "Content-Type: application/json" \
    -d '{"refresh": "..."}'
# -> 204 No Content

# Authenticated request
curl https://api.example.com/api/profile/ \
    -H "Authorization: Bearer ..."
```

## Blacklist backends

A blacklist tracks refresh tokens that have been logged out or
rotated. An authenticator that finds a blacklisted JTI raises
`AuthenticationFailed`. Two backends ship out of the box, and a
third-party backend can be registered through `BLACKLIST_BACKEND`.

### CacheBlacklistBackend (default)

Stores entries in the Django cache configured by
`BLACKLIST_CACHE_ALIAS`. Each entry's TTL is set to the token's
remaining lifetime so revoked entries expire automatically without
manual cleanup.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "BLACKLIST_BACKEND": "restflow.authentication.jwt.CacheBlacklistBackend",
        "BLACKLIST_CACHE_ALIAS": "default",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
}
```

The backend refuses to start with `LocMemCache` or `DummyCache`
unless `BLACKLIST_ALLOW_LOCMEM` is True. In-process caches are unsafe
for blacklists in multi-worker deployments because revocations made
on one worker would not propagate to the others. 

### ModelBlacklistBackend

Persists revoked JTIs in the `BlacklistedToken` Django model. Use
this when a durable, queryable record is required, when audit trails
matter, or when a cache layer is not available.

```python
INSTALLED_APPS = [
    "rest_framework",
    "restflow.caching",
    "restflow.authentication",
    "restflow.authentication",
]

RESTFLOW_SETTINGS = {
    "JWT": {
        "BLACKLIST_BACKEND": "restflow.authentication.jwt.ModelBlacklistBackend",
    },
}
```

Run migrations after adding the app.

```bash
python manage.py migrate
```

The model has three columns: `jti` (CharField, unique, max length
128), `expires_at` (DateTimeField, indexed), and `created_at` (auto
timestamp). Rows persist until `cleanup_expired` is called, so plan a
periodic task to drain expired rows.

### Custom backend

A custom backend subclasses `BlacklistBackend` and implements the sync
and async method pairs.

```python
from restflow.authentication import BlacklistBackend


class RedisBlacklistBackend(BlacklistBackend):
    def blacklist(self, jti: str, *, expires_at: int) -> None:
        # Persist the JTI with a TTL of (expires_at - now).
        ...

    def is_blacklisted(self, jti: str) -> bool:
        # Return True when the JTI is present.
        ...

    async def ablacklist(self, jti: str, *, expires_at: int) -> None:
        # Async version of blacklist.
        ...

    async def ais_blacklisted(self, jti: str) -> bool:
        # Async version of is_blacklisted.
        ...
```

Point `BLACKLIST_BACKEND` at the dotted path, the class object, or an
instance.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "BLACKLIST_BACKEND": "myproject.auth.RedisBlacklistBackend",
    },
}
```

## BlacklistBackend interface

The interface exposes sync and async pairs for each operation.

```python
class BlacklistBackend:
    def blacklist(self, jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted until the given expiry timestamp."""

    def is_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is currently in the blacklist."""

    async def ablacklist(self, jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted until the given expiry timestamp."""

    async def ais_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is currently in the blacklist."""
```

Implementation notes for custom backends.

- `blacklist` receives the JTI and the absolute expiry timestamp
  (seconds since epoch). Store the entry until `expires_at`.
  Re-blacklisting the same JTI should be idempotent.
- `is_blacklisted` should return False quickly when the JTI is not
  present. The hot path runs once per authenticated request, so
  measure the latency before shipping a remote-call backend.
- The async variants mirror the sync ones using a native async client
  where possible.
- Errors should propagate. `ATokenBlacklist.is_blacklisted` returns
  False for an empty JTI but does not catch backend exceptions; a
  failed lookup raises and produces a 500.

## Refresh token rotation

When `ROTATE_REFRESH_TOKENS` is True (the default), every refresh
issues a new refresh token and blacklists the old one (when
blacklisting is enabled). The response carries both fields.

```json
{"access": "...", "refresh": "..."}
```

When False, only the access token is returned and the original
refresh token remains valid until it expires.

```json
{"access": "..."}
```

Rotation is the safer default. A stolen refresh token can mint access
tokens until it expires; rotation limits the attack window to one
refresh because the second use of the stolen token finds it on the
blacklist (or, with rotation but no blacklist, the legitimate user
will be the one whose refresh stops working, which is detectable).

When rotation and blacklisting are both off, the refresh token is a
long-lived bearer token. Avoid that combination unless the operational
context demands it.

## Custom user-id claim and field

By default the access token carries `{"user_id": user.id}`. To use a
different attribute, set both `USER_ID_CLAIM` (the JWT claim name)
and `USER_ID_FIELD` (the attribute on the User model).

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "USER_ID_CLAIM": "uid",
        "USER_ID_FIELD": "uuid",
    },
}
```

Tokens minted under this setting carry `{"uid": user.uuid}` and
authentication looks up the user via
`User.objects.aget(uuid=token["uid"])`.

`USER_ID_FIELD` must appear in `USER_ID_FIELD_ALLOWLIST`. The default
allowlist is `("id", "pk", "uuid", "username", "email")`. This guards
against accidentally embedding a sensitive attribute (such as a
hashed password column) into a signed token. To allow another field,
override the allowlist explicitly.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "USER_ID_CLAIM": "external_id",
        "USER_ID_FIELD": "external_id",
        "USER_ID_FIELD_ALLOWLIST": ("id", "pk", "uuid", "username", "email", "external_id"),
    },
}
```

Worked example: a project that issues UUID-keyed tokens and wants the
claim name to match the field name.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "USER_ID_CLAIM": "uuid",
        "USER_ID_FIELD": "uuid",
    },
}


class CustomUser(AbstractUser):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
```

The token now reads `{"uuid": "...", ...}` and the authenticator looks
up the user by UUID. Two stable identifiers (id and uuid) coexist on
the model; the JWT references the public-facing UUID.

## AUTH_HEADER_TYPES

`AUTH_HEADER_TYPES` is a tuple of accepted Authorization header
prefixes, checked case-insensitively. The default is `("Bearer",)`.
Multiple prefixes can be supplied to interoperate with legacy
clients.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "AUTH_HEADER_TYPES": ("Bearer", "JWT"),
    },
}
```

A request with `Authorization: bearer ...`, `Authorization: BEARER ...`,
or `Authorization: JWT ...` is accepted. The first entry in the
tuple is used in the `WWW-Authenticate` response header emitted on
401 responses.

## USER_AUTHENTICATION_RULE

`USER_AUTHENTICATION_RULE` is a callable that receives the user returned
by `django.contrib.auth.aauthenticate` and returns `True` when the user
is allowed to obtain tokens. The default implementation rejects `None`
and inactive users.

```python
def default_user_authentication_rule(user) -> bool:
    return user is not None and user.is_active
```

Supply a custom callable (or its dotted path) to enforce additional
gates such as email verification, MFA enrollment, or tenant membership.

```python
# myproject/auth.py

def require_verified_email(user) -> bool:
    return user is not None and user.is_active and user.email_verified


# settings.py
RESTFLOW_SETTINGS = {
    "JWT": {
        "USER_AUTHENTICATION_RULE": "myproject.auth.require_verified_email",
    },
}
```

A callable object or direct function reference works too.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "USER_AUTHENTICATION_RULE": require_verified_email,
    },
}
```

When the rule returns `False`, `TokenObtainView` raises
`AuthenticationFailed` with the message
"No active account found with the given credentials".

## Leeway and clock skew

`LEEWAY` is the number of seconds of tolerance applied to the exp,
nbf, and iat claims during decode. Setting a small leeway helps when
the API and its clients run on machines with imperfect clock sync.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "LEEWAY": 30,
    },
}
```

A token that expired three seconds ago is still accepted with a
30-second leeway. Keep this value small; large values widen the
window in which a stolen token remains usable. A common production
choice is 30 to 60 seconds.

## Issuer and audience

`ISSUER` and `AUDIENCE` map to the iss and aud JWT claims. When
either is set, encode adds the claim and decode requires it to match.
They default to None, which omits the claim from issued tokens and
skips the check at decode time.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "ISSUER": "https://api.example.com",
        "AUDIENCE": "example-clients",
    },
}
```

A token issued under one ISSUER will not validate when the API is
later reconfigured with a different ISSUER. Plan migrations
accordingly: roll out a verifier that accepts both the old and new
issuer (a custom subclass that overrides `decode_token`) before
swapping the default.

`AUDIENCE` is useful in microservice topologies where one issuer
mints tokens for multiple verifiers. Each verifier sets `AUDIENCE`
to the value embedded in tokens meant for it; tokens meant for a
different service fail the audience check.

## TokenError vs AuthenticationFailed

Two exception types are surfaced.

- `TokenError` (defined in `restflow.authentication.jwt`) is raised
  by `encode_token`, `decode_token`, `AccessToken.verify`, and
  `RefreshToken.verify` when the token cannot be encoded, decoded,
  or verified. Possible causes include expired tokens, missing or
  wrong signing key, wrong algorithm, wrong token_type, and issuer
  or audience mismatches.
- `rest_framework.exceptions.AuthenticationFailed` is raised by
  `JWTAuthentication.aauthenticate` and the pre-built views. It
  produces an HTTP 401 with a WWW-Authenticate header.

In the views and the authenticator, every `TokenError` is caught and
re-raised as `AuthenticationFailed` with the original message
preserved. The split lets internal code distinguish "this token is
broken" from "this request must be denied", which is useful when
writing custom views that do not want a 401 on every parse failure.

```python
from restflow.authentication import AccessToken, TokenError

try:
    token = AccessToken.verify(raw)
except TokenError as exc:
    # Programmatic handling: log, retry with a different key, etc.
    raise
```

## Error handling and 401 responses

When `AuthenticationFailed` propagates out of the authenticator,
`AsyncAPIView.ahandle_exception` calls
`self.get_authenticate_header(request)` and stores the result on
`exc.auth_header`. The default `JWTAuthentication.authenticate_header`
returns `'Bearer realm="api"'`. DRF's exception handler renders a 401
response with the header attached.

A view that does not have a usable `WWW-Authenticate` value forces
the status to 403. JWT-only views always have one because
`JWTAuthentication.authenticate_header` is set; no extra wiring is
needed.

The same applies to the pre-built views. Each one defines
`get_authenticate_header` so failed obtain or refresh requests
produce a 401 with `Bearer realm="api"`.

## Manual token issuance

Tokens can be minted outside the obtain view, for example after a
custom signup flow or for a service-to-service handshake.

```python
from rest_framework.response import Response

from restflow.authentication import AccessToken, RefreshToken
from restflow.views import AsyncAPIView


class SignupView(AsyncAPIView):
    authentication_classes = ()
    permission_classes = ()

    async def post(self, request):
        user = await create_user(request.data)
        return Response({
            "access": str(AccessToken.for_user(user)),
            "refresh": str(RefreshToken.for_user(user)),
        })
```

Verifying a token directly, without going through the authenticator.

```python
from restflow.authentication import AccessToken, TokenError

try:
    token = AccessToken.verify(raw)
except TokenError as exc:
    # Bad signature, expired, wrong type, etc.
    raise
```

Both are useful for service workers, pubsub consumers, and any code
path that handles tokens outside an HTTP request.

## Cleanup of expired blacklist rows

`ModelBlacklistBackend` writes rows that persist past the token's
expiry. The model exposes two cleanup helpers.

```python
from restflow.authentication.models import BlacklistedToken

# sync
deleted = BlacklistedToken.cleanup_expired()

# async
deleted = await BlacklistedToken.acleanup_expired()
```

Both delete every row whose `expires_at` is in the past and return
the deleted count. Wire them into a periodic task (Celery beat,
django-q, plain cron with `manage.py shell -c ...`) so the table does
not grow without bound. `CacheBlacklistBackend` does not need cleanup
because the cache TTL handles it.

## Working with multiple key generations

Rotating the signing key is occasionally necessary. The simplest
strategy:

1. Generate a new secret. Deploy verifiers that accept either the old
   or the new secret (a custom `decode_token` that tries both).
2. Once every verifier accepts both, swap the issuer over to the new
   secret.
3. After every existing token has expired, retire the old secret.

A custom `decode_token` looks like this.

```python
import jwt as pyjwt

from restflow.authentication.jwt import TokenError


def decode_token(raw, settings):
    for key in (settings.SIGNING_KEY_NEW, settings.SIGNING_KEY_OLD):
        try:
            return pyjwt.decode(raw, key, algorithms=[settings.ALGORITHM])
        except pyjwt.InvalidTokenError:
            continue
    raise TokenError("Token cannot be verified with any active key.")
```

Subclass `JWTAuthentication` and call this helper from
`aauthenticate` to use it. The shipped implementation does not bake
in multi-key support because the right semantics depend on the
operational context.

## Cross-service tokens

When several services share an authentication issuer, set `ISSUER`
on the issuer and on every verifier. Set `AUDIENCE` per-verifier so a
token cut for service A is rejected by service B.

A common topology:

- `auth.example.com` issues tokens. `ISSUER = "https://auth.example.com"`,
  `AUDIENCE` is set per request based on which service the token is
  intended for.
- `api.example.com` verifies tokens. `ISSUER = "https://auth.example.com"`,
  `AUDIENCE = "api.example.com"`.
- `reports.example.com` verifies tokens.
  `ISSUER = "https://auth.example.com"`,
  `AUDIENCE = "reports.example.com"`.

Asymmetric algorithms pair naturally with this setup: the issuer
holds the private key, the verifiers hold only the public key. A
compromised verifier cannot mint tokens.

## Example

A complete configuration for a production-shaped deployment.

```python
# settings.py
import secrets
from datetime import timedelta

INSTALLED_APPS = [
    "rest_framework",
    "restflow.caching",
    "restflow.authentication",
    "restflow.authentication",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    },
}

RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": secrets.token_urlsafe(64),
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
        "ISSUER": "https://api.example.com",
        "AUDIENCE": "example-clients",
        "AUTH_HEADER_TYPES": ("Bearer",),
        "BLACKLIST_ENABLED": True,
        "BLACKLIST_BACKEND": "restflow.authentication.jwt.CacheBlacklistBackend",
        "BLACKLIST_CACHE_ALIAS": "default",
        "ROTATE_REFRESH_TOKENS": True,
        "LEEWAY": 30,
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "restflow.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

```python
# urls.py
from django.urls import path

from restflow.authentication import (
    TokenBlacklistView,
    TokenObtainView,
    TokenRefreshView,
)

from myproject.views import ProfileView

urlpatterns = [
    path("api/auth/token/", TokenObtainView.as_view()),
    path("api/auth/token/refresh/", TokenRefreshView.as_view()),
    path("api/auth/token/blacklist/", TokenBlacklistView.as_view()),
    path("api/profile/", ProfileView.as_view()),
]
```

```python
# myproject/views.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from restflow.authentication import JWTAuthentication
from restflow.views import AsyncAPIView


class ProfileView(AsyncAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
        })
```

## Troubleshooting

### SIGNING_KEY is not set

The error is raised from `encode_token` when `SIGNING_KEY` is None.
Set the key in Django settings before issuing or verifying tokens.

### "Token has expired"

The exp claim is in the past after applying `LEEWAY`. Either issue a
fresh token (the typical client behaviour: catch 401, call
`/refresh/`, retry) or increase `LEEWAY` for clock-skew tolerance.

### "Wrong token type"

`AccessToken.verify` was called with a refresh token, or
`RefreshToken.verify` was called with an access token. The token
itself is fine; the call site needs to use the matching class.

### "User not found" or "User is inactive"

The token verifies but the database lookup fails. Either the user
was deleted between the token issue and the request, or the user has
been deactivated. Treat both as 401 and prompt the client to log in
again.

### CacheBlacklistBackend rejects LocMemCache

The default cache is in-process, which would let a revocation made
on one worker miss the others. Either configure a shared cache
(Redis or Memcached) or set `BLACKLIST_ALLOW_LOCMEM=True` for tests
where a single process is fine.

### "ALGORITHM='RS256' but VERIFYING_KEY=None"

Decode falls back to `SIGNING_KEY` (the private key) when
`VERIFYING_KEY` is unset, which works only because PyJWT can derive
the public key from a private RSA key. To deploy a verifier without
the private key, set `VERIFYING_KEY` to the PEM-encoded public key
explicitly.

### "Authorization header must be 'Bearer <token>'"

The header was present but had the wrong number of parts. Check the
client. Bearer tokens never contain spaces and the prefix must match
one of the entries in `AUTH_HEADER_TYPES`.
