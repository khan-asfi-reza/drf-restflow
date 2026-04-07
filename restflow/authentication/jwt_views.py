from django.contrib.auth import aauthenticate as django_aauthenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.response import Response

from restflow.authentication.jwt import (
    AccessToken,
    ATokenBlacklist,
    RefreshToken,
    TokenError,
    get_jwt_settings,
    get_user_authentication_rule,
)
from restflow.serializers import Field, Serializer
from restflow.views import AsyncAPIView


class TokenObtainSerializer(Serializer):
    """Validates a username and password pair for a token obtain request."""

    username: str
    password: str = Field(write_only=True)


class TokenRefreshSerializer(Serializer):
    """Validates a refresh token string."""

    refresh: str


class TokenBlacklistSerializer(Serializer):
    """Validates the refresh token to blacklist."""

    refresh: str


class TokenObtainView(AsyncAPIView):
    """
    Returns a fresh access and refresh token pair for a valid username and password.
    Adds an async surface that authenticates via django.contrib.auth.aauthenticate.
    """

    serializer_class = TokenObtainSerializer
    authentication_classes = ()
    permission_classes = ()

    def get_authenticate_header(self, request):
        """Returns the WWW-Authenticate header value used on 401 responses."""
        return 'Bearer realm="api"'

    async def post(self, request):
        """Returns {access, refresh} tokens for the supplied credentials."""
        ser = await self.avalidated_serializer()
        user = await django_aauthenticate(
            request=request,
            username=ser.validated_data["username"],
            password=ser.validated_data["password"],
        )
        if not get_user_authentication_rule()(user):
            msg = _("No active account found with the given credentials.")
            raise exceptions.AuthenticationFailed(msg, code="no_active_account")
        return Response({
            "access": str(AccessToken.for_user(user)),
            "refresh": str(RefreshToken.for_user(user)),
        })


class TokenRefreshView(AsyncAPIView):
    """
    Returns a fresh access token for a valid refresh token.
    Refreshing a blacklisted or expired refresh token raises 401.
    """

    serializer_class = TokenRefreshSerializer
    authentication_classes = ()
    permission_classes = ()

    def get_authenticate_header(self, request):
        """Returns the WWW-Authenticate header value used on 401 responses."""
        return 'Bearer realm="api"'

    async def post(self, request):
        """Returns a new {access} token derived from the supplied refresh token. Rotates the refresh token when ROTATE_REFRESH_TOKENS is enabled."""
        ser = await self.avalidated_serializer()
        try:
            refresh = RefreshToken.verify(ser.validated_data["refresh"])
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="invalid_token") from exc

        jwt_settings = get_jwt_settings()
        if jwt_settings.BLACKLIST_ENABLED and await ATokenBlacklist.is_blacklisted(refresh.jti):
            msg = _("Token has been blacklisted.")
            raise exceptions.AuthenticationFailed(msg, code="token_blacklisted")

        access = refresh.access_token
        if not jwt_settings.ROTATE_REFRESH_TOKENS:
            return Response({"access": str(access)})

        new_refresh = refresh.rotate()
        if jwt_settings.BLACKLIST_ENABLED:
            await refresh.ablacklist()
        return Response({
            "access": str(access),
            "refresh": str(new_refresh),
        })


class TokenBlacklistView(AsyncAPIView):
    """
    Blacklists a refresh token so it cannot mint further access tokens.
    The token's JTI is added to the configured blacklist for the remainder of its lifetime.
    """

    serializer_class = TokenBlacklistSerializer
    authentication_classes = ()
    permission_classes = ()

    def get_authenticate_header(self, request):
        """Returns the WWW-Authenticate header value used on 401 responses."""
        return 'Bearer realm="api"'

    async def post(self, request):
        """Blacklists the supplied refresh token and returns 204."""
        ser = await self.avalidated_serializer()
        try:
            refresh = RefreshToken.verify(ser.validated_data["refresh"])
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="invalid_token") from exc
        await refresh.ablacklist()
        return Response(status=204)
