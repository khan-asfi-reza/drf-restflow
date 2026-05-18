# Serializers

Restflow ships a thin layer over DRF's serializer classes that
adds type-annotation-driven field declaration and an async surface.
The public API stays compatible with vanilla DRF, so any DRF tutorial
or existing knowledge carries over. The two big additions worth
internalising up front are: annotated names become DRF fields through
a metaclass, and every sync serializer method has an async variant
(prefixed with `a`) that awaits user-supplied async callables.

## Restflow Serializers

Restflow's serializers extend DRF's classes with five things.

- **Type-annotation-driven fields.** Annotated names become DRF fields
  through a metaclass, so `name: str` declares a `CharField` without
  writing it out by hand. See the
  [Type annotations guide](type-annotations.md) for the full mapping.
- **An async surface.** Every sync entry point has an async variant:
  `is_valid` becomes `ais_valid`, `save` becomes `asave`, and so on.
  The sync hooks refuse async user callables so async code paths
  never accidentally run through `async_to_sync`.
- **The InlineSerializer factory.** A one-call constructor that
  builds a Serializer or ModelSerializer subclass at runtime. See
  the [InlineSerializer guide](inline.md).
- **A request/response split.** The view layer accepts separate
  serializer classes for input and output (covered in the views
  guide). Existing single-serializer views keep working unchanged.

Everything else is unchanged from DRF.


| Class | Use it when |
| --- | --- |
| Serializer | Validation or shaping with no underlying Django model. |
| ModelSerializer | Standard create, update, and read paths against a Django model. |
| HyperlinkedModelSerializer | HATEOAS-style APIs where related objects render as URLs instead of primary keys. |
| InlineSerializer | Ad-hoc shapes inside another serializer, schema-only payloads for drf-spectacular, or one-off model variants without a dedicated class. |

## Quick examples

### Serializer

```python
from typing import Literal
from restflow.serializers import Serializer, Email


class UserSer(Serializer):
    name: str
    age: int
    email: Email
    role: Literal["admin", "user"]


ser = UserSer(data={"name": "Ada", "age": 36, "email": "ada@x.test", "role": "admin"})
ser.is_valid(raise_exception=True)
print(ser.validated_data)
```

### ModelSerializer

```python
from restflow.serializers import ModelSerializer, Field


class UserSer(ModelSerializer):
    extra: str = Field(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email"]
```

The annotated `extra` field is auto-merged into `Meta.fields`, so it
does not need to be repeated.

### HyperlinkedModelSerializer

```python
from restflow.serializers import HyperlinkedModelSerializer


class ArticleSer(HyperlinkedModelSerializer):
    class Meta:
        model = Article
        fields = ["url", "title", "author"]
        extra_kwargs = {"url": {"view_name": "article-detail"}}
```

Related fields render as URLs, and the identity field defaults to
`url` instead of the primary key.

### InlineSerializer

```python
from restflow.serializers import InlineSerializer, Email


PingSer = InlineSerializer(
    name="PingSer",
    fields={"name": str, "email": Email, "score": int},
)
```

The factory returns a Serializer subclass when no model is given, or
a ModelSerializer subclass when `model=` is provided.

## The async surface in depth

Every sync method on a serializer has an async variant. Sync entry
points refuse async user callables (validators, `validate_<name>`,
`validate`, `create`, `update`); async entry points await them.

| Sync | Async | What it does |
| --- | --- | --- |
| is_valid() | ais_valid() | Validates initial_data, populates validated_data and errors. |
| to_internal_value() | ato_internal_value() | Runs each field's run_validation plus validate_<name> hooks. |
| run_validation() | arun_validation() | Drives to_internal_value plus the top-level validate hook. |
| to_representation() | ato_representation() | Renders an instance for output. |
| validate() | avalidate() | Top-level cross-field validation hook. Override one or both. |
| save() | asave() | Calls create or update (or their async variants). |
| create() | acreate() | Persists a new instance. |
| update() | aupdate() | Persists an updated instance. |

Behaviour notes worth memorising.

- The sync `to_internal_value`, `run_validation`, and `save` raise
  `TypeError` if a user callable (`validate_<name>`, `validate`,
  `create`, `update`) returns a coroutine. The error message names
  the async variant to use instead.
