import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import get_authorization_header

from restflow.authentication.authentication import BaseAuthentication
from restflow.settings import restflow_settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
BLACKLIST_CACHE_PREFIX = "restflow:jwt:bl:"
HMAC_ALGORITHMS = ("HS256", "HS384", "HS512")
ASYMMETRIC_ALGORITHMS = (
    "RS256", "RS384", "RS512",
    "PS256", "PS384", "PS512",
    "ES256", "ES256K", "ES384", "ES512",
    "EdDSA",
)
ALLOWED_ALGORITHMS = HMAC_ALGORITHMS + ASYMMETRIC_ALGORITHMS


LOCAL_CACHE_BACKEND_PATHS = (
    "django.core.cache.backends.locmem.LocMemCache",
    "django.core.cache.backends.dummy.DummyCache",
)

class TokenError(Exception):
    """Raised when a JWT cannot be decoded, has expired, or fails verification."""


def get_jwt_settings():
    return restflow_settings.JWT


def get_verifying_key():
    s = get_jwt_settings()
    return s.VERIFYING_KEY or s.SIGNING_KEY


def get_now_time() -> datetime:
    # Using custom datetime.now with utc, instead of django's timezone.now
    # Since custom timezone for a django config can be different, causing corner cases.
    return datetime.now(tz=UTC)


def validate_algorithm(algorithm: str) -> None:
    if algorithm == "none":
        # Algorithm should not be none, very very unsafe.
        msg = _(
            "RESTFLOW_SETTINGS['JWT']['ALGORITHM'] is 'none'. "
            "The 'none' algorithm disables signature verification and is unsafe."
        )
        raise TokenError(msg)
    if algorithm not in ALLOWED_ALGORITHMS:
        msg = _(
            "RESTFLOW_SETTINGS['JWT']['ALGORITHM']={algorithm!r} is not supported. "
            "Choose one of {allowed}."
        ).format(algorithm=algorithm, allowed=", ".join(ALLOWED_ALGORITHMS))
        raise TokenError(msg)


def default_user_authentication_rule(user) -> bool:
    """Returns True when the user may authenticate. Default rule rejects None and inactive users."""
    return user is not None and user.is_active


def get_user_authentication_rule():
    """Resolves the configured USER_AUTHENTICATION_RULE callable, importing dotted-path strings."""
    rule = get_jwt_settings().USER_AUTHENTICATION_RULE
    if isinstance(rule, str):
        return import_string(rule)
    return rule


def validate_signing_key_shape(algorithm: str, key) -> None:
    if key is None:  # pragma: no cover
        # encode_token must reject None earlier, otherwise chaos
        return
    if algorithm in HMAC_ALGORITHMS:
        rendered = key if isinstance(key, str) else (
            key.decode("latin-1", errors="replace")
            if isinstance(key, (bytes, bytearray))
            else None
        )
        if rendered is not None and "-----BEGIN " in rendered:
            msg = _(
                "RESTFLOW_SETTINGS['JWT']['ALGORITHM']={algorithm!r} expects an HMAC secret "
                "but SIGNING_KEY looks like a PEM-encoded asymmetric key. "
                "Use a random secret (e.g. secrets.token_urlsafe(64)) or switch to an asymmetric algorithm."
            ).format(algorithm=algorithm)
            raise TokenError(msg)


def get_blacklisted_token_model():
    """Lazy import of the BlacklistedToken model.

    Kept lazy so jwt.py can be imported before Django app loading
    finishes; the model only resolves when the ModelBlacklistBackend
    is actually used.
    """
    from restflow.authentication.models import BlacklistedToken  # noqa: PLC0415
    return BlacklistedToken


def resolve_token_blacklist_backend(spec) -> "BlacklistBackend":
    # Either User Defined or Default or Set via Settings.
    # Must always return a object of BlacklistBackend, not a class.
    if isinstance(spec, BlacklistBackend):
        return spec
    if isinstance(spec, type) and issubclass(spec, BlacklistBackend):
        return spec()
    if isinstance(spec, str):
        cls = import_string(spec)
        return cls()
    return CacheBlacklistBackend()


def get_token_blacklist_backend() -> "BlacklistBackend":
    return resolve_token_blacklist_backend(get_jwt_settings().BLACKLIST_BACKEND)


