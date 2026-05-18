# Helpers

`restflow.helpers` collects small utilities that the rest of the
library leans on. Type aliases for serializers, async / sync
bridge helpers for code that has to support both worlds, and a
couple of plain dict / attribute helpers.

The module is public. Importing from it is supported and stable.

## Type aliases

Three `NewType` aliases that flag intent on serializer fields. Each
one is a thin wrapper over `str` so type checkers treat them as
distinct types while runtime behavior stays a string.

```python
from restflow.helpers import Email, IPAddress, BlankableString
```

### `Email`

Marks a field as an email address. The default field map in
`restflow.serializers` resolves an `Email` annotation to
`serializers.EmailField()`.

```python
class CustomerSerializer(Serializer):
    email: Email
```

### `IPAddress`

Marks a field as an IP address. Resolves to
`serializers.IPAddressField()` so both IPv4 and IPv6 inputs are
validated.

```python
class AuditEntrySerializer(Serializer):
    client_ip: IPAddress
```

### `BlankableString`

A string that allows the empty string. Resolves to
`serializers.CharField(allow_blank=True)`. Plain `str` annotations
default to a non-blank `CharField`, so this alias is the way to opt
into blank input without writing the field by hand.

```python
class FeedbackSerializer(Serializer):
    note: BlankableString
```

## Async / sync bridge

Code paths that may receive either a regular value or an awaitable
use these three helpers to stay sync-friendly without sprinkling
`isinstance` checks.

### `maybe_await(value)`

Awaits the value when it is awaitable, returns it as-is otherwise.

```python
result = await maybe_await(callable_or_awaitable())
```

### `require_sync(value, async_alternative)`

Returns the value when it is not awaitable. When it is, the
coroutine is closed and a `TypeError` is raised pointing at the
`async_alternative` argument.

```python
data = require_sync(
    user_callback(request),
    async_alternative="auser_callback",
)
```

This guards sync entry points from accepting an async callable that
would silently never run. The error message names the async
alternative so the call site knows which method to switch to.

### `run_sync(value)`

Returns the value when it is not awaitable. When it is, the
coroutine is driven to completion through `async_to_sync`. Use
this in sync paths that must accept either a sync or an async
callable.

```python
data = run_sync(user_callback(request))
```

`require_sync` is the right choice when async input is a programmer
error. `run_sync` is the right choice when async input is allowed
but has to be waited on inline.
