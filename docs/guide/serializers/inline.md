# InlineSerializer

`InlineSerializer` is a factory that builds a `Serializer` or
`ModelSerializer` subclass at runtime. It is useful for ad-hoc
shapes nested inside another serializer, schema-only payloads for
drf-spectacular, and one-off model variants where a dedicated class
would be overkill.


Calling `InlineSerializer(...)` returns a class, not an instance:

```python
from restflow.serializers import InlineSerializer


PingSer = InlineSerializer(name="PingSer", fields={"name": str})
print(PingSer)               # <class 'PingSer'>
print(PingSer.__bases__)     # (<class '...Serializer'>,)
ser = PingSer(data={"name": "Ada"})
ser.is_valid(raise_exception=True)
```

Without a `model=`, the result is a `Serializer` subclass. With
`model=`, it is a `ModelSerializer` subclass.

## Signature

```python
InlineSerializer(
    name=None,
    fields=None,
    extra_kwargs=None,
    read_only_fields=None,
    write_only_fields=None,
    model=None,
    model_fields=None,
)
```

| Parameter | Description |
| --- | --- |
| `name` | Class name for the generated subclass. Defaults to `"<Model>Serializer"` when `model` is given, otherwise `"_Serializer"`. |
| `fields` | Mapping of field name to a DRF field instance or a Python type. |
| `extra_kwargs` | Per-field kwargs merged into the `Meta` class for the model variant. |
| `read_only_fields` | Names that get `{"read_only": True}` merged into `extra_kwargs`. |
| `write_only_fields` | Names that get `{"write_only": True}` merged into `extra_kwargs`. |
| `model` | Django model class. Switches to `ModelSerializer` mode. |
| `model_fields` | `Meta.fields` value for the model variant. List, tuple, or `"__all__"`. |

At least one of `model` or `fields` must be provided. Calling with
neither raises `ValueError`.

## Plain serializer mode

Without `model`, the factory returns a `Serializer` subclass. The
`fields=` mapping is required and supplies the entire field set.

```python
from restflow.serializers import InlineSerializer, Email


PingSer = InlineSerializer(
    name="PingSer",
    fields={
        "name": str,
        "email": Email,
        "score": int,
    },
)
```

`extra_kwargs`, `read_only_fields`, and `write_only_fields` are
ignored in plain serializer mode -- they only apply when a model is
present. To configure individual fields here, pass real DRF field
instances inside `fields=`:

```python
from rest_framework import serializers


PingSer = InlineSerializer(
    name="PingSer",
    fields={
        "name": serializers.CharField(max_length=100),
        "score": serializers.IntegerField(min_value=0),
    },
)
```

## Model serializer mode

Pass a Django model class to `model=` to build a `ModelSerializer`
subclass:

```python
from restflow.serializers import InlineSerializer


UserSer = InlineSerializer(
    model=User,
    model_fields=["id", "username", "email"],
)
```

`Meta.fields` is set from `model_fields` when given, otherwise from
the keys of the `fields=` mapping, otherwise from `"__all__"`.

```python
# fields takes precedence as a default for Meta.fields
UserSer = InlineSerializer(
    model=User,
    fields={"extra": str},
)
# Meta.fields == ["extra"]
```

```python
# explicit model_fields wins
UserSer = InlineSerializer(
    model=User,
    fields={"extra": str},
    model_fields=["id", "username", "extra"],
)
# Meta.fields == ["id", "username", "extra"]
```

```python
# fall back to all model fields
UserSer = InlineSerializer(model=User)
# Meta.fields == "__all__"
```

The `fields=` mapping in model mode adds explicit declarations on
top of the model-derived fields, the same as on a hand-written
`ModelSerializer`.

## Field values

`fields=` accepts two kinds of values:

- A DRF `Field` instance, used directly.
- A Python type, resolved using the same rules as annotation-driven field declarations.

