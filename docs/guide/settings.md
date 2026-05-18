# Settings

Every restflow knob lives under a single Django setting,
`RESTFLOW_SETTINGS`. The shape mirrors `restflow.settings.DEFAULTS`:
two top-level sections (`JWT` and `CACHE_SETTINGS`), each holding a
flat dict of keys.

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        # ...
    },
    "CACHE_SETTINGS": {
        # ...
    },
}
```

Settings are looked up lazily, cached on first read, and reset
automatically when Django emits a `setting_changed` signal for
`RESTFLOW_SETTINGS`. `override_settings` in tests works without
extra hooks.

```python
from restflow.settings import restflow_settings

restflow_settings.JWT.ALGORITHM
restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER
```

Reading an unknown key raises `AttributeError`. The lazy accessor
is the canonical import target; keep `from restflow.settings import
restflow_settings` rather than instantiating `RestflowSettings`
directly.

---

## JWT

JWT settings drive `restflow.authentication.JWTAuthentication`,
`TokenObtainView`, `TokenRefreshView`, `TokenBlacklistView`, and
the bundled blacklist backends.

Full schema with defaults:

```python
RESTFLOW_SETTINGS = {
    "JWT": {
        "SIGNING_KEY": None,
        "VERIFYING_KEY": None,
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ISSUER": None,
        "AUDIENCE": None,
        "USER_ID_CLAIM": "user_id",
        "USER_ID_FIELD": "id",
        "USER_ID_FIELD_ALLOWLIST": ("id", "pk", "uuid", "username", "email"),
        "AUTH_HEADER_TYPES": ("Bearer",),
        "BLACKLIST_ENABLED": True,
        "BLACKLIST_BACKEND": "restflow.authentication.jwt.CacheBlacklistBackend",
        "BLACKLIST_CACHE_ALIAS": "default",
        "BLACKLIST_ALLOW_LOCMEM": False,
        "ROTATE_REFRESH_TOKENS": True,
        "LEEWAY": 0,
        "CHECK_USER_IS_ACTIVE": True,
        "CHECK_REVOKE_TOKEN": False,
        "REVOKE_TOKEN_CLAIM": "hash_password",
        "USER_AUTHENTICATION_RULE": "restflow.authentication.jwt.default_user_authentication_rule",
    },
}
```

### SIGNING_KEY

Type: `str | bytes | None`. Default: `None`.

Secret used to sign tokens. For HS-family algorithms this is the
shared secret. For RS or ES algorithms this is the private key.
Setting `SIGNING_KEY` is required for tokens to be issued. The
default `None` raises `ImproperlyConfigured` on the first sign
attempt.

### VERIFYING_KEY

Type: `str | bytes | None`. Default: `None`.

Public key used to verify tokens. Optional for HS-family
algorithms (the signing key is also the verifying key). Required
for RS or ES algorithms. When unset, falls back to `SIGNING_KEY`.

### ALGORITHM

Type: `str`. Default: `"HS256"`.

JWT signing algorithm. Restflow validates the algorithm at startup
and rejects `none`. Supported values match `pyjwt`, including
`"HS256"`, `"HS384"`, `"HS512"`, `"RS256"`, `"RS384"`, `"RS512"`,
`"ES256"`, `"ES384"`, `"ES512"`.

### ACCESS_TOKEN_LIFETIME

Type: `datetime.timedelta`. Default: `timedelta(minutes=5)`.

Time before an access token's `exp` claim. Short lifetimes (5 to
15 minutes) are typical; refresh tokens cover the longer session.

### REFRESH_TOKEN_LIFETIME

Type: `datetime.timedelta`. Default: `timedelta(days=1)`.

Time before a refresh token's `exp` claim.

### ISSUER

Type: `str | None`. Default: `None`.

Value of the JWT `iss` claim. When set, encoded tokens carry the
claim and decoding rejects tokens with a different issuer.

### AUDIENCE

Type: `str | list[str] | None`. Default: `None`.

Value of the JWT `aud` claim. When set, encoded tokens carry the
claim and decoding rejects tokens whose audience does not match.

### USER_ID_CLAIM

Type: `str`. Default: `"user_id"`.

Claim name where the user identifier is stored on the token. The
authentication path reads this claim back to look up the user.

### USER_ID_FIELD

Type: `str`. Default: `"id"`.

Attribute on the user model that is encoded into `USER_ID_CLAIM`.
Common values are `"id"`, `"pk"`, `"uuid"`, `"username"`, or
`"email"`.

### USER_ID_FIELD_ALLOWLIST

Type: `tuple[str, ...]`. Default: `("id", "pk", "uuid", "username", "email")`.

Field names that `USER_ID_FIELD` is allowed to take. Reduces the
risk of pointing at a sensitive or non-unique field by accident.

### AUTH_HEADER_TYPES

Type: `tuple[str, ...]`. Default: `("Bearer",)`.

Authorization header prefixes accepted by `JWTAuthentication`. The
first entry is also the prefix used in challenge headers.

### BLACKLIST_ENABLED

Type: `bool`. Default: `True`.

Toggles blacklist checks. When `False`, `TokenBlacklistView` is
still callable but the check on incoming tokens is skipped.

### BLACKLIST_BACKEND

Type: `str`. Default: `"restflow.authentication.jwt.CacheBlacklistBackend"`.

Dotted path to the blacklist backend class.
`CacheBlacklistBackend` stores revoked token IDs in Django's cache
framework. `restflow.authentication.jwt.ModelBlacklistBackend`
stores them in the database via the bundled `BlacklistedToken`
model and survives cache flushes.

### BLACKLIST_CACHE_ALIAS

Type: `str`. Default: `"default"`.

Django cache alias used by `CacheBlacklistBackend`. Useful when a
dedicated redis instance backs the blacklist.

### BLACKLIST_ALLOW_LOCMEM

Type: `bool`. Default: `False`.

`CacheBlacklistBackend` rejects `LocMemCache` by default since
in-memory caches are per-process and cannot share state across
workers. Set to `True` to allow it in tests or single-process
deployments.

### ROTATE_REFRESH_TOKENS

Type: `bool`. Default: `True`.

When `True`, `TokenRefreshView` issues a new refresh token along
with the access token and blacklists the previous refresh token
(when `BLACKLIST_ENABLED`). When `False`, the same refresh token
keeps working until it expires.

### LEEWAY

Type: `int | float | datetime.timedelta`. Default: `0`.

Seconds of clock skew allowed when comparing `exp` and `nbf`
claims. Forwarded to `pyjwt` as the `leeway` argument.

### CHECK_USER_IS_ACTIVE

Type: `bool`. Default: `True`.

When `True`, the default authentication rule rejects users whose
`is_active` is `False`. Set to `False` to allow inactive users
through the authentication step (rarely the right call).

### CHECK_REVOKE_TOKEN

Type: `bool`. Default: `False`.

When `True`, every authenticated request compares
`REVOKE_TOKEN_CLAIM` on the token against a value derived from
the user. A mismatch fails authentication. The bundled rule hashes
the user's password, so changing the password invalidates every
issued token without populating the blacklist.

### REVOKE_TOKEN_CLAIM

Type: `str`. Default: `"hash_password"`.

Claim name used by `CHECK_REVOKE_TOKEN`. The default checks a
hash of the user's password.

### USER_AUTHENTICATION_RULE

Type: `str`. Default: `"restflow.authentication.jwt.default_user_authentication_rule"`.

Dotted path to a callable that takes a user instance and returns
`True` when authentication should succeed. Plug a custom callable
in to enforce additional gates (verified email, MFA, tenant
membership).

---

## CACHE_SETTINGS

`CACHE_SETTINGS` drives `cache_result`, key construction, and the
invalidation pipeline.

Full schema with defaults:

```python
RESTFLOW_SETTINGS = {
    "CACHE_SETTINGS": {
        "MAX_KEY_SUFFIX_LENGTH": 250,
        "HASH_SUFFIX_ON_OVERFLOW": False,
        "KEY_HASH_ALGORITHM": "sha256",
        "DEFAULT_DISPATCHER": "inline",
        "DISPATCHER_RAISE_EXCEPTION": False,
        "DISPATCHER_SETTINGS": {
            "celery": {
                "TASK_NAME": "restflow.caching.tasks.task_run_cache_rules",
                "QUEUE": None,
                "RAISE_EXCEPTION": None,
            },
            "threadpool": {
                "MAX_WORKERS": 4,
                "RAISE_EXCEPTION": None,
            },
            "django_rq": {
                "QUEUE": "default",
                "FUNCTION_PATH": "restflow.caching.tasks.run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "dramatiq": {
                "QUEUE": "default",
                "ACTOR_NAME": "restflow.task_run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "django_q": {
                "CLUSTER": None,
                "GROUP": None,
                "FUNCTION_PATH": "restflow.caching.tasks.run_cache_rules",
                "RAISE_EXCEPTION": None,
            },
            "asyncio": {
                "RAISE_EXCEPTION": None,
            },
            "inline": {
                "RAISE_EXCEPTION": None,
            },
        },
    },
}
```

### MAX_KEY_SUFFIX_LENGTH

Type: `int`. Default: `250`.

Maximum length, in characters, of the cache-key suffix before
overflow handling kicks in. Suffixes longer than this are either
truncated or replaced with their hash, depending on
`HASH_SUFFIX_ON_OVERFLOW`. `KeyConstructor.Meta.max_key_suffix_length`
overrides this for one constructor.

### HASH_SUFFIX_ON_OVERFLOW

Type: `bool`. Default: `False`.

When `True`, suffixes longer than `MAX_KEY_SUFFIX_LENGTH` are
replaced with the hex digest produced by `KEY_HASH_ALGORITHM`.
When `False`, they are truncated.
`KeyConstructor.Meta.hash_suffix_on_overflow` overrides this for
one constructor.

### KEY_HASH_ALGORITHM

Type: `str` (hashlib name) or `Callable[[str], str]`. Default: `"sha256"`.

Algorithm used by `restflow.caching.hashing.hash_string`. Either a
`hashlib` name (`"sha256"`, `"blake2b"`, `"md5"`) or a callable
that takes a string and returns its hex digest. Changing this
invalidates every existing cache entry; bump
`KeyConstructor.Meta.version` for a clean cutover.

### DEFAULT_DISPATCHER

Type: `str`. Default: `"inline"`.

Name of the dispatcher used by an `InvalidationRule` that does
not pass `dispatcher=` itself. Bundled values are `"inline"`,
`"threadpool"`, `"asyncio"`, `"celery"`, `"django_rq"`,
`"django_q"`, `"dramatiq"`. Custom dispatchers registered through
`register_dispatcher` are also valid.

### DISPATCHER_RAISE_EXCEPTION

Type: `bool`. Default: `False`.

Global default for whether the worker-side entry re-raises
framework-level errors so brokers can retry or dead-letter, or
logs and swallows them. The resolution order, highest priority
first:

1. `InvalidationRule.raise_exception`.
2. The per-dispatcher `RAISE_EXCEPTION` entry under
   `DISPATCHER_SETTINGS`.
3. `DISPATCHER_RAISE_EXCEPTION`.

Per-rule errors raised inside the registry's per-rule application
path are always logged and swallowed regardless of this flag.

### DISPATCHER_SETTINGS

Type: `dict[str, dict[str, Any]]`. Default: as shown above.

Per-dispatcher defaults, keyed by dispatcher `name`. Each
`Dispatcher` subclass reads its own block and merges it under any
per-rule `dispatcher_config={...}`.

#### celery

| Key | Type | Default | Effect |
|---|---|---|---|
| `TASK_NAME` | `str` | `"restflow.caching.tasks.task_run_cache_rules"` | Celery task name to call. The bundled task lives in `restflow.caching.tasks` and is decorated as `@shared_task`. |
| `QUEUE` | `str \| None` | `None` | Celery queue routing key. `None` uses the worker's default queue. |
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. Falls back to `DISPATCHER_RAISE_EXCEPTION`. |

#### threadpool

| Key | Type | Default | Effect |
|---|---|---|---|
| `MAX_WORKERS` | `int` | `4` | Size of the thread pool that runs invalidation tasks. |
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. |

#### django_rq

| Key | Type | Default | Effect |
|---|---|---|---|
| `QUEUE` | `str` | `"default"` | django-rq queue name. |
| `FUNCTION_PATH` | `str` | `"restflow.caching.tasks.run_cache_rules"` | Dotted path to the worker entry the queue calls. |
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. |

#### dramatiq

| Key | Type | Default | Effect |
|---|---|---|---|
| `QUEUE` | `str` | `"default"` | dramatiq queue name. |
| `ACTOR_NAME` | `str` | `"restflow.task_run_cache_rules"` | dramatiq actor name registered on workers. |
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. |

#### django_q

| Key | Type | Default | Effect |
|---|---|---|---|
| `CLUSTER` | `str \| None` | `None` | django-q cluster name. `None` uses the default cluster. |
| `GROUP` | `str \| None` | `None` | django-q task group, useful for grouping invalidation tasks in the admin. |
| `FUNCTION_PATH` | `str` | `"restflow.caching.tasks.run_cache_rules"` | Dotted path to the worker entry. |
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. |

#### asyncio

| Key | Type | Default | Effect |
|---|---|---|---|
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. The dispatcher schedules tasks on the running event loop and falls back to the sync worker when no loop is running. |

#### inline

| Key | Type | Default | Effect |
|---|---|---|---|
| `RAISE_EXCEPTION` | `bool \| None` | `None` | Per-dispatcher override. The inline dispatcher runs invalidation in the request thread, so `True` propagates errors to the caller. |

---

## Reading a setting

```python
from restflow.settings import restflow_settings

restflow_settings.JWT.ALGORITHM
restflow_settings.CACHE_SETTINGS.DEFAULT_DISPATCHER
restflow_settings.CACHE_SETTINGS.DISPATCHER_SETTINGS.celery.QUEUE
```

`restflow_settings` is the process-wide accessor. Nested sections
are themselves `RestflowSettings` instances, so attribute access
works all the way down. Reading an unknown key raises
`AttributeError`.

`restflow_settings.to_dict()` returns the resolved settings as a
plain dict, useful for diagnostics and management commands.

## Overriding in tests

```python
from django.test.utils import override_settings


@override_settings(
    RESTFLOW_SETTINGS={
        "JWT": {"ACCESS_TOKEN_LIFETIME": timedelta(seconds=30)},
        "CACHE_SETTINGS": {"DEFAULT_DISPATCHER": "celery"},
    },
)
def test_short_token():
    ...
```

Only the keys passed in `override_settings` are overridden, but
the override replaces the dict at the section level. Pass the full
section when only one key is being changed and the rest of the
defaults are also wanted.

The lazy accessor reacts to `setting_changed` automatically, so
the override takes effect on the next attribute read. There is no
need to call `restflow_settings.reload()` from tests.
