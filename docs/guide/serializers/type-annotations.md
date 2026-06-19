# Type annotations

Restflow's `Serializer`, `ModelSerializer`, and
`HyperlinkedModelSerializer` walk class-level type annotations and
turn them into DRF fields at class-creation time. This page covers
the type-to-field mapping, the `Field` sentinel, reserved names,
supported types, and inheritance rules.

## Annotation Field Mapping

The default
mapping is:

| Python type | DRF field |
| --- | --- |
| int | IntegerField |
| float | FloatField |
| str | CharField |
| bool | BooleanField |
| bytes | CharField |
| datetime.datetime | DateTimeField |
| datetime.date | DateField |
| datetime.time | TimeField |
| datetime.timedelta | DurationField |
| decimal.Decimal | DecimalField (restflow's, with max_digits=20 and decimal_places=6) |
| uuid.UUID | UUIDField |
| Email | EmailField |
| IPAddress | IPAddressField |
| dict | DictField |
| Any | JSONField |

```python
import datetime
import decimal
import uuid
from typing import Any
from restflow.serializers import Serializer, Email, IPAddress


class EverythingSer(Serializer):
    name: str
    age: int
    score: float
    active: bool
    created_at: datetime.datetime
    birthday: datetime.date
    starts_at: datetime.time
    duration: datetime.timedelta
    balance: decimal.Decimal
    token: uuid.UUID
    email: Email
    server_ip: IPAddress
    metadata: dict
    payload: Any
```

`bytes` mapping to `CharField` is intentional: DRF does not ship a
distinct bytes field, and CharField round-trips through HTTP without
loss when the content is ASCII or UTF-8 text.

## Optional and union types

`Optional[T]` and `T | None` resolve to the field for `T` with
`allow_null=True` and `required=False`. Both forms are equivalent.

```python
from restflow.serializers import Serializer


class ProfileSer(Serializer):
    bio: str | None
    age: int | None
    avatar_url: str | None = None  # see the default values gotcha below
```

Unions with more than one non-None member are rejected, since the
field type is ambiguous.

```python
class Bad(Serializer):
    value: int | str   # raises AssertionError at class creation time
```

For mixed types, declare a custom field or use `JSONField` through
the `Any` annotation.

An explicit override on a paired `Field` sentinel takes precedence.

```python
class StrictOptional(Serializer):
    bio: str | None = Field(required=True)  # required=True wins
```

## NotRequired (required=False without allow_null)

`Optional[T]` and `T | None` make a field both optional and nullable.
When you want a field that may be left out of the input but must not be
null when it is present, wrap the type in `NotRequired[T]`. It sets
`required=False` and leaves `allow_null` untouched.

```python
from restflow.serializers import NotRequired, Serializer


class SignupSer(Serializer):
    email: str
    nickname: NotRequired[str]        # optional key, but cannot be null
    referral: NotRequired[str | None] # optional key and nullable
```

`NotRequired` is the same marker used by `typing.TypedDict`, re-exported
for convenience. It composes with the other forms: `NotRequired[T | None]`
is optional and nullable, and an explicit `Field(required=True)` still
takes precedence.

```python
class Override(Serializer):
    name: NotRequired[str] = Field(required=True)  # required=True wins
```

## Literal (ChoiceField)

A `Literal` annotation produces a DRF `ChoiceField` whose `choices`
are the literal values paired with themselves.

```python
from typing import Literal
from restflow.serializers import Serializer


class UserSer(Serializer):
    role: Literal["admin", "editor", "viewer"]
    tier: Literal[1, 2, 3]
```

Choice display labels are not generated. Both the value and the label
default to the literal value. To customise labels, declare the field
explicitly.

```python
from rest_framework import serializers


class UserSer(Serializer):
    role = serializers.ChoiceField(
        choices=[
            ("admin", "Administrator"),
            ("editor", "Editor"),
            ("viewer", "Viewer"),
        ],
    )
```

The literal members can be of any hashable type. Mixed-type literals
are accepted but unusual.

```python
class WeirdSer(Serializer):
    flag: Literal[True, "yes", 1]
```

## list[T] (ListField)

A `list[T]` annotation becomes a `ListField` whose `child` is the
field for `T`.

```python
from restflow.serializers import Serializer


class TagSer(Serializer):
    names: list[str]
    counts: list[int]
    matrix: list[list[int]]
```

The inner type goes through the same resolver, so nested lists,
literals inside lists, and nested serializers inside lists all work.

`list[Literal["a", "b"]]` produces a `ListField(child=ChoiceField(choices=...))`.
`list[int | None]` produces a `ListField(child=IntegerField(allow_null=True, required=False))`.

When `T` is a serializer subclass, the resolver instantiates the
serializer with `many=True` instead of wrapping it in a `ListField`.
This matches DRF's idiomatic "nested serializer with many=True"
pattern.

```python
from restflow.serializers import Serializer


class AddressSer(Serializer):
    street: str
    city: str


class UserSer(Serializer):
    addresses: list[AddressSer]   # AddressSer(many=True), not ListField
```

## Bare list

A bare `list` annotation (without a type argument) defaults to a
string child, matching DRF's default `ListField` behaviour.

```python
class TagSer(Serializer):
    names: list   # ListField(child=CharField())
```

## Annotated

`Annotated[T, metadata]` strips the metadata and resolves `T`. The
metadata can be anything; the resolver does not interpret it.

```python
from typing import Annotated


class UserSer(Serializer):
    age: Annotated[int, "in years"]   # resolves like `age: int`
```

This is useful for documentation tools that read PEP 593 metadata
without affecting the runtime field type.

## Nested serializers

Annotating a name with another Serializer subclass creates a nested
serializer field. `list[NestedSer]` produces the same nested
serializer with `many=True`.

```python
from restflow.serializers import Serializer


class AddressSer(Serializer):
    street: str
    city: str
    zip: str


class UserSer(Serializer):
    name: str
    address: AddressSer
    previous_addresses: list[AddressSer]
```

Nested ModelSerializers work the same way.

The captured kwargs from a paired `Field` sentinel pass through to
the nested serializer constructor.

```python
class UserSer(Serializer):
    address: AddressSer = Field(allow_null=True, required=False)
```

This becomes `AddressSer(allow_null=True, required=False)`.

## The Field sentinel

`Field` is a placeholder that captures DRF kwargs. Pair it with an
annotation to layer extra options onto the resolved field.

```python
from restflow.serializers import Serializer, Field, Email


class UserSer(Serializer):
    name: str = Field(max_length=100, help_text="The user's display name")
    email: Email = Field(write_only=True)
    age: int = Field(min_value=0, max_value=150, required=False)
```

`Field()` cannot be used without an annotation. A bare `Field()`
declared on a class without a corresponding annotation has no type
information to resolve against and is ignored. To declare a regular
DRF field, use the actual class (`serializers.CharField(...)`).

The sentinel works recursively: an `Optional[Email] = Field(write_only=True)`
produces an `EmailField(allow_null=True, required=False, write_only=True)`.

## Field generation priority

When the same name is declared in multiple ways, the priority is:

**Explicit declarations > Type annotations > Inherited fields**

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

The check applies to type annotations. Avoid assigning DRF field
instances to these names as well -- it breaks the serializer in
harder-to-diagnose ways.

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

Runtime values remain plain strings.

To add more NewType aliases for project-specific types, register the
mapping in app startup.

```python
from typing import NewType
from rest_framework import serializers
from restflow.serializers import SerializerFieldMap


PhoneNumber = NewType("PhoneNumber", str)


class PhoneNumberField(serializers.CharField):
    ...


SerializerFieldMap[PhoneNumber] = PhoneNumberField
```

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
from restflow.serializers import Serializer, Field


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

Two annotation forms make a field optional without a `Field` sentinel.
`Optional[T]` and `T | None` trigger `required=False` and
`allow_null=True`, so `bio: str | None` is already optional.
`NotRequired[T]` triggers `required=False` only, so `nickname:
NotRequired[str]` may be left out but cannot be null.

`Field(default=...)` sets DRF's `default=` argument, which means the
field is allowed to be missing from the input and is filled in with
the default for `validated_data`. It is distinct from
`Field(initial=...)`, which only affects the rendered initial value
in DRF's browsable API.

## DecimalField defaults

`restflow.serializers.DecimalField` is a thin subclass of DRF's
`DecimalField` with `max_digits=20` and `decimal_places=6` as the
defaults. An annotation `balance: decimal.Decimal` resolves to this
class, so projects that store fixed-point money values get a
reasonable default precision without writing it out.

```python
import decimal


class WalletSer(Serializer):
    balance: decimal.Decimal   # max_digits=20, decimal_places=6
```

To change the precision per project, subclass and register.

```python
from restflow.serializers import DecimalField, SerializerFieldMap
import decimal


class MoneyField(DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)


SerializerFieldMap[decimal.Decimal] = MoneyField
```

For a single class, override the field through `Field`.

```python
class InvoiceSer(Serializer):
    total: decimal.Decimal = Field(max_digits=12, decimal_places=2)
```

## Unsupported annotations

Annotations that do not fit the rules raise `AssertionError` at class
creation. The error message names the offending type.

Examples that fail:

- `set[int]` -- sets are not in the mapping and do not match the
  list rule.
- `tuple[int, str]` -- tuples are not in the mapping.
- `int | str` -- non-None unions are rejected.
- A custom class that is not a Serializer subclass and is not in
  `SerializerFieldMap`.

For unsupported types, either declare the field explicitly or
register a custom mapping.

## Custom types

Two ways to plug in a new type.

### Extend SerializerFieldMap

Add a mapping from a Python type to a DRF field class. New
annotations using that type resolve through the new entry.

```python
from rest_framework import serializers
from restflow.serializers import SerializerFieldMap


class ColorField(serializers.CharField):
    pass


class Color(str):
    pass


SerializerFieldMap[Color] = ColorField
```

```python
class PaintSer(Serializer):
    primary: Color   # resolves to ColorField
```

The mapping is global, so register it during app startup (in
`AppConfig.ready`, for example). Avoid touching it from inside a
request handler.

### Explicit field declarations

When only a single class needs the custom field, declare it
explicitly instead of touching the global map.

```python
from rest_framework import serializers


class PaintSer(Serializer):
    primary = ColorField(default="white")
```

Explicit declarations win over annotations, so this works even if
the same name is annotated.

### Subclass DecimalField

The `DecimalField` re-exported from `restflow.serializers` ships
with `max_digits=20` and `decimal_places=6`. Subclass it to change
those defaults across a project.

```python
from restflow.serializers import DecimalField


class MoneyField(DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)
```

Use it as a regular DRF field, or register it in
`SerializerFieldMap` against a custom NewType for annotation-driven
declarations.