def encode_token(payload: dict) -> str:
    """Encode a payload dict as a signed JWT using the configured signing key and algorithm."""
    s = get_jwt_settings()
    if s.SIGNING_KEY is None:
        msg = _(
            "RESTFLOW_SETTINGS['JWT']['SIGNING_KEY'] is not set. "
            "Configure a signing key before issuing or verifying tokens."
        )
        raise TokenError(msg)
    validate_algorithm(s.ALGORITHM)
    validate_signing_key_shape(s.ALGORITHM, s.SIGNING_KEY)
    return pyjwt.encode(payload, s.SIGNING_KEY, algorithm=s.ALGORITHM)


def decode_token(raw: str) -> dict:
    """Decode and verify a JWT. Raises TokenError on any failure."""
    s = get_jwt_settings()
    validate_algorithm(s.ALGORITHM)
    validate_signing_key_shape(s.ALGORITHM, get_verifying_key())
    options = {"require": ["exp", "iat"]}
    try:
        return pyjwt.decode(
            raw,
            get_verifying_key(),
            algorithms=[s.ALGORITHM],
            options=options,
            issuer=s.ISSUER,
            audience=s.AUDIENCE,
            leeway=s.LEEWAY,
        )
    except pyjwt.ExpiredSignatureError as exc:
        msg = _("Token has expired.")
        raise TokenError(msg) from exc
    except pyjwt.InvalidTokenError as exc:
        msg = str(exc) or _("Token is invalid.")
        raise TokenError(msg) from exc



def validate_user_id_field(user_id_field: str, allowlist) -> None:
    if user_id_field not in allowlist:
        msg = _(
            "RESTFLOW_SETTINGS['JWT']['USER_ID_FIELD']={user_id_field!r} "
            "is not in USER_ID_FIELD_ALLOWLIST={allowlist!r}. "
            "Token claims must reference a stable, non-sensitive identifier "
            "(such as id, pk, uuid, username, email)."
        ).format(user_id_field=user_id_field, allowlist=tuple(allowlist))
        raise TokenError(msg)


def get_password_hash(password: str) -> str:
    """Return a stable fingerprint of the user's hashed password for revoke-token claims."""
    return hashlib.md5(password.encode()).hexdigest()


def build_jwt_payload(user, *, token_type: str, lifetime: timedelta) -> dict:
    s = get_jwt_settings()
    validate_user_id_field(s.USER_ID_FIELD, s.USER_ID_FIELD_ALLOWLIST)
    now = get_now_time()
    payload = {
        "token_type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": secrets.token_urlsafe(16),
        s.USER_ID_CLAIM: getattr(user, s.USER_ID_FIELD),
    }
    if s.ISSUER is not None:
        payload["iss"] = s.ISSUER
    if s.AUDIENCE is not None:
        payload["aud"] = s.AUDIENCE
    if s.CHECK_REVOKE_TOKEN:
        payload[s.REVOKE_TOKEN_CLAIM] = get_password_hash(user.password)
    return payload

@dataclass(frozen=True)
class _Token:
    """Holds the decoded payload and the raw signed string for a JWT."""

    payload: dict = field(default_factory=dict)
    raw: str = ""
    token_type: str = ""

    def __str__(self) -> str:
        return self.raw

    @property
    def jti(self) -> str:
        return self.payload.get("jti", "")

    @property
    def exp(self) -> int:
        return int(self.payload.get("exp", 0))


class AccessToken(_Token):
    """
    Short-lived bearer token sent on every authenticated request.
    """

    @classmethod
    def for_user(cls, user) -> "AccessToken":
        """Returns a freshly signed access token for the given user."""
        s = get_jwt_settings()
        payload = build_jwt_payload(
            user, token_type=ACCESS_TOKEN_TYPE, lifetime=s.ACCESS_TOKEN_LIFETIME
        )
        return cls(payload=payload, raw=encode_token(payload), token_type=ACCESS_TOKEN_TYPE)

    @classmethod
    def verify(cls, raw: str) -> "AccessToken":
        """Decodes and validates the raw token, raising TokenError on any failure."""
        payload = decode_token(raw)
        if payload.get("token_type") != ACCESS_TOKEN_TYPE:
            msg = _("Wrong token type, expected {expected!r}.").format(expected=ACCESS_TOKEN_TYPE)
            raise TokenError(msg)
        return cls(payload=payload, raw=raw, token_type=ACCESS_TOKEN_TYPE)


