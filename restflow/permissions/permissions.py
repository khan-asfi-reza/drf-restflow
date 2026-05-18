from asgiref.sync import sync_to_async
from rest_framework import permissions as drf_perms
from rest_framework.permissions import SAFE_METHODS

from restflow.helpers import maybe_await


def has_permission(perm, request, view):
    """Async compatible has_permission checker. Checks whether async variant exists or not."""
    ahas = getattr(perm, "ahas_permission", None)
    if ahas is not None:
        return ahas(request, view)
    return perm.has_permission(request, view)


def has_object_permission(perm, request, view, obj):
    """Async compatible has_object_permission checker. Checks whether async variant exists or not."""
    ahas = getattr(perm, "ahas_object_permission", None)
    if ahas is not None:
        return ahas(request, view, obj)
    return perm.has_object_permission(request, view, obj)


class AsyncOperationMixin(drf_perms.OperationHolderMixin):
    def __and__(self, other):
        return AsyncOperand(AND, self, other)

    def __or__(self, other):
        return AsyncOperand(OR, self, other)

    def __rand__(self, other):
        return AsyncOperand(AND, other, self)

    def __ror__(self, other):
        return AsyncOperand(OR, other, self)

    def __invert__(self):
        return AsyncSingleOperand(NOT, self)


class AsyncSingleOperand(AsyncOperationMixin):
    def __init__(self, operator_class, op1_class):
        self.operator_class = operator_class
        self.op1_class = op1_class

    def __call__(self, *args, **kwargs):
        op1 = self.op1_class(*args, **kwargs)
        return self.operator_class(op1)


class AsyncOperand(AsyncOperationMixin):
    def __init__(self, operator_class, op1_class, op2_class):
        self.operator_class = operator_class
        self.op1_class = op1_class
        self.op2_class = op2_class

    def __call__(self, *args, **kwargs):
        op1 = self.op1_class(*args, **kwargs)
        op2 = self.op2_class(*args, **kwargs)
        return self.operator_class(op1, op2)


class AND(drf_perms.AND):
    """
    Permission combinator produced by perm1 & perm2.
    Adds async ahas_permission and ahas_object_permission that short-circuit on the first denying operand.
    """

    async def ahas_permission(self, request, view):
        """Returns True only when both operands allow the request."""
        if not await maybe_await(has_permission(self.op1, request, view)):
            return False
        return await maybe_await(has_permission(self.op2, request, view))

    async def ahas_object_permission(self, request, view, obj):
        """Returns True only when both operands allow access to the object."""
        if not await maybe_await(
            has_object_permission(self.op1, request, view, obj)
        ):
            return False
        return await maybe_await(
            has_object_permission(self.op2, request, view, obj)
        )


class OR(drf_perms.OR):
    """
    Permission combinator produced by perm1 | perm2.
    Adds async ahas_permission and ahas_object_permission that short-circuit on the first allowing operand.
    """

    async def ahas_permission(self, request, view):
        """Returns True when either operand allows the request."""
        if await maybe_await(has_permission(self.op1, request, view)):
            return True
        return await maybe_await(has_permission(self.op2, request, view))

    async def ahas_object_permission(self, request, view, obj):
        """Returns True when either operand allows access to the object."""
        if await maybe_await(
            has_permission(self.op1, request, view)
        ) and await maybe_await(
            has_object_permission(self.op1, request, view, obj)
        ):
            return True
        return await maybe_await(
            has_permission(self.op2, request, view)
        ) and await maybe_await(
            has_object_permission(self.op2, request, view, obj)
        )


class NOT(drf_perms.NOT):
    """
    Permission combinator produced by ~perm.
    Adds async ahas_permission and ahas_object_permission that invert the wrapped permission's verdict.
    """

    async def ahas_permission(self, request, view):
        """Returns the negation of the wrapped operand's permission check."""
        return not await maybe_await(
            has_permission(self.op1, request, view)
        )

    async def ahas_object_permission(self, request, view, obj):
        """Returns the negation of the wrapped operand's object permission check."""
        return not await maybe_await(
            has_object_permission(self.op1, request, view, obj)
        )



class BasePermissionMetaclass(
    AsyncOperationMixin, drf_perms.BasePermissionMetaclass
):
    pass


class BasePermission(drf_perms.BasePermission, metaclass=BasePermissionMetaclass):
    """
    All permission classes should extend BasePermission.
    Adds async ahas_permission and ahas_object_permission hooks that default to running the sync methods in a thread.
    """

    async def ahas_permission(self, request, view):
        """Returns True when the request is permitted, False otherwise."""
        return await sync_to_async(
            self.has_permission, thread_sensitive=True
        )(request, view)

    async def ahas_object_permission(self, request, view, obj):
        """Returns True when the request is permitted to act on the given object."""
        return await sync_to_async(
            self.has_object_permission, thread_sensitive=True
        )(request, view, obj)


class AllowAny(BasePermission, drf_perms.AllowAny):
    """
    Allow any access.
    Adds an async surface that returns True .
    """

    async def ahas_permission(self, request, view):
        """Always returns True."""
        return True


class IsAuthenticated(BasePermission, drf_perms.IsAuthenticated):
    """
    Allows access only to authenticated users.
    Adds an async surface that reads request.user .
    """

    async def ahas_permission(self, request, view):
        """Returns True if the request user is authenticated."""
        return bool(request.user and request.user.is_authenticated)


class IsAdminUser(BasePermission, drf_perms.IsAdminUser):
    """
    Allows access only to admin users.
    Adds an async surface that reads request.user .
    """

    async def ahas_permission(self, request, view):
        """Returns True if the request user is staff."""
        return bool(request.user and request.user.is_staff)


class IsAuthenticatedOrReadOnly(BasePermission, drf_perms.IsAuthenticatedOrReadOnly):
    """
    The request is authenticated as a user, or is a read-only request.
    Adds an async surface that resolves .
    """

    async def ahas_permission(self, request, view):
        """Returns True for SAFE_METHODS or when the request user is authenticated."""
        return bool(
            request.method in SAFE_METHODS
            or (request.user and request.user.is_authenticated)
        )


class DjangoModelPermissions(BasePermission, drf_perms.DjangoModelPermissions):
    """
    The request is authenticated using Django's standard model-level permissions.
    Inherits the sync logic from DRF; the async surface defaults to sync_to_async.
    """


class DjangoModelPermissionsOrAnonReadOnly(
    BasePermission, drf_perms.DjangoModelPermissionsOrAnonReadOnly
):
    """
    Same as DjangoModelPermissions, except anonymous users have read-only access.
    Inherits the sync logic from DRF; the async surface defaults to sync_to_async.
    """


class DjangoObjectPermissions(BasePermission, drf_perms.DjangoObjectPermissions):
    """
    The request is authenticated using Django's object-level permissions.
    Inherits the sync logic from DRF; the async surface defaults to sync_to_async.
    """
