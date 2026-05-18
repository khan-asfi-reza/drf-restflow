# Key Constructors

A `KeyConstructor` describes how to build a cache key from a function
call. Each attribute is a `CacheKeyField` that pulls a piece of data
out of the call and turns it into a deterministic string. The
constructor joins those slices into the final key.

## Anatomy of a cache key

Every key produced by a `KeyConstructor` has three parts:

```
<namespace>::<function-id>::<partition>::<suffix>
```

- The **function id** is the function's dotted path
  (`myapp.views.get_user`) or whatever value is passed as
  `Meta.key_identifier`.
- The **namespace** is an optional `Meta.namespace` placed in front
  of the function id.
- The **partition** is the part built from key fields with
  `partition=True`. Entries that share the same partition prefix can
  be wiped together with `delete_by_prefix(...)`.
- The **suffix** is the part built from the non-partition key fields.

## Declaring a constructor

```python
from restflow.caching import (
    KeyConstructor, ArgsKeyField, ConstantKeyField, QueryParamsKeyField,
)


class UserPayloadKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    version = ConstantKeyField("v", "1")
    page = QueryParamsKeyField(["page", "size"])

    class Meta:
        namespace = "users"
        version = 1
        max_key_suffix_length = 250
        hash_suffix_on_overflow = True
```

`Meta` is optional. The full set of options:

| Option | Default | Effect |
| --- | --- | --- |
| `namespace` | `""` | String prefix in front of every generated key. |
| `version` | `1` | Bumping invalidates every key produced by this constructor. |
| `key_identifier` | `""` | Replaces the per-function identifier. Useful when two functions should share a cache. |
| `max_key_suffix_length` | settings default (`250`) | Maximum suffix length before overflow handling kicks in. |
| `hash_suffix_on_overflow` | settings default (`False`) | When `True`, suffixes longer than `max_key_suffix_length` are replaced with their SHA-256 digest. When `False`, the suffix is truncated. |

`max_key_suffix_length` and `hash_suffix_on_overflow` fall back to the
values in
`RESTFLOW_SETTINGS["CACHE_SETTINGS"]` (see [Settings](../settings.md))
when not set on `Meta`.

## InlineKeyConstructor

Build the constructor class from a plain dict of
fields without writing a subclass.

```python
from restflow.caching import InlineKeyConstructor, ArgsKeyField


UserKey = InlineKeyConstructor(
    fields={"user": ArgsKeyField("user_id", partition=True)},
    namespace="users",
)


@cache_result(UserKey, ttl=60)
def get_user(user_id: int): ...
```

Calls with the same `fields` and Meta values return the cached class,
so repeated decorator runs on the same module do not pile up new
subclasses.

## DefaultKeyConstructor

When `@cache_result` is used without a key constructor, the wrapper
uses `DefaultKeyConstructor`, which captures every positional and
keyword argument. Each unique combination of arguments produces a
separate cache entry, with no namespace and no partition.

```python
from restflow.caching import cache_result


@cache_result(ttl=60)
def expensive_op(a: int, b: int):
    return a + b
```

## Cache key fields

The available `CacheKeyField` subclasses, each with their key
parameters.

### ConstantKeyField

A fixed `key: value` pair on every call. Useful for tagging keys with
values that do not depend on call arguments, like an environment
label, an app version, or a feature flag.

```python
class UserKey(KeyConstructor):
    env = ConstantKeyField("env", "production")
    user = ArgsKeyField("user_id", partition=True)
```

### ArgsKeyField

Captures function arguments by name.

```python
class UserKey(KeyConstructor):
    user = ArgsKeyField("user_id", partition=True)
    lang = ArgsKeyField("lang")
```

- `arguments` accepts `"*"` for every bound argument, a single name,
  or a list of names.
- `path` applies a dotted attribute path to each captured value
  before stringification, so `ArgsKeyField("user", path="id")`
  records `user.id` rather than the user object itself.
- `normalizer` runs on each resolved value, useful for coercion to
  primitives. If the normalizer raises, the original value is used.

### RequestValueKeyField

Reads a value off the request object using a dotted path.

```python
class UserKey(KeyConstructor):
    user = RequestValueKeyField("user.id", partition=True)
```

- `path` is the dotted path applied to the request, like `"user.id"`
  or `"META.HTTP_X_TENANT"`.
- `request_arg` defaults to `"request"`. Change it when the wrapped
  function takes the request under a different name.
- `view_self_request_fallback` is `True` by default, which lets DRF
  viewset methods that receive `self` resolve `self.request`.

### QueryParamsKeyField

Captures values from the request's query string.

```python
class ListUsersKey(KeyConstructor):
    filters = QueryParamsKeyField(["status", "role"])
```

- `params` accepts `"*"` for every parameter, a single name, or a
  list of names. Multi-value parameters are recorded sorted, so
  `?tag=a&tag=b` and `?tag=b&tag=a` produce the same key.
- `request_arg` and `view_self_request_fallback` work the same way
  as on `RequestValueKeyField`.

### DjangoModelKeyField

Fingerprints a Django model's schema. Useful when the cached payload
depends on the model's shape, so a migration that adds, removes, or
retypes a field invalidates the cache automatically. The payload is
always hashed.

```python
class UserKey(KeyConstructor):
    shape = DjangoModelKeyField(User)
```

### DrfSerializerKeyField

Fingerprints a DRF serializer's shape. Useful when the cached
response would change if the serializer changes, since adding or
removing a field invalidates the cache automatically. Walks nested
serializers and list serializers. The payload is always hashed.

```python
class ListUsersKey(KeyConstructor):
    shape = DrfSerializerKeyField(UserSerializer)
```

## Common parameters on every key field

Every `CacheKeyField` accepts the same three keyword arguments:

| Parameter | Default | Effect |
| --- | --- | --- |
| `partition` | `False` | When `True`, the field's contribution moves into the cache key prefix. Entries that share a prefix can be wiped with `delete_by_prefix(...)`. |
| `hash_value` | `False` | When `True`, the stringified payload is replaced with its SHA-256 digest. Useful for long or sensitive payloads. |
| `sort_lists` | `True` | When `True`, list and tuple items are sorted before stringification, so `f([1, 2])` and `f([2, 1])` share a cache entry. Set to `False` when list order is meaningful. Dict keys are always sorted. |

## Partition vs suffix

Choose `partition=True` for a field to wipe a group of related entries
together. Typical examples:

- A user id, so that `delete_by_prefix(user_id=42)` drops every
  cached entry tagged with that user for the given function.
- A tenant id, for multi-tenant isolation.
- A locale, to drop everything for a language at once.

Choose the default (`partition=False`) for fields that produce many
distinct cache entries within the same partition, like page numbers
or sort orders.

Example:

```python
class BaseKeyConstructor(KeyConstructor):
    user_id = ArgsKeyField("user_id", partition=True)
    
    class Meta:
        identifier = "user_data"
        version = 1

class Constructor1(BaseKeyConstructor):
    part = ConstantKeyField("part", "a")

class Constructor2(BaseKeyConstructor):
    part = ConstantKeyField("part", "b")

# both share the same prefix `restflow.cache.user_data::user_id:42`
# so `delete_by_prefix(user_id=42)` will drop both

```

## Where to next

- [cache_result](cache-result.md): apply a constructor to a function
  and use the resulting wrapper.
- [Invalidation Rules](invalidation.md): connect Django model signals
  to cache invalidation.
- [Settings](../settings.md): tune `MAX_KEY_SUFFIX_LENGTH` and
  `HASH_SUFFIX_ON_OVERFLOW` globally.
