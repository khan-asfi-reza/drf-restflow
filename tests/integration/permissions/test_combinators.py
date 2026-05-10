import asyncio
from unittest.mock import MagicMock

from restflow.permissions import (
    AllowAny,
    BasePermission,
    IsAdminUser,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)


def run_coro(coro):
    return asyncio.run(coro)


def make_request(*, authenticated=True, staff=False, method="GET"):
    user = MagicMock()
    user.is_authenticated = authenticated
    user.is_staff = staff
    request = MagicMock()
    request.user = user
    request.method = method
    return request


class AsyncTrue(BasePermission):
    async def ahas_permission(self, request, view):
        return True

    async def ahas_object_permission(self, request, view, obj):
        return True


class AsyncFalse(BasePermission):
    async def ahas_permission(self, request, view):
        return False

    async def ahas_object_permission(self, request, view, obj):
        return False


class SyncTrue(BasePermission):
    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return True


class SyncFalse(BasePermission):
    def has_permission(self, request, view):
        return False

    def has_object_permission(self, request, view, obj):
        return False


def test_three_way_and_chain_all_allow():
    perm = (AsyncTrue & AsyncTrue & AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_three_way_and_chain_one_denies():
    perm = (AsyncTrue & AsyncFalse & AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is False


def test_three_way_or_chain_all_deny():
    perm = (AsyncFalse | AsyncFalse | AsyncFalse)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is False


def test_three_way_or_chain_last_allows():
    perm = (AsyncFalse | AsyncFalse | AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_nested_and_or_complex():
    perm = ((AsyncTrue & AsyncFalse) | AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_nested_or_and_complex():
    perm = ((AsyncFalse | AsyncTrue) & AsyncFalse)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is False


def test_double_negation_collapses_to_original():
    perm = (~~AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_negation_of_and_de_morgan():
    perm = (~(AsyncTrue & AsyncFalse))()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_mixed_sync_async_in_chain():
    perm = (SyncTrue & AsyncTrue & SyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_mixed_sync_deny_in_async_chain_denies():
    perm = (AsyncTrue & SyncFalse)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is False


def test_object_permission_three_way_and_chain():
    perm = (AsyncTrue & AsyncTrue & AsyncTrue)()
    assert run_coro(perm.ahas_object_permission(make_request(), None, object())) is True


def test_object_permission_three_way_or_chain_with_one_match():
    perm = (AsyncFalse | AsyncTrue | AsyncFalse)()
    assert run_coro(perm.ahas_object_permission(make_request(), None, object())) is True


def test_invert_then_and_combination():
    perm = (~AsyncFalse & AsyncTrue)()
    assert run_coro(perm.ahas_permission(make_request(), None)) is True


def test_allow_any_or_anything_short_circuits():
    perm = (AllowAny | AsyncFalse)()
    assert run_coro(perm.ahas_permission(make_request(authenticated=False), None)) is True


def test_is_authenticated_and_admin_requires_both():
    perm = (IsAuthenticated & IsAdminUser)()
    assert run_coro(perm.ahas_permission(make_request(authenticated=True, staff=True), None)) is True
    assert run_coro(perm.ahas_permission(make_request(authenticated=True, staff=False), None)) is False
    req = make_request(authenticated=False, staff=False)
    req.user.is_authenticated = False
    assert run_coro(perm.ahas_permission(req, None)) is False


def test_is_authenticated_or_read_only_post_requires_auth():
    perm = IsAuthenticatedOrReadOnly()
    anon_get = make_request(authenticated=False, method="GET")
    anon_get.user.is_authenticated = False
    anon_post = make_request(authenticated=False, method="POST")
    anon_post.user.is_authenticated = False
    assert run_coro(perm.ahas_permission(anon_get, None)) is True
    assert run_coro(perm.ahas_permission(anon_post, None)) is False


def test_chain_with_is_admin_or_owner_pattern():
    class IsOwner(BasePermission):
        async def ahas_permission(self, request, view):
            return True

        async def ahas_object_permission(self, request, view, obj):
            return getattr(obj, "owner", None) == "me"

    perm = (IsAdminUser | IsOwner)()
    obj = type("O", (), {"owner": "me"})()
    assert run_coro(perm.ahas_object_permission(make_request(staff=False), None, obj)) is True
    obj2 = type("O", (), {"owner": "other"})()
    assert run_coro(perm.ahas_object_permission(make_request(staff=True), None, obj2)) is True
    assert run_coro(perm.ahas_object_permission(make_request(staff=False), None, obj2)) is False


def test_or_object_first_perm_allows_only_class_level_then_falls_through():
    class AllowClassDenyObj(BasePermission):
        async def ahas_permission(self, request, view):
            return True

        async def ahas_object_permission(self, request, view, obj):
            return False

    perm = (AllowClassDenyObj | AsyncTrue)()
    assert run_coro(perm.ahas_object_permission(make_request(), None, object())) is True


def test_invert_combinator_object_permission():
    perm = (~AsyncTrue)()
    assert run_coro(perm.ahas_object_permission(make_request(), None, object())) is False


def test_or_chain_short_circuits_after_first_allow():
    calls = []

    class RecAllow(BasePermission):
        async def ahas_permission(self, request, view):
            calls.append("allow")
            return True

    class RecDeny(BasePermission):
        async def ahas_permission(self, request, view):
            calls.append("deny")
            return False

    perm = (RecAllow | RecDeny)()
    run_coro(perm.ahas_permission(make_request(), None))
    assert calls == ["allow"]


def test_and_chain_short_circuits_after_first_deny():
    calls = []

    class RecDeny(BasePermission):
        async def ahas_permission(self, request, view):
            calls.append("deny")
            return False

    class RecAllow(BasePermission):
        async def ahas_permission(self, request, view):
            calls.append("allow")
            return True

    perm = (RecDeny & RecAllow)()
    run_coro(perm.ahas_permission(make_request(), None))
    assert calls == ["deny"]