class RefreshToken(_Token):
    """
    Long-lived token used to mint new access tokens without forcing the user to log in again.
    """

    @classmethod
    def for_user(cls, user) -> "RefreshToken":
        """Returns a freshly signed refresh token for the given user."""
        s = get_jwt_settings()
        payload = build_jwt_payload(
            user, token_type=REFRESH_TOKEN_TYPE, lifetime=s.REFRESH_TOKEN_LIFETIME
        )
        return cls(payload=payload, raw=encode_token(payload), token_type=REFRESH_TOKEN_TYPE)

    @classmethod
    def verify(cls, raw: str) -> "RefreshToken":
        """Decodes and validates the raw refresh token, raising TokenError on any failure."""
        payload = decode_token(raw)
        if payload.get("token_type") != REFRESH_TOKEN_TYPE:
            msg = _("Wrong token type, expected {expected!r}.").format(expected=REFRESH_TOKEN_TYPE)
            raise TokenError(msg)
        return cls(payload=payload, raw=raw, token_type=REFRESH_TOKEN_TYPE)

    @property
    def access_token(self) -> AccessToken:
        """Returns a fresh access token derived from this refresh token's user claim."""
        return self._mint(ACCESS_TOKEN_TYPE)

    def rotate(self) -> "RefreshToken":
        """Returns a fresh refresh token derived from this token's user claim."""
        return self._mint(REFRESH_TOKEN_TYPE)

    def _mint(self, token_type: str):
        s = get_jwt_settings()
        now = get_now_time()
        lifetime = (
            s.ACCESS_TOKEN_LIFETIME
            if token_type == ACCESS_TOKEN_TYPE
            else s.REFRESH_TOKEN_LIFETIME
        )
        payload = {
            "token_type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + lifetime).timestamp()),
            "jti": secrets.token_urlsafe(16),
            s.USER_ID_CLAIM: self.payload[s.USER_ID_CLAIM],
        }
        if s.ISSUER is not None:
            payload["iss"] = s.ISSUER
        if s.AUDIENCE is not None:
            payload["aud"] = s.AUDIENCE
        if s.CHECK_REVOKE_TOKEN and s.REVOKE_TOKEN_CLAIM in self.payload:
            payload[s.REVOKE_TOKEN_CLAIM] = self.payload[s.REVOKE_TOKEN_CLAIM]
        cls = AccessToken if token_type == ACCESS_TOKEN_TYPE else RefreshToken
        return cls(payload=payload, raw=encode_token(payload), token_type=token_type)

    def blacklist(self) -> None:
        """Adds this token's JTI to the configured blacklist backend."""
        ATokenBlacklist.blacklist(self.jti, expires_at=self.exp)

    async def ablacklist(self) -> None:
        """Adds this token's JTI to the configured blacklist backend."""
        await ATokenBlacklist.ablacklist(self.jti, expires_at=self.exp)