- `asave` falls back to the sync `create` or `update` when the async
  twin is not overridden, so existing sync subclasses keep working
  under async views without a rewrite.
- `acreate` and `aupdate` raise `NotImplementedError` by default,
  matching DRF's sync behaviour.
- `ato_representation` awaits an async `to_representation` override
  when present. Nested async serializers are not auto-awaited; render
  them explicitly inside the override if needed.
- `avalidate` defaults to returning `attrs` unchanged. Override only
  when async cross-field validation is required.
- `arun_validation` awaits the user's `validate` method through
  `maybe_await`, so a sync `validate` and an async `avalidate` can
  coexist. When both are defined, `arun_validation` awaits whichever
  one the user actually calls (typically the async path uses
  `validate` because `arun_validation` calls `self.validate`).

## Sync vs async semantics

The sync and async paths share the same field declaration code and
the same primitive validation flow. They differ in how user callables
are dispatched.

```python
# sync path: refuses coroutines
class UserSer(Serializer):
    username: str

    def validate_username(self, value):
        return value.lower()

# async path: awaits coroutines
class UserSer(Serializer):
    username: str

    async def validate_username(self, value):
        if await User.objects.filter(username=value).aexists():
            raise serializers.ValidationError("taken")
        return value
```

Calling `is_valid()` on the second class raises `TypeError`. Call
`ais_valid()` instead.

The reason for the strict refusal is that silently running a
coroutine through `async_to_sync` from inside `is_valid` is a
performance trap and the wrapped coroutine runs on a fresh event
loop that does not see any of the request's existing async context,
and small bugs (a forgotten await) become huge production problems.
The async variant makes the intent explicit.

## Field generation priority

When the same name is declared in multiple ways, the priority is:

**Explicit declarations > Type annotations > Inherited fields**

The metaclass walks the class body in three passes.

1. Explicit DRF field instances declared on the subclass are
   collected first. `Field()` is excluded because it is a sentinel,
   not a real DRF field.
2. Annotated names that do not appear in the explicit list are
   resolved through `get_field_from_type`. If the annotation is
   paired with a `Field()` sentinel, the captured kwargs are merged
   into the resolved field.
3. Inherited fields from base classes are added for any name not
   already covered.

The resulting `_declared_fields` dict is `inherited + annotated +
explicit`, with later passes winning when a name appears in multiple
passes. This mirrors the precedence rule above.

```python
from rest_framework import serializers
from restflow.serializers import Serializer, Field


class BaseSer(Serializer):
    name: str
    code: str


class UserSer(BaseSer):
    # explicit declaration wins over the inherited annotation
    name = serializers.CharField(max_length=200)

    # annotation wins over the inherited annotation, with extra kwargs
    code: str = Field(max_length=10)

    # new annotation
    email: str
```

## Reserved attribute names

A handful of names are part of the Serializer protocol and cannot be
used as annotated field names.

- data
- errors
- validated_data
- instance
- initial_data
- fields
- context

Annotating any of these raises `ValueError` at class creation.

```python
class Bad(Serializer):
    data: str   # raises ValueError: `data` collides with a Serializer attribute
```

The check covers annotations only. Explicit DRF field declarations on
these names are out of scope for the metaclass guard, but they break
the serializer harder, so do not do it.

## Default values

A plain assignment after an annotation does NOT set a DRF default.
The assigned value is treated as a class attribute and ignored by
the metaclass.

```python
class UserSer(Serializer):
    name: str = "anonymous"     # the "anonymous" string is dropped
```

To set a default, use the `Field` sentinel.

```python
from restflow.serializers import Field


class UserSer(Serializer):
    name: str = Field(default="anonymous")
    role: str = Field(default="user", required=False)
```

The same rule applies to `required=False`. An annotation alone
produces a required field; mark it optional through `Field`.

```python
class UserSer(Serializer):
    nickname: str = Field(required=False)
```

The one exception is `Optional[T]` and `T | None`: the union with
`None` triggers `required=False` and `allow_null=True` automatically,
so `bio: str | None` is already optional.

## Field sentinel

`Field` is a placeholder that captures DRF kwargs. Pair it with an
annotation to layer extra options onto the resolved field.