```python
from rest_framework import serializers
from restflow.serializers import InlineSerializer, Email


PingSer = InlineSerializer(
    name="PingSer",
    fields={
        "name": str,                                    # CharField
        "email": Email,                                  # EmailField
        "tags": list[int],                               # ListField with IntegerField child
        "color": serializers.CharField(max_length=7),    # explicit DRF field
    },
)
```

Nested serializers work too: pass another Serializer subclass as
the value, or a `list[NestedSer]` for a many=True nested field.

## read_only_fields and write_only_fields

Both only apply in model serializer mode.

```python
UserSer = InlineSerializer(
    model=User,
    model_fields=["id", "username", "email", "password"],
    read_only_fields=["id"],
    write_only_fields=["password"],
)


# Equivalent to:
class UserSer(ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        extra_kwargs = {
            "id": {"read_only": True},
            "password": {"write_only": True},
        }
```

When the same name appears in both an explicit `extra_kwargs` and
`read_only_fields` or `write_only_fields`, explicit `extra_kwargs`
entries take precedence.

## Naming

When `name` is not given, the factory falls back to:

- `"{Model}Serializer"` in model mode (for example, `"UserSerializer"`).
- `"_Serializer"` in plain serializer mode.

The string controls the generated class's `__name__`, so it shows
up in error messages, repr output, and OpenAPI schemas. Pick a
distinct name when the default would collide with another class.

## Examples

### Schema-only payloads

For drf-spectacular endpoints that return a custom shape:

```python
from drf_spectacular.utils import extend_schema
from restflow.serializers import InlineSerializer


@extend_schema(
    responses=InlineSerializer(
        name="HealthCheckResponse",
        fields={
            "status": str,
            "uptime_seconds": int,
            "version": str,
        },
    ),
)
def health_check(request):
    ...
```

### Nested inside another serializer

```python
from rest_framework import serializers
from restflow.serializers import InlineSerializer, Serializer


class OrderSer(Serializer):
    order_id: str
    items = InlineSerializer(
        name="OrderItem",
        fields={
            "sku": str,
            "quantity": int,
            "price": float,
        },
    )(many=True)
```

The trailing `(many=True)` instantiates the generated class as a
list serializer, the same way any DRF serializer subclass would be
used.

### Quick model variant

```python
UserListSer = InlineSerializer(
    model=User,
    model_fields=["id", "username", "date_joined"],
    read_only_fields=["id", "date_joined"],
)


UserCreateSer = InlineSerializer(
    model=User,
    model_fields=["username", "email", "password"],
    write_only_fields=["password"],
)
```

### Mixed model and ad-hoc fields

```python
UserSer = InlineSerializer(
    model=User,
    model_fields=["id", "username", "extra"],
    fields={
        "extra": str,
    },
    extra_kwargs={
        "extra": {"required": False},
    },
)
```

## Caveats

- **Type checkers.** Dynamically generated classes are opaque to
  static analysis. Downstream code that introspects the returned
  class's attributes may need its own annotations or `# type: ignore`
  comments.
- **Pickling.** Generated classes live wherever the call site is.
  Pickling instances of an inline serializer requires the class to
  be findable by import path; if it is constructed inside a
  function, pickle will not be able to locate it. For values that
  need to round-trip through pickle (Celery results, caches), use a
  module-level class definition instead.
- **drf-spectacular.** Inline serializers play nicely with
  drf-spectacular as long as the `name` is distinct. Reusing the
  same `name` for different shapes produces ambiguous schema
  components.
- **Mutable Meta in model mode.** The factory builds a fresh `Meta`
  per call. Mutating attributes on the returned class's `Meta`
  affects only that class.
- **No async surface here directly.** Inline serializers inherit
  from the restflow `Serializer` or `ModelSerializer`, so the async
  surface (`ais_valid`, `asave`, and friends) is available through
  the returned class. To override `acreate` or `aupdate`, declare a
  full subclass instead -- the factory does not accept method
  overrides.
