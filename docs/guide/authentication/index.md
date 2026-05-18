# Authentication

Restflow ships an async-compatible authentication layer that is built on top of
DRF's authentication classes and adds a built-in JSON Web Token
implementation. Every authenticator exposes an `aauthenticate`
coroutine so the async dispatch loop in `AsyncAPIView` does not have
to fall back to a thread on every request, and every shipped class
also keeps the synchronous `authenticate` hook so existing DRF views
continue to work unchanged.

Restflow adds async-varients for all the authentication classes. There is an `aauthenticate(request)` coroutine alongside the sync `authenticate(request)`.

## Features

- **Async-native classes.** Every authenticator implements async varaints of their    sync `authenticate` method, named as `aauthenticate`.
- **A built-in JWT implementation.** The `restflow.authentication.jwt`
  module ships an async-native bearer-token authenticator with a
  configurable signing algorithm, blacklist support, refresh-token
  rotation, and pre-built obtain, refresh, and blacklist views. PyJWT
  is the only dependency.
- **An adapter for djangorestframework-simplejwt.** Projects already
  standardised on simplejwt can keep their issuance pipeline and gain
  async-aware authentication by importing
  `SimpleJWTAuthentication` from the `simplejwt` extra.

## Choosing an authenticator

- For a new API that needs JSON Web Tokens, pick `JWTAuthentication`.
  It is async-native, has only PyJWT as a dependency, and ships pre-
  built obtain, refresh, and blacklist views.
- For an existing project on `djangorestframework-simplejwt`, pick
  `SimpleJWTAuthentication`.
- For browser sessions, pick `SessionAuthentication`.
- For machine-to-machine API tokens stored as DRF authtokens, pick
  `TokenAuthentication`.
- For SSO setups, pick `RemoteUserAuthentication`.
- `BasicAuthentication` is fine for tests and admin tooling but is
  not recommended for production traffic because credentials travel
  on every request.

## Combining authenticators

`authentication_classes` is a list. Each class is tried in order, and
the first one to return a non-None result wins.

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


## Built-in JWT

The built-in JWT authenticator is the recommended choice for new
projects. It depends only on PyJWT, supports HMAC and asymmetric
algorithms, ships with a configurable issuer, audience, and leeway,
and provides three pre-built views plus two blacklist backends. The
settings block lives at `RESTFLOW_SETTINGS["JWT"]`.

See the dedicated [JWT authentication](jwt.md) page for the full
guide, including the settings reference, the token classes, the
authentication flow, refresh-token rotation, custom blacklist
backends, and worked configurations.

## DRF parity classes

`BasicAuthentication`, `SessionAuthentication`, `TokenAuthentication`,
and `RemoteUserAuthentication` mirror their DRF counterparts. Sync
behaviour is identical, so an existing DRF project can swap imports
without changing logic.

See [Built-in authenticators](built-in.md)

## SimpleJWT adapter

For projects already standardised on `djangorestframework-simplejwt`,
the adapter at
`restflow.authentication.simplejwt.SimpleJWTAuthentication` plugs
simplejwt's token validation into restflow's async dispatch without
rewriting code. Install with
`pip install drf-restflow[simplejwt]` or
`uv add 'drf-restflow[simplejwt]'`.

See [SimpleJWT adapter](simplejwt.md) for details.

## Inactive users and missing rows

Every shipped authenticator checks `user.is_active`. An inactive user
raises `AuthenticationFailed` with a localized message rather than
returning a tuple. This matches DRF's behaviour and means the standard
permission classes never receive an inactive user.

Missing user rows (a JWT carrying a user_id that no longer exists, a
TokenAuthentication key whose user has been deleted, a Basic
credential whose username is not in the database) also raise
`AuthenticationFailed`. The text of the exception varies by
authenticator; the status code is always 401.


## Project-wide configuration

DRF's `DEFAULT_AUTHENTICATION_CLASSES` setting still applies. Set the
default authenticators at the project level and override on
individual views as needed.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "restflow.authentication.JWTAuthentication",
        "restflow.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
```

## Reference pages

- [JWT authentication](jwt.md) -- the built-in implementation,
  settings reference, blacklist backends, refresh rotation.
- [Built-in authenticators](built-in.md) -- DRF parity classes with
  every failure mode documented.
- [SimpleJWT adapter](simplejwt.md) -- async-aware adapter for the
  djangorestframework-simplejwt package.
- [API: JWT](../../api/authentication/jwt.md) -- generated reference
  for the JWT module.
- [API: JWT views](../../api/authentication/jwt-views.md) -- generated
  reference for TokenObtainView, TokenRefreshView, and
  TokenBlacklistView.
- [API: Blacklist backends](../../api/authentication/blacklist.md) --
  generated reference for the two shipped backends.
- [API: SimpleJWT adapter](../../api/authentication/simplejwt.md)
- [API: Built-in authenticators](../../api/authentication/built-in.md)
