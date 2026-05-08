import asyncio
from unittest.mock import MagicMock

from restflow.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)


def _run(coro):
    return asyncio.run(coro)


def _request(*, authenticated=True, staff=False, method="GET"):
    user = MagicMock()
    user.is_authenticated = authenticated
    user.is_staff = staff
    request = MagicMock()
    request.user = user
    request.method = method
    return request


def test_allow_any_ahas_permission_returns_true():
    assert _run(AllowAny().ahas_permission(_request(), None)) is True


def test_is_authenticated_ahas_permission_for_logged_in():
    assert _run(IsAuthenticated().ahas_permission(_request(authenticated=True), None)) is True


def test_is_authenticated_ahas_permission_rejects_anonymous():
    request = _request(authenticated=False)
    request.user.is_authenticated = False
    assert _run(IsAuthenticated().ahas_permission(request, None)) is False


def test_is_admin_ahas_permission_requires_staff():
    assert _run(IsAdminUser().ahas_permission(_request(staff=True), None)) is True
    assert _run(IsAdminUser().ahas_permission(_request(staff=False), None)) is False


def test_is_authenticated_or_read_only_allows_get_for_anonymous():
    request = _request(authenticated=False, method="GET")
    request.user.is_authenticated = False
    assert _run(IsAuthenticatedOrReadOnly().ahas_permission(request, None)) is True


def test_is_authenticated_or_read_only_rejects_post_for_anonymous():
    request = _request(authenticated=False, method="POST")
    request.user.is_authenticated = False
    assert _run(IsAuthenticatedOrReadOnly().ahas_permission(request, None)) is False


def test_and_composition_async():
    perm = (IsAuthenticated & IsAdminUser)()
    assert _run(perm.ahas_permission(_request(authenticated=True, staff=True), None)) is True
    assert _run(perm.ahas_permission(_request(authenticated=True, staff=False), None)) is False


def test_or_composition_async():
    perm = (IsAuthenticated | IsAdminUser)()
    assert _run(perm.ahas_permission(_request(authenticated=True, staff=False), None)) is True


def test_not_composition_async():
    perm = (~IsAuthenticated)()
    request = _request(authenticated=False)
    request.user.is_authenticated = False
    assert _run(perm.ahas_permission(request, None)) is True


def test_base_permission_falls_back_to_sync():
    class CustomSync(BasePermission):
        def has_permission(self, request, view):
            return True

    assert _run(CustomSync().ahas_permission(_request(), None)) is True


def test_base_permission_object_falls_back_to_sync():
    class CustomSync(BasePermission):
        def has_object_permission(self, request, view, obj):
            return obj == "allowed"

    perm = CustomSync()
    assert _run(perm.ahas_object_permission(_request(), None, "allowed")) is True
    assert _run(perm.ahas_object_permission(_request(), None, "other")) is False


class _AlwaysAllow(BasePermission):
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return True


class _AlwaysDeny(BasePermission):
    def has_permission(self, request, view):
        return False

    def has_object_permission(self, request, view, obj):
        return False


def test_rand_creates_async_holder():
    perm = (_AlwaysAllow & IsAdminUser)()
    assert _run(perm.ahas_permission(_request(staff=True), None)) is True


def test_ror_creates_async_holder():
    perm = (_AlwaysDeny | IsAdminUser)()
    assert _run(perm.ahas_permission(_request(staff=True), None)) is True


def test_and_short_circuits_when_first_denies():
    perm = (_AlwaysDeny & _AlwaysAllow)()
    assert _run(perm.ahas_permission(_request(), None)) is False


def test_and_object_permission_short_circuits_when_first_denies():
    perm = (_AlwaysDeny & _AlwaysAllow)()
    assert _run(perm.ahas_object_permission(_request(), None, object())) is False


def test_and_object_permission_true_when_both_allow():
    perm = (_AlwaysAllow & _AlwaysAllow)()
    assert _run(perm.ahas_object_permission(_request(), None, object())) is True


def test_or_short_circuits_when_first_allows():
    perm = (_AlwaysAllow | _AlwaysDeny)()
    assert _run(perm.ahas_permission(_request(), None)) is True


def test_or_falls_through_when_first_denies():
    perm = (_AlwaysDeny | _AlwaysAllow)()
    assert _run(perm.ahas_permission(_request(), None)) is True


def test_or_object_permission_short_circuits_when_first_allows():
    perm = (_AlwaysAllow | _AlwaysDeny)()
    assert _run(perm.ahas_object_permission(_request(), None, object())) is True


def test_or_object_permission_falls_through_to_second():
    perm = (_AlwaysDeny | _AlwaysAllow)()
    assert _run(perm.ahas_object_permission(_request(), None, object())) is True


def test_not_object_permission_inverts_wrapped():
    perm = (~_AlwaysAllow)()
    assert _run(perm.ahas_object_permission(_request(), None, object())) is False
    perm_deny = (~_AlwaysDeny)()
    assert _run(perm_deny.ahas_object_permission(_request(), None, object())) is True


class _SyncOnlyPermission:
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return True


def test_call_has_permission_falls_back_to_sync_when_no_async_method():
    from restflow.permissions.permissions import has_permission

    result = has_permission(_SyncOnlyPermission(), _request(), None)
    assert result is True


def test_call_has_object_permission_uses_async_when_present():
    from restflow.permissions.permissions import has_object_permission

    perm = _AlwaysAllow()
    coro = has_object_permission(perm, _request(), None, object())
    assert _run(coro) is True


def test_call_has_object_permission_falls_back_to_sync():
    from restflow.permissions.permissions import has_object_permission

    result = has_object_permission(
        _SyncOnlyPermission(), _request(), None, object()
    )
    assert result is True


def test_rand_dunder_invokes_async_holder():
    from restflow.permissions.permissions import AsyncOperand

    holder = IsAuthenticated.__rand__(IsAdminUser)
    assert isinstance(holder, AsyncOperand)
    perm = holder()
    assert _run(perm.ahas_permission(_request(staff=True), None)) is True


def test_ror_dunder_invokes_async_holder():
    from restflow.permissions.permissions import AsyncOperand

    holder = IsAuthenticated.__ror__(IsAdminUser)
    assert isinstance(holder, AsyncOperand)
    perm = holder()
    assert _run(perm.ahas_permission(_request(staff=True), None)) is True
