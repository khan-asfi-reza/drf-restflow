try:
    from rest_framework_simplejwt.authentication import (
        JWTAuthentication as _SimpleJWTAuthentication,
    )
    from rest_framework_simplejwt.exceptions import (
        InvalidToken,
    )
    from rest_framework_simplejwt.exceptions import (
        TokenError as _SimpleJWTTokenError,
    )
    from rest_framework_simplejwt.settings import (
        api_settings as _simplejwt_settings,
    )
    from rest_framework_simplejwt.tokens import get_md5_hash_password
except ImportError as exc:  # pragma: no cover
    msg = (
        "djangorestframework-simplejwt is not installed. "
    )
    raise ImportError(msg) from exc

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions

from restflow.authentication.authentication import BaseAuthentication


class SimpleJWTAuthentication(BaseAuthentication, _SimpleJWTAuthentication):
    """
    Async aware adapter for djangorestframework-simplejwt.
    Reuses simplejwt's token validation and adds an async surface that resolves the user via async ORM.
    """

    async def aauthenticate(self, request):
        """Returns a (user, token) tuple for the bearer token in the Authorization header, or None when no token is supplied."""
        header = self.get_header(request)
        if header is None:
            return None
        raw = self.get_raw_token(header)
        if raw is None:
            return None
        try:
            validated = self.get_validated_token(raw)
        except (_SimpleJWTTokenError, InvalidToken) as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="invalid_token") from exc
        user = await self.aget_user(validated)
        return (user, validated)

    async def aget_user(self, validated_token):
        user_model = get_user_model()
        try:
            user_id = validated_token[_simplejwt_settings.USER_ID_CLAIM]
        except KeyError as exc:
            msg = _("Token contained no recognizable user identification.")
            raise exceptions.AuthenticationFailed(msg, code="invalid_token") from exc
        try:
            user = await user_model.objects.aget(
                **{_simplejwt_settings.USER_ID_FIELD: user_id}
            )
        except user_model.DoesNotExist as exc:
            msg = _("User not found.")
            raise exceptions.AuthenticationFailed(msg, code="user_not_found") from exc

        if _simplejwt_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise exceptions.AuthenticationFailed(
                _("User is inactive."), code="user_inactive"
            )

        if _simplejwt_settings.CHECK_REVOKE_TOKEN and validated_token.get(
            _simplejwt_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise exceptions.AuthenticationFailed(
                _("The user's password has been changed."), code="password_changed"
            )

        return user
