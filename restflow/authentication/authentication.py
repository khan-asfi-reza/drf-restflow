import base64
import binascii

from asgiref.sync import sync_to_async
from django.contrib.auth import aauthenticate as django_aauthenticate
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import authentication as drf_auth
from rest_framework import exceptions
from rest_framework.authentication import get_authorization_header


class BaseAuthentication(drf_auth.BaseAuthentication):
    """
    All authentication classes should extend BaseAuthentication.
    Adds an async aauthenticate hook that defaults to running the sync authenticate in a thread.
    """

    async def aauthenticate(self, request):
        """Returns a (user, auth) tuple or None for the given request."""
        return await sync_to_async(
            self.authenticate, thread_sensitive=True
        )(request)


class BasicAuthentication(BaseAuthentication, drf_auth.BasicAuthentication):
    """
    HTTP Basic authentication against username and password.
    Adds an async surface that resolves credentials via django.contrib.auth.aauthenticate.
    """
    async def aauthenticate(self, request):
        """Returns a (user, None) tuple after validating the Basic credentials, or None when no header is present."""
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != b"basic":
            return None
        if len(auth) == 1:
            msg = _("Invalid basic header. No credentials provided.")
            raise exceptions.AuthenticationFailed(msg)
        if len(auth) > 2:
            msg = _(
                "Invalid basic header. "
                "Credentials string should not contain spaces."
            )
            raise exceptions.AuthenticationFailed(msg)

        try:
            try:
                auth_decoded = base64.b64decode(auth[1]).decode("utf-8")
            except UnicodeDecodeError:
                auth_decoded = base64.b64decode(auth[1]).decode("latin-1")
            userid, password = auth_decoded.split(":", 1)
        except (TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
            msg = _(
                "Invalid basic header. Credentials not correctly base64 encoded."
            )
            raise exceptions.AuthenticationFailed(msg) from exc

        return await self.aauthenticate_credentials(userid, password, request)

    async def aauthenticate_credentials(self, userid, password, request=None):
        """Authenticates the user.<pk>/<username field> and password using the configured authentication backends."""
        credentials = {
            get_user_model().USERNAME_FIELD: userid,
            "password": password,
        }
        user = await django_aauthenticate(request=request, **credentials)
        if user is None:
            raise exceptions.AuthenticationFailed(_("Invalid username/password."))
        if not user.is_active:
            raise exceptions.AuthenticationFailed(_("User inactive or deleted."))
        return (user, None)


class SessionAuthentication(BaseAuthentication, drf_auth.SessionAuthentication):
    """
    Use Django's session framework for authentication.
    Adds an async surface that prefers request._request.auser when available and runs the CSRF check off the event loop.
    """
    async def aauthenticate(self, request):
        """Returns a (user, None) tuple from the session, or None when no active user is present."""
        underlying = getattr(request, "_request", request)
        auser = getattr(underlying, "auser", None)
        if callable(auser):
            user = await auser()
        else:
            user = getattr(underlying, "user", None)
        if not user or not user.is_active:
            return None
        await sync_to_async(self.enforce_csrf, thread_sensitive=True)(request)
        return (user, None)


class TokenAuthentication(BaseAuthentication, drf_auth.TokenAuthentication):
    """
    Simple token based authentication.
    Clients should authenticate by passing the token key in the "Authorization" HTTP header, prepended with the string "Token ".
    Adds an async surface that resolves the token via async ORM.
    """
    async def aauthenticate(self, request):
        """Returns a (user, token) tuple after validating the Authorization header, or None when no token is supplied."""
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None
        if len(auth) == 1:
            msg = _("Invalid token header. No credentials provided.")
            raise exceptions.AuthenticationFailed(msg)
        if len(auth) > 2:
            msg = _(
                "Invalid token header. Token string should not contain spaces."
            )
            raise exceptions.AuthenticationFailed(msg)
        try:
            token = auth[1].decode()
        except UnicodeError as exc:
            msg = _(
                "Invalid token header. "
                "Token string should not contain invalid characters."
            )
            raise exceptions.AuthenticationFailed(msg) from exc
        return await self.aauthenticate_credentials(token)

    async def aauthenticate_credentials(self, key):
        """Returns a (user, token) tuple for the given token key using async ORM."""
        model = self.get_model()
        try:
            token = await model.objects.select_related("user").aget(key=key)
        except model.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed(_("Invalid token.")) from exc
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed(_("User inactive or deleted."))
        return (token.user, token)


class RemoteUserAuthentication(BaseAuthentication, drf_auth.RemoteUserAuthentication):
    """
    REMOTE_USER authentication.
    Maps the value at request.META[header] to a User via the configured Django auth backend.
    Adds an async surface using django.contrib.auth.aauthenticate.
    """
    async def aauthenticate(self, request):
        """Returns a (user, None) tuple from the configured remote-user header, or None when no active user is resolved."""
        user = await django_aauthenticate(
            request=request, remote_user=request.META.get(self.header)
        )
        if user and user.is_active:
            return (user, None)
        return None
