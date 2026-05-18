# Permissions

`restflow.permissions` ships async-aware permission classes that drop
into the same slot as DRF permissions. Every class extends DRF's
`BasePermission` and adds an async surface, so the same permission
works for sync and async views without modification.

Permission classes are checked after authentication on every request.
DRF resolves the request's user through the configured authentication
classes, then runs each permission class in order. The view is allowed
to proceed only when every permission class returns True.

Async views call `ahas_permission` during request initialisation, and
`ahas_object_permission` after the target object has been fetched.
Sync views still call `has_permission` and `has_object_permission`,
which is why every permission in this module inherits the DRF sync
implementation alongside the async surface.

The async dispatch path can also work with legacy permission classes
that only define the sync hooks. The default `ahas_permission`
implementation on `BasePermission` runs the sync method through
`sync_to_async`, so any third-party permission keeps working when
mounted on an async view.

```python
from restflow.permissions import IsAuthenticated
from restflow.views import AsyncListAPIView


class ArticleList(AsyncListAPIView):
    permission_classes = [IsAuthenticated]
```

## Async hooks

Two hooks define the async surface:

- `async ahas_permission(request, view) -> bool` -- runs once per
  request, before the view body.
- `async ahas_object_permission(request, view, obj) -> bool` -- runs
  after the object lookup for detail-style actions.

`BasePermission` provides defaults for both that wrap the sync
`has_permission` and `has_object_permission` so existing DRF
permissions work under async dispatch. Override `ahas_permission`
directly when the check can run natively async.

The standard classes -- `AllowAny`, `IsAuthenticated`, `IsAdminUser`,
and `IsAuthenticatedOrReadOnly` -- override `ahas_permission` because
their checks read attributes that are already loaded on the request.
`DjangoModelPermissions`, `DjangoModelPermissionsOrAnonReadOnly`, and
`DjangoObjectPermissions` rely on Django's permission cache and may
hit the database, so they use the sync-wrapper path.

Returning a truthy non-bool is allowed but not recommended. Stick to
True or False so combinators read cleanly.

## Standard permissions

### AllowAny

Always returns True. Useful as an explicit marker that a route is
public, or as the default when other permissions are layered on
through combinators.

```python
from restflow.permissions import AllowAny


class HealthCheck(AsyncAPIView):
    permission_classes = [AllowAny]
```

### IsAuthenticated

Returns True when `request.user` exists and is authenticated. This is
the most common entry point for protected endpoints.

```python
from restflow.permissions import IsAuthenticated


class AccountSettings(AsyncRetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
```

### IsAdminUser

Returns True when `request.user` is set and `is_staff` is True. The
check honours the Django admin convention rather than superuser
status, so any user with the staff flag passes.

```python
from restflow.permissions import IsAdminUser


class AdminMetrics(AsyncListAPIView):
    permission_classes = [IsAdminUser]
```

### IsAuthenticatedOrReadOnly

Allows safe-method requests (`GET`, `HEAD`, `OPTIONS`) for everyone
and requires authentication for write methods. Anonymous reads,
authenticated writes is the typical use case.

```python
from restflow.permissions import IsAuthenticatedOrReadOnly


class CommentList(AsyncListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
```

### DjangoModelPermissions

Maps the request's HTTP method to the Django model permission
required to perform it. `POST` requires `add`, `PUT` and `PATCH`
require `change`, `DELETE` requires `delete`. The view must define
`queryset` so the permission can derive the model's app label and
model name.

The class inherits the DRF sync logic and uses the default
`sync_to_async` path on the async surface, since `user.has_perm`
hits the permission cache, which can issue a query on first access.

```python
from restflow.permissions import DjangoModelPermissions
from restflow.views import AsyncModelViewSet


class ArticleViewSet(AsyncModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [DjangoModelPermissions]
```

### DjangoModelPermissionsOrAnonReadOnly

Same as `DjangoModelPermissions`, but anonymous users can perform
read-only requests. Authenticated users still need the matching
model permission for writes.

```python
from restflow.permissions import DjangoModelPermissionsOrAnonReadOnly


class ArticleViewSet(AsyncModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]
```

### DjangoObjectPermissions

Adds object-level checks on top of `DjangoModelPermissions`. After
the model-level check passes, the framework calls
`ahas_object_permission`, which delegates to
`user.has_perm(perm, obj)`. Pair this with django-guardian or any
backend that resolves object permissions.

```python
from restflow.permissions import DjangoObjectPermissions


class DocumentViewSet(AsyncModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [DjangoObjectPermissions]
```

## Combinators

DRF supports boolean composition of permission classes through the
`&`, `|`, and `~` operators, with brackets for grouping. Operators
follow the same precedence and associativity rules as Python's
logical operators (`~` highest, then `&`, then `|`). Restflow
inherits that and adds async-native operator classes
(`AND`, `OR`, `NOT`) so combinator branches resolve through the
async hook (`ahas_permission`, `ahas_object_permission`).

| Operator | Class | Meaning |
| --- | --- | --- |
| `perm1 & perm2` | `AND` | Both operands must allow. |
| `perm1 \| perm2` | `OR` | Either operand may allow. |
| `~perm` | `NOT` | Inverts the operand's verdict. |

```python
from restflow.permissions import IsAuthenticated, IsAdminUser


class ArticleViewSet(AsyncModelViewSet):
    permission_classes = [IsAuthenticated & (IsAdminUser | IsOwner)]
```