class BlacklistBackend:
    """
    Abstract base for JWT blacklist storage.
    Subclasses implement blacklist and is_blacklisted (sync) plus ablacklist,
    ais_blacklisted, and add (async), selected via the JWT BLACKLIST_BACKEND setting.
    """

    def blacklist(self, jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted until the given expiry timestamp."""
        raise NotImplementedError

    def _is_blacklisted_sync(self, jti: str) -> bool:
        """Sync blacklist check for use in synchronous code paths."""
        raise NotImplementedError

    async def is_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is currently in the blacklist."""
        raise NotImplementedError

    async def ablacklist(self, jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted until the given expiry timestamp."""
        raise NotImplementedError

    async def ais_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is currently in the blacklist."""
        return await self.is_blacklisted(jti)

    async def add(self, jti: str, *, expires_at: int) -> None:
        """Alias for ablacklist."""
        await self.ablacklist(jti, expires_at=expires_at)



class CacheBlacklistBackend(BlacklistBackend):
    """
    Cache backed JWT blacklist using the configured Django cache.
    Entries are keyed by the token JTI and expire automatically when the token would have.
    """

    def __init__(self) -> None:
        self._verified = False

    @staticmethod
    def _key(jti: str) -> str:
        return f"{BLACKLIST_CACHE_PREFIX}{jti}"

    def _verify_backend(self) -> None:
        if self._verified:
            return
        s = get_jwt_settings()
        cache = caches[s.BLACKLIST_CACHE_ALIAS]
        backend_path = f"{type(cache).__module__}.{type(cache).__name__}"
        if backend_path in LOCAL_CACHE_BACKEND_PATHS and not s.BLACKLIST_ALLOW_LOCMEM:
            msg = (
                f"CacheBlacklistBackend cannot use {backend_path!r} because "
                "the cache is per-process. Tokens revoked on one worker will "
                "still be valid on other workers. Use Redis, Memcached, or "
                "another cross-process cache, or set "
                "RESTFLOW_SETTINGS['JWT']['BLACKLIST_ALLOW_LOCMEM']=True to opt in."
            )
            raise ImproperlyConfigured(msg)
        self._verified = True

    def blacklist(self, jti: str, *, expires_at: int) -> None:
        """Stores the JTI in the cache with a TTL equal to the token's remaining lifetime."""
        self._verify_backend()
        s = get_jwt_settings()
        cache = caches[s.BLACKLIST_CACHE_ALIAS]
        ttl = max(1, expires_at - int(get_now_time().timestamp()))
        cache.set(self._key(jti), True, timeout=ttl)

    def _is_blacklisted_sync(self, jti: str) -> bool:
        self._verify_backend()
        s = get_jwt_settings()
        cache = caches[s.BLACKLIST_CACHE_ALIAS]
        return bool(cache.get(self._key(jti), False))

    async def is_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is present in the cache."""
        self._verify_backend()
        s = get_jwt_settings()
        cache = caches[s.BLACKLIST_CACHE_ALIAS]
        return bool(await cache.aget(self._key(jti), False))

    async def ablacklist(self, jti: str, *, expires_at: int) -> None:
        """Stores the JTI in the cache with a TTL equal to the token's remaining lifetime."""
        self._verify_backend()
        s = get_jwt_settings()
        cache = caches[s.BLACKLIST_CACHE_ALIAS]
        ttl = max(1, expires_at - int(get_now_time().timestamp()))
        await cache.aset(self._key(jti), True, timeout=ttl)

    async def ais_blacklisted(self, jti: str) -> bool:
        """Returns True if the JTI is present in the cache."""
        return await self.is_blacklisted(jti)

    async def add(self, jti: str, *, expires_at: int) -> None:
        """Alias for ablacklist."""
        await self.ablacklist(jti, expires_at=expires_at)


class ModelBlacklistBackend(BlacklistBackend):
    """
    Django model backed JWT blacklist.
    Persists revoked JTIs in BlacklistedToken rows. Requires 'restflow.authentication' in INSTALLED_APPS.
    """

    def blacklist(self, jti: str, *, expires_at: int) -> None:
        """Inserts a BlacklistedToken row for the given JTI if one does not already exist."""
        BlacklistedToken = get_blacklisted_token_model()
        BlacklistedToken.objects.get_or_create(
            jti=jti,
            defaults={"expires_at": datetime.fromtimestamp(expires_at, tz=UTC)},
        )

    def _is_blacklisted_sync(self, jti: str) -> bool:
        BlacklistedToken = get_blacklisted_token_model()
        return BlacklistedToken.objects.filter(jti=jti).exists()

    async def is_blacklisted(self, jti: str) -> bool:
        """Returns True if a BlacklistedToken row exists for the given JTI."""
        BlacklistedToken = get_blacklisted_token_model()
        return await BlacklistedToken.objects.filter(jti=jti).aexists()

    async def ablacklist(self, jti: str, *, expires_at: int) -> None:
        """Inserts a BlacklistedToken row for the given JTI if one does not already exist."""
        BlacklistedToken = get_blacklisted_token_model()
        await BlacklistedToken.objects.aget_or_create(
            jti=jti,
            defaults={"expires_at": datetime.fromtimestamp(expires_at, tz=UTC)},
        )

    async def ais_blacklisted(self, jti: str) -> bool:
        """Returns True if a BlacklistedToken row exists for the given JTI."""
        return await self.is_blacklisted(jti)

    async def add(self, jti: str, *, expires_at: int) -> None:
        """Alias for ablacklist."""
        await self.ablacklist(jti, expires_at=expires_at)


class ATokenBlacklist:
    """
    Facade over the configured BlacklistBackend.
    Reads the backend setting on every call so runtime swaps and override_settings work as expected.
    """

    @staticmethod
    def blacklist(jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted using the configured backend."""
        get_token_blacklist_backend().blacklist(jti, expires_at=expires_at)

    @staticmethod
    def _sync_is_blacklisted(jti: str) -> bool:
        if not jti:
            return False
        return get_token_blacklist_backend()._is_blacklisted_sync(jti)

    @staticmethod
    async def is_blacklisted(jti: str) -> bool:
        """Returns True if the JTI is currently blacklisted."""
        if not jti:
            return False
        return await get_token_blacklist_backend().is_blacklisted(jti)

    @staticmethod
    async def add(jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted using the configured backend."""
        await get_token_blacklist_backend().add(jti, expires_at=expires_at)

    @staticmethod
    async def ablacklist(jti: str, *, expires_at: int) -> None:
        """Records the JTI as blacklisted using the configured backend."""
        await get_token_blacklist_backend().ablacklist(jti, expires_at=expires_at)

    @staticmethod
    async def ais_blacklisted(jti: str) -> bool:
        """Returns True if the JTI is currently blacklisted."""
        if not jti:
            return False
        return await get_token_blacklist_backend().is_blacklisted(jti)


class JWTAuthentication(BaseAuthentication):
    """
    Bearer token authentication using JSON Web Tokens.
    Validates signature, expiry, issuer, and audience via PyJWT, and looks up the user via async ORM.
    """

    www_authenticate_realm = "api"

    def authenticate(self, request):
        """Returns a (user, token) tuple for the bearer token in the Authorization header, or None when no token is supplied."""
        s = get_jwt_settings()
        header = get_authorization_header(request).split()
        accepted = [t.lower().encode() for t in s.AUTH_HEADER_TYPES]
        if not header or header[0].lower() not in accepted:
            return None
        if len(header) != 2:
            msg = _("Authorization header must be 'Bearer <token>'.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_authorization_header")
        try:
            raw = header[1].decode()
        except UnicodeError as exc:
            msg = _("Token contains invalid characters.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_token") from exc
        try:
            token = AccessToken.verify(raw)
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="invalid_token") from exc
        if s.BLACKLIST_ENABLED and ATokenBlacklist._sync_is_blacklisted(token.jti):
            msg = _("Token has been blacklisted.")
            raise exceptions.AuthenticationFailed(msg, code="token_blacklisted")
        user = self.get_user(token)
        return (user, token)

    async def aauthenticate(self, request):
        """Returns a (user, token) tuple for the bearer token in the Authorization header, or None when no token is supplied."""
        s = get_jwt_settings()
        header = get_authorization_header(request).split()
        accepted = [t.lower().encode() for t in s.AUTH_HEADER_TYPES]
        if not header or header[0].lower() not in accepted:
            return None
        if len(header) != 2:
            msg = _("Authorization header must be 'Bearer <token>'.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_authorization_header")
        try:
            raw = header[1].decode()
        except UnicodeError as exc:
            msg = _("Token contains invalid characters.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_token") from exc

        try:
            token = AccessToken.verify(raw)
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="invalid_token") from exc

        if s.BLACKLIST_ENABLED and await ATokenBlacklist.ais_blacklisted(token.jti):
            msg = _("Token has been blacklisted.")
            raise exceptions.AuthenticationFailed(msg, code="token_blacklisted")

        user = await self.aget_user(token)
        return (user, token)

    def authenticate_header(self, request):
        """Returns the WWW-Authenticate header value used on 401 responses."""
        return f'Bearer realm="{self.www_authenticate_realm}"'

    def get_user(self, token: AccessToken):
        s = get_jwt_settings()
        user_model = get_user_model()
        try:
            user_id = token.payload[s.USER_ID_CLAIM]
        except KeyError as exc:
            msg = _("Token contained no recognizable user identification.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_token") from exc
        try:
            user = user_model.objects.get(**{s.USER_ID_FIELD: user_id})
        except user_model.DoesNotExist as exc:
            msg = _("User not found.")
            raise exceptions.AuthenticationFailed(msg, code="user_not_found") from exc
        if s.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise exceptions.AuthenticationFailed(_("User is inactive."), code="user_inactive")
        if s.CHECK_REVOKE_TOKEN and token.payload.get(s.REVOKE_TOKEN_CLAIM) != get_password_hash(user.password):
            raise exceptions.AuthenticationFailed(
                _("The user's password has been changed."), code="password_changed"
            )
        return user

    async def aget_user(self, token: AccessToken):
        s = get_jwt_settings()
        user_model = get_user_model()
        try:
            user_id = token.payload[s.USER_ID_CLAIM]
        except KeyError as exc:
            msg = _("Token contained no recognizable user identification.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_token") from exc
        try:
            user = await user_model.objects.aget(**{s.USER_ID_FIELD: user_id})
        except user_model.DoesNotExist as exc:
            msg = _("User not found.")
            raise exceptions.AuthenticationFailed(msg, code="user_not_found") from exc

        if s.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise exceptions.AuthenticationFailed(
                _("User is inactive."), code="user_inactive"
            )

        if s.CHECK_REVOKE_TOKEN and token.payload.get(
            s.REVOKE_TOKEN_CLAIM
        ) != get_password_hash(user.password):
            raise exceptions.AuthenticationFailed(
                _("The user's password has been changed."), code="password_changed"
            )

        return user