```python
from restflow.serializers import Serializer, Field, Email


class UserSer(Serializer):
    name: str = Field(max_length=100, help_text="display name")
    email: Email = Field(write_only=True)
    age: int = Field(min_value=0, max_value=150, required=False)
```


## Email and IPAddress aliases

`Email` and `IPAddress` are `NewType` aliases re-exported from
`restflow.helpers`. They look like plain `str` to the type checker
but resolve to `EmailField` and `IPAddressField` through the mapping.

```python
from restflow.serializers import Serializer, Email, IPAddress


class ContactSer(Serializer):
    email: Email
    server_ip: IPAddress
```

Because `NewType` does not produce a real subclass, runtime values
remain plain strings. The aliases exist purely so the annotation hits
a different cell in `SerializerFieldMap`.

## Validators and validate hooks

Validators apply on the field directly, exactly as in DRF.

```python
from rest_framework.validators import UniqueValidator


class UserSer(ModelSerializer):
    username: str = Field(validators=[UniqueValidator(queryset=User.objects.all())])

    class Meta:
        model = User
        fields = ["username"]
```

`validate_<name>` hooks fire from `to_internal_value` (sync) or
`ato_internal_value` (async). The sync path refuses async hooks with
a `TypeError` whose message names the async variant.

```python
class UserSer(Serializer):
    username: str

    def validate_username(self, value):
        if value.startswith("_"):
            raise serializers.ValidationError("Cannot start with underscore.")
        return value
```

Async version.

```python
class UserSer(Serializer):
    username: str

    async def validate_username(self, value):
        exists = await User.objects.filter(username=value).aexists()
        if exists:
            raise serializers.ValidationError("Already taken.")
        return value
```

Calling `is_valid()` on this serializer raises `TypeError` because
the user callable is async; call `ais_valid()` instead.

## Top-level validate

The top-level `validate` hook handles cross-field rules. Both sync
and async versions are supported. The async `avalidate` defaults to
returning `attrs` unchanged.

```python
class PasswordSer(Serializer):
    password: str
    password_again: str

    def validate(self, attrs):
        if attrs["password"] != attrs["password_again"]:
            raise serializers.ValidationError({"password_again": "Mismatch."})
        return attrs
```

```python
class PasswordSer(Serializer):
    password: str
    password_again: str

    async def avalidate(self, attrs):
        if attrs["password"] != attrs["password_again"]:
            raise serializers.ValidationError({"password_again": "Mismatch."})
        return attrs
```

The sync `validate` hook is required for `is_valid()`. The async
`avalidate` is optional and is awaited from `arun_validation`. When
both are defined, sync code paths use `validate` and async code paths
use whichever the user invokes from `arun_validation` (the default
`arun_validation` calls `self.validate`, then awaits the result if
it is awaitable, so a single `async def validate` works under both
path names).

## create, update, save

`save()` calls `create(validated_data)` for new instances and
`update(instance, validated_data)` for existing ones. The async
`asave` calls `acreate`/`aupdate` when overridden, falling back to
the sync versions otherwise.

```python
from restflow.serializers import ModelSerializer


class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

    async def acreate(self, validated_data):
        return await User.objects.acreate(**validated_data)

    async def aupdate(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        await instance.asave()
        return instance
```

When only the sync `create` or `update` is overridden, `asave` falls
back to it. This keeps existing code working under async views
without a rewrite, at the cost of running synchronous ORM calls
inside the event loop. Migrate hot paths to the async variants as
needed.

The sync `save()` still works the same way and refuses async
`create`/`update` overrides with a `TypeError` pointing at `asave`.

## Where to go next

- [Type annotations](type-annotations.md): the full mapping table,
  reserved names, the Field sentinel, custom types, every resolution
  rule documented.
- [ModelSerializer and HyperlinkedModelSerializer](model-serializers.md):
  Meta options, async create or update, source attributes, related
  fields.
- [InlineSerializer](inline.md): the factory signature, plain and
  model-driven variants, every kwarg.
- [Serializer API reference](../../api/serializers/serializers.md):
  the four classes and their attributes.
- [Field utilities API reference](../../api/serializers/fields.md):
  `Field`, `DecimalField`, `SerializerFieldMap`,
  `get_field_from_type`.
