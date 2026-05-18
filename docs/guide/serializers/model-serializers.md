# ModelSerializer and HyperlinkedModelSerializer

Restflow's model serializers extend DRF's classes with the same
annotation-driven field declaration as `Serializer`, plus an async
surface for `create`, `update`, and validation.


## ModelSerializer

`ModelSerializer` mirrors DRF's `ModelSerializer`. The `Meta` class
declares the model and the fields to expose, and the serializer
generates DRF fields from the model's columns.

```python
from restflow.serializers import ModelSerializer


class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "date_joined"]
```

Annotation-driven fields layer on top: any annotated name produces a
DRF field that overrides whatever the auto-generation would have
produced.

```python
from typing import Literal
from restflow.serializers import ModelSerializer, Field


class UserSer(ModelSerializer):
    role: Literal["admin", "editor", "viewer"]
    extra: str = Field(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["id", "username", "email"]
```

`role` and `extra` are added to the field set without listing them
in `Meta.fields`.

## Auto-merging annotations into Meta.fields

When `Meta.fields` is a list or tuple, the metaclass appends every
annotated name that is not already present.

```python
class UserSer(ModelSerializer):
    extra: str = Field(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username"]


# After class creation, UserSer.Meta.fields == ["id", "username", "extra"]
```

## Meta options

Every standard DRF `Meta` option is supported. The most common ones:

| Option | Purpose |
| --- | --- |
| `model` | The Django model class. |
| `fields` | Field names to include. List, tuple, or `"__all__"`. |
| `exclude` | Field names to exclude. Mutually exclusive with `fields`. |
| `read_only_fields` | Names that bypass `validate_<name>` and are skipped on input. |
| `extra_kwargs` | Per-field option overrides. |
| `depth` | Auto-nest related serializers up to this depth. |
| `validators` | Class-level DRF validators. |

```python
class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "date_joined"]
        read_only_fields = ["id", "date_joined"]
        extra_kwargs = {
            "email": {"required": True},
            "username": {"min_length": 3, "max_length": 30},
        }
```

`extra_kwargs` runs against both auto-generated fields and
annotation-driven fields. Settings declared through the `Field`
sentinel still apply on top.

## HyperlinkedModelSerializer

`HyperlinkedModelSerializer` renders related fields and the identity
field as URLs instead of primary keys. It accepts every option that
`ModelSerializer` does, plus `Meta.url_field_name` for the identity
field.

```python
from restflow.serializers import HyperlinkedModelSerializer


class ArticleSer(HyperlinkedModelSerializer):
    class Meta:
        model = Article
        fields = ["url", "title", "author", "category"]
        url_field_name = "url"
        extra_kwargs = {
            "url": {"view_name": "article-detail"},
            "author": {"view_name": "user-detail"},
            "category": {"view_name": "category-detail"},
        }
```

Annotation-driven fields, the async surface, and the `Field` sentinel
all work identically here.

## Source attributes

Use `source=` to map a serializer field to a different attribute on
the model instance.

```python
from rest_framework import serializers
from restflow.serializers import ModelSerializer


class UserSer(ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    company_name = serializers.CharField(source="profile.company.name")

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "company_name"]
```

The same applies to annotation-driven fields, declared through the
`Field` sentinel:

```python
from restflow.serializers import ModelSerializer, Field


class UserSer(ModelSerializer):
    full_name: str = Field(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username"]
```

`source="*"` lets a nested serializer flatten or reshape the
instance without needing a real attribute path; see DRF's
`Serializer` documentation for the full mechanic.

## Validation

Restflow's model serializers run validators in the same order
as DRF:

1. Field-level validators declared on the field
   (`min_length`, `validators=[...]`, etc).
2. The `validate_<name>` hook for each field, if defined.
3. The top-level `validate(self, attrs)` hook.
4. Class-level `Meta.validators`.

### validate_<name>

The sync hook is called from `to_internal_value`. The async variant is
called from `ato_internal_value`. The sync entry point refuses async
hooks with a `TypeError` whose message names `ato_internal_value`.

```python
from rest_framework.exceptions import ValidationError
from restflow.serializers import ModelSerializer


class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

    def validate_username(self, value):
        if value.startswith("_"):
            raise ValidationError("Cannot start with underscore.")
        return value
```

Async version:

```python
class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

    async def validate_username(self, value):
        exists = await User.objects.filter(username=value).aexists()
        if exists:
            raise ValidationError("Already taken.")
        return value
```

Calling `is_valid()` on this serializer raises `TypeError` because
the user callable is async; call `ais_valid()` instead.

### validate

The top-level hook handles cross-field rules. Both sync and async
versions are supported. The async `avalidate` falls back to
returning `attrs` unchanged.

```python
class PasswordSer(Serializer):
    password: str
    password_again: str

    def validate(self, attrs):
        if attrs["password"] != attrs["password_again"]:
            raise ValidationError({"password_again": "Mismatch."})
        return attrs
```

```python
class PasswordSer(Serializer):
    password: str
    password_again: str

    async def avalidate(self, attrs):
        if attrs["password"] != attrs["password_again"]:
            raise ValidationError({"password_again": "Mismatch."})
        return attrs
```

The sync `validate` hook is required for `is_valid()`. The async
`avalidate` is optional and is awaited from `arun_validation`. When
both are defined, sync code paths use `validate` and async code
paths use `avalidate`.

## Async create and update

`asave` awaits `acreate` for new instances and `aupdate` for
updates. `ModelSerializer` ships default implementations of both
that mirror DRF's sync `ModelSerializer.create` and
`ModelSerializer.update` logic using the async ORM (`acreate`,
`asave`, `aset`). No override is needed for the common case.

```python
from restflow.serializers import ModelSerializer


class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


ser = UserSer(data={"username": "alice", "email": "alice@example.com"})
await ser.ais_valid(raise_exception=True)
user = await ser.asave()
```

Override `acreate` or `aupdate` only when the default logic is not
sufficient:

```python
class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

    async def acreate(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return await User.objects.acreate(**validated_data)

    async def aupdate(self, instance, validated_data):
        send_notification = validated_data.get("email") != instance.email
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        await instance.asave()
        if send_notification:
            await notify_email_changed(instance)
        return instance
```

If only the sync `create` or `update` is overridden, `asave` falls
back to it. This keeps existing code working under async views
without a rewrite.

The sync `save()` still works the same way and refuses async
`create`/`update` overrides with a `TypeError` pointing at `asave`.

## Read-only model serialization

Read-only serializers come up often -- for example, when a list
endpoint returns a different shape than the create endpoint accepts.
The standard tools apply here:

```python
class UserListSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "date_joined"]
        read_only_fields = fields
```

For computed values, declare a `SerializerMethodField` or an
annotated read-only field through `Field`:

