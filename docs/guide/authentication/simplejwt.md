# SimpleJWT adapter

`SimpleJWTAuthentication` is an async-aware adapter for
[djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/).
It reuses simplejwt's token validation and adds an `aauthenticate`
hook that resolves the user via the async ORM, so simplejwt-based
projects plug cleanly into restflow's `AsyncAPIView` dispatch loop
without rewriting their issuance pipeline.

## When to use the adapter

The adapter exists for two scenarios.

- An existing project standardised on simplejwt, with token
  issuance, claim customisation, blacklisted tokens, and tooling
  already in place. The adapter avoids rewriting that code while
  bringing async-aware authentication to restflow async views.
- A project that needs a feature simplejwt has and the built-in does
  not, such as sliding tokens, the OutstandingToken model, or
  simplejwt-specific token rotation hooks.

For a new project that does not have those constraints, the built-in
[JWTAuthentication](jwt.md) is the simpler choice. It is async-native,
has fewer moving parts, and ships its own pre-built views.

## Installation

The adapter lives behind the `simplejwt` extra so projects that do
not need it are not forced to install simplejwt.

```bash
pip install drf-restflow[simplejwt]
# or
uv add 'drf-restflow[simplejwt]'
```

Add `rest_framework_simplejwt` to `INSTALLED_APPS` if simplejwt's own
apps are required (for example, when using the `token_blacklist`
app).

```python
INSTALLED_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "restflow.caching",
    "restflow.authentication",
]
```

The adapter raises `ImportError` at import time when simplejwt is not
installed. The error message names the install command so the failure
mode is obvious.

## Difference from the built-in

| Concern | Built-in JWTAuthentication | SimpleJWTAuthentication |
| --- | --- | --- |
| Settings block | RESTFLOW_SETTINGS["JWT"] | SIMPLE_JWT |
| Token classes | restflow's AccessToken, RefreshToken | simplejwt's AccessToken, RefreshToken, SlidingToken |
| Sliding tokens | Not supported | Supported |
| OutstandingToken model | Not present | Available via simplejwt's token_blacklist app |
| Pre-built views | TokenObtainView, TokenRefreshView, TokenBlacklistView | simplejwt's TokenObtainPairView, TokenRefreshView, TokenVerifyView, etc. |
| Async user lookup | Native | Added by the adapter |

The two implementations are not interchangeable at the token level. A
token issued by simplejwt cannot be verified by the built-in
verifier, and vice versa. Pick one for the lifetime of an unmigrated
client population.

## Usage

The class lives at
`restflow.authentication.simplejwt.SimpleJWTAuthentication` and is
not re-exported at the package root. Import it from the submodule.

```python
from restflow.authentication.simplejwt import SimpleJWTAuthentication
```

Wire it into a view exactly like any other authenticator.

```python
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from restflow.authentication.simplejwt import SimpleJWTAuthentication
from restflow.views import AsyncAPIView


class ProfileView(AsyncAPIView):
    authentication_classes = [SimpleJWTAuthentication]
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return Response({"id": request.user.id})
```

For project-wide configuration, set it as the default authenticator.

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "restflow.authentication.simplejwt.SimpleJWTAuthentication",
    ],
}
```

## Settings

The adapter reads simplejwt's own settings under `SIMPLE_JWT`. The
restflow `RESTFLOW_SETTINGS["JWT"]` block is ignored when the
adapter is in use.

```python
# settings.py
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": "...",
    "USER_ID_CLAIM": "user_id",
    "USER_ID_FIELD": "id",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
```

The full list of settings is documented in the
[simplejwt project](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html).
Every key under `SIMPLE_JWT` works exactly as it does under stock
simplejwt; the adapter only changes the user-lookup path.

## Async user lookup

Stock simplejwt resolves the user with the synchronous ORM, which
forces a thread hop on async views. The adapter swaps that for a
native async lookup.

```python
async def aget_user(self, validated_token):
    user_model = get_user_model()
    user_id = validated_token[_simplejwt_settings.USER_ID_CLAIM]
    user = await user_model.objects.aget(
        **{_simplejwt_settings.USER_ID_FIELD: user_id},
    )
    if not user.is_active:
        raise AuthenticationFailed("User is inactive.")
    return user
```

The lookup uses simplejwt's `USER_ID_FIELD` and `USER_ID_CLAIM`, so a
custom field configuration on simplejwt is honoured automatically.

## Mixed deployments

The adapter works alongside other authenticators. A common pattern:
JWT for API consumers, Session for the browsable API, both on the
same view.

```python
class ProfileView(AsyncAPIView):
    authentication_classes = [
        SimpleJWTAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [IsAuthenticated]
```

A request with a Bearer header takes the JWT path. A browser request
with a session cookie takes the session path. Order matters; the
list runs top to bottom and the first non-None tuple wins.

## Token issuance and refresh

For token issuance and refresh, mount simplejwt's own views.

```python
# urls.py
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

urlpatterns = [
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/token/verify/", TokenVerifyView.as_view()),
]
```

For an async-native obtain or refresh, switch to the built-in views
shipped under `restflow.authentication`. That requires committing to
the built-in token format, which is a breaking change for clients
holding simplejwt-issued tokens.

## Sliding tokens and other simplejwt features

The adapter inherits from simplejwt's `JWTAuthentication`, which
supports sliding tokens through `TOKEN_TYPE_CLAIM` and the related
settings. To use sliding tokens:

1. Configure `SIMPLE_JWT["AUTH_TOKEN_CLASSES"]` to include
   `rest_framework_simplejwt.tokens.SlidingToken`.
2. Mount `TokenObtainSlidingView` and `TokenRefreshSlidingView` on
   the URL conf.
3. The adapter validates sliding tokens through the same
   `get_validated_token` call.

The built-in restflow JWT sliding tokens is not implemented yet. 