Precedence means `~A & B | C` parses as `((~A) & B) | C`. Brackets
override precedence for any composition that needs a different
grouping, for example `IsAuthenticated & (IsAdminUser | IsOwner)`.

The async operator classes implement `ahas_permission` and
`ahas_object_permission` and short-circuit on the first decisive
operand. `AND.ahas_permission` returns False as soon as the first
operand rejects, and `OR.ahas_permission` returns True as soon as
the first operand allows. The behaviour matches DRF's sync
combinators; the difference is that the async dispatch path awaits
each operand  when the operand exposes an async
hook.

`OR.ahas_object_permission` enforces a small but important rule
that mirrors DRF's sync behaviour: for each operand, both
`ahas_permission` and `ahas_object_permission` must pass before the
operand can grant access. This prevents an operand from leaking
object-level access to a request it would have rejected at the
permission gate.

```python
class IsArchived(BasePermission):
    async def ahas_permission(self, request, view):
        return True

    async def ahas_object_permission(self, request, view, obj):
        return obj.archived


# the un-archive endpoint should reject already-active articles
permission_classes = [IsAuthenticated & ~IsArchived]
```

Combinators support nesting. `(A & B) | C` and `A & (B | C)` are
both valid. The runtime walks the tree, so deep compositions cost
no more than the sum of the operand checks.

## Custom permissions

Subclass `BasePermission` and implement the async hooks for the path
the view uses. For mixed sync and async deployments, implement both
the sync and async hooks so the permission class works under either
dispatch.

```python
from restflow.permissions import BasePermission


class IsOwner(BasePermission):
    """Allows access only to the owner of the object."""

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.owner_id == request.user.id
        )

    async def ahas_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.owner_id == request.user.id
        )
```

If the check is purely about the request and never the object,
implement `has_permission` and `ahas_permission` instead.

```python
class IsTenantMember(BasePermission):
    """Allows access only to members of the active tenant."""

    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        return bool(
            tenant
            and request.user.is_authenticated
            and tenant.members.filter(pk=request.user.pk).exists()
        )

    async def ahas_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        if not tenant or not request.user.is_authenticated:
            return False
        return await tenant.members.filter(pk=request.user.pk).aexists()
```

When only the async hook is implemented, the sync dispatch path
falls back to the sync `has_permission` from DRF's `BasePermission`,
which returns True. That makes the permission a no-op on sync views.
Implement `has_permission` whenever the same code might be mounted
on a sync view as well.

## Per-action permissions

`restflow.views.ActionConfig` overrides class-level attributes for
a single action on an `AsyncViewSet` or `AsyncModelViewSet`.
`permission_classes` is one of the supported overrides, so the
viewset can keep a sensible default and tighten or loosen access
on a per-action basis.

```python
from restflow.permissions import IsAuthenticated, IsAdminUser
from restflow.views import ActionConfig, AsyncModelViewSet


class ArticleViewSet(AsyncModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]
    action_configs = {
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

A common pattern: keep list and retrieve open to authenticated
users, restrict destroy to admins, and require ownership for
update.

```python
class ArticleViewSet(AsyncModelViewSet):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated]
    action_configs = {
        "update": ActionConfig(
            permission_classes=[IsAuthenticated & IsOwner],
        ),
        "partial_update": ActionConfig(
            permission_classes=[IsAuthenticated & IsOwner],
        ),
        "destroy": ActionConfig(permission_classes=[IsAdminUser]),
    }
```

When `permission_classes` is None on the `ActionConfig`, the
class-level value is used. This keeps the override minimal: only
state what changes.

## Configuring globally

DRF's `DEFAULT_PERMISSION_CLASSES` setting still applies. Set it to
the most restrictive permission that should be the floor for the
project, then loosen on individual views.

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "restflow.permissions.IsAuthenticated",
    ],
}
```

A common production setup is `IsAuthenticated` as the default and
`AllowAny` on the few public endpoints.

## Common pitfalls

### Coroutines from a sync hook

Returning a coroutine from a sync `has_permission` does not work.
The sync dispatch path treats the return value as a boolean, so a
coroutine evaluates as truthy and the request is allowed. Always
implement `ahas_permission` for async logic, and keep
`has_permission` synchronous when both are present.

```python
# bad: coroutine evaluated as truthy
class BrokenPermission(BasePermission):
    async def has_permission(self, request, view):
        return await some_async_check()


# good: keep the sync hook sync, use the async hook for async work
class FixedPermission(BasePermission):
    def has_permission(self, request, view):
        return some_sync_check()

    async def ahas_permission(self, request, view):
        return await some_async_check()
```

### Anonymous user on the sync flow

DRF's sync `has_permission` denies access when `request.user` is
None on classes like `IsAuthenticated`. The async overrides on
restflow's standard permissions test for None explicitly so the
behaviour is consistent. Custom permissions should follow the same
pattern: guard against a missing user before reading attributes
from it.

### Mixing async and sync operands in a combinator

Combinators detect each operand's hooks at call time. An operand
with only sync hooks runs through the default `sync_to_async`
adapter, while async-native operands run inline. Mixed trees work
without intervention; combine restflow permissions with legacy
DRF permissions freely.

### Truthy non-bool returns

A non-bool truthy return value is treated as True. This is
permitted but discouraged because it makes combinator output
harder to read and breaks the pattern that downstream tooling
expects. Always return True or False explicitly.

## Next steps

- [Permission classes API reference](../../api/permissions/permissions.md)
  lists every shipped permission with its docstring.
- [Permission combinators API reference](../../api/permissions/combinators.md)
  documents the AND, OR, and NOT classes.
