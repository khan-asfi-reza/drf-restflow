# DRF integration

`RestflowFilterBackend` plugs a `FilterSet` into Django REST
Framework's filter pipeline. It does two jobs:

1. **Applies the FilterSet** to incoming querysets, so views do not
   need to call `filterset.filter_queryset(qs)` explicitly.
2. **Emits OpenAPI parameters** so every filter (including lookup
   variants like `price__gte` and negation variants like `price!`)
   shows up automatically in `/schema/` and Swagger UI.

## Setup

```python
from rest_framework import generics
from restflow.filters import RestflowFilterBackend
from myapp.filters import ProductFilterSet
from myapp.models import Product
from myapp.serializers import ProductSerializer


class ProductView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
```

That is the entire wiring. The view body does not need
`ProductFilterSet(request=request).filter_queryset(qs)`.

## Globally enabling the backend

Add it to `DEFAULT_FILTER_BACKENDS` to use it on every
`GenericAPIView`:

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": [
        "restflow.filters.RestflowFilterBackend",
    ],
}
```

Views opt in by setting `filterset_class`. Views without it pass
through unchanged.

## Dynamic FilterSets

Override `get_filterset_class()` on the view to pick a class at
request time, for example based on the user's role:

```python
class ProductView(generics.ListAPIView):
    filter_backends = [RestflowFilterBackend]

    def get_filterset_class(self):
        if self.request.user.is_staff:
            return StaffProductFilterSet
        return PublicProductFilterSet
```

Override `get_filterset(filterset_class)` to control instantiation
directly.

## OpenAPI / schema generation

The backend implements `get_schema_operation_parameters(view)`, which
DRF's built-in `AutoSchema` and `drf-spectacular` both call. Each
declared field, plus every generated lookup and negation variant,
becomes one OpenAPI parameter:

| FilterSet field | Generated parameters |
| --- | --- |
| `name: str` | `name`, `name!` |
| `price = IntegerField(lookups=["comparison"])` | `price`, `price__gt`, `price__gte`, `price__lt`, `price__lte`, plus `!` variants |
| `status: Literal["a", "b"]` | `status` (with `enum: ["a", "b"]`), `status!` |
| `tags: list[str]` | `tags` (array, `explode=true`), `tags!` |

### Type mapping

| Field | OpenAPI `schema` |
| --- | --- |
| `IntegerField` | `{type: integer}` (with `minimum`/`maximum` if set) |
| `FloatField` | `{type: number, format: float}` |
| `DecimalField` | `{type: string, format: decimal}` |
| `BooleanField` | `{type: boolean}` |
| `StringField` | `{type: string}` (with `minLength`/`maxLength`) |
| `EmailField` | `{type: string, format: email}` |
| `DateField` / `DateTimeField` / `TimeField` | `{type: string, format: date}` / `date-time` / `time` |
| `DurationField` | `{type: string, format: duration}` |
| `ChoiceField` (incl. `Literal[...]`) | `{type: string, enum: [...]}` |
| `ListField` | `{type: array, items: <child>}` |
| `OrderField` | `{type: array, items: {type: string, enum: [...]}}` |

Validators on the underlying field flow into the schema where
OpenAPI has a corresponding keyword (`minimum`, `maximum`,
`minLength`, `maxLength`).

### Descriptions

The backend auto-generates parameter descriptions from the variant
name:

- `price__gte` becomes `"price is greater than or equal to"`.
- `price!` becomes `"exclude where price"`.
- `price__gte!` becomes `"exclude where price is greater than or equal to"`.

Override per field by passing `help_text=`:

```python
class ProductFilterSet(FilterSet):
    name = StringField(help_text="Filter by product name (case-insensitive)")
```

`help_text` always wins over the auto-generated hint.

## Plain APIView

`filterset_class` works on plain `APIView` and `AsyncAPIView` too, not
only on generic views. Apply the FilterSet manually in the handler;
spectacular picks up the schema parameters from `filterset_class`
automatically.

```python
from restflow.views import AsyncAPIView
from restflow.filters import FilterSet, StringField


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])


class ProductSearchView(AsyncAPIView):
    filterset_class = ProductFilterSet

    async def get(self, request):
        qs = ProductFilterSet(request=request).filter_queryset(
            Product.objects.all()
        )
        ...
```

## Caveats

- The `!` character in negation variants is unencoded in URLs. It is
  a valid sub-delim per RFC 3986. Most clients handle it; in shell,
  quote the URL: `curl '...?price!=100'`.
