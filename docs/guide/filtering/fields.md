# Fields

Reference for every field type in Restflow, plus lookups, type
annotations, validation, and PostgreSQL features.

## Field basics

### Field arguments

| Argument | Description |
| --- | --- |
| `db_field` | Column name on the model or queryset. Defaults to the field name on the FilterSet. |
| `filter_by` | Custom lookup expression. Can be a string, or a callable that returns a `Q` object or a filter dict. Takes precedence over `db_field`. |
| `lookups` | List of lookup expressions to generate as variants. |
| `method` | Custom filter method (callable or method name on the FilterSet). |
| `negate` | When `True`, the filter excludes matches instead of including them. |
| `required` | When `True`, the FilterSet raises a validation error if the value is missing. |
| `allow_negate` | When `False`, no `!` negation variant is generated for this field. |

### filter_by takes precedence over db_field

By default, the field name is used as `db_field`, which produces
`queryset.filter(field_name=value)`.
When `filter_by` or `method` is specified `lookups` are ignored, raises exception.

```python
class ProductFilter(FilterSet):
    # runs queryset.filter(price=<value>)
    price = IntegerField()
```

```python
class ProductFilter(FilterSet):
    # query-string param is "price_value", ORM column is "price"
    # runs queryset.filter(price=<value>)
    price_value = IntegerField(db_field="price")
```

```python
class ProductFilter(FilterSet):
    # runs queryset.filter(price__gte=<value>)
    price_value = IntegerField(filter_by="price__gte")
```

### Three ways to declare fields

```python
from restflow.filters import FilterSet, StringField


class ProductFilterSet(FilterSet):
    # 1. type annotation
    name: str

    # 2. explicit field
    description = StringField(lookups=["icontains"])

    # 3. model-based with extra_kwargs
    class Meta:
        model = Product
        fields = ["price"]
        extra_kwargs = {
            "price": {"min_value": 0},
        }
```

### Field generation

Each field can generate multiple filter parameters.

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(lookups=["comparison"])


# generates:
# - price        (exact match)
# - price__gt
# - price__gte
# - price__lt
# - price__lte
# - price!       (not equal, negation)
# - price__gt!
# - price__gte!
# - price__lt!
# - price__lte!
```

## Type annotations

```python
from typing import List, Literal, Optional
from datetime import datetime, date, time
from decimal import Decimal
from restflow.filters import Email, IPAddress


class ProductFilterSet(FilterSet):
    # basic types
    name: str
    quantity: int
    rating: float
    in_stock: bool
    price: Decimal

    # date and time
    created_date: date
    created_at: datetime
    opening_time: time

    # specialised types
    contact_email: Email
    server_ip: IPAddress

    # choice types
    status: Literal["draft", "published", "archived"]
    priority: Literal[1, 2, 3, 4, 5]

    # list types
    tags: List[int]
    categories: List[str]

    # optional
    category: Optional[str]
    brand: int | None
```

## Field types

### StringField

```python
from restflow.filters import StringField


class ProductFilterSet(FilterSet):
    name = StringField()
    title = StringField(lookups=["icontains", "istartswith"])
    sku = StringField(min_length=3, max_length=20, required=True)
    category_name = StringField(filter_by="category__name__icontains")
```

**Available lookups:** `exact`, `iexact`, `contains`, `icontains`,
`startswith`, `istartswith`, `endswith`, `iendswith`, `regex`,
`iregex`.

**Lookup category:** `text` expands to `icontains`, `contains`,
`startswith`, `endswith`, `iexact`.

**Parameters:** `min_length`, `max_length`, `required`, `validators`,
`help_text`, `trim_whitespace` (default `True`), `allow_blank`,
`lookups`, `db_field`, `filter_by`, `method`.

### IntegerField

```python
from restflow.filters import IntegerField


class ProductFilterSet(FilterSet):
    quantity: int
    price = IntegerField(lookups=["comparison"])
    stock = IntegerField(min_value=0, max_value=10000)
    category_id = IntegerField(filter_by="category__id")
```

**Available lookups:** `exact`, `gt`, `gte`, `lt`, `lte`, `in`,
`range`.

**Lookup category:** `comparison` expands to `gt`, `gte`, `lt`,
`lte`.

**Parameters:** `min_value`, `max_value`, `required`, `validators`,
`help_text`, `lookups`, `db_field`, `filter_by`, `method`.

### FloatField

```python
from restflow.filters import FloatField


class ProductFilterSet(FilterSet):
    rating: float
    score = FloatField(lookups=["comparison"])
    discount = FloatField(min_value=0.0, max_value=100.0)
```

**Available lookups:** `exact`, `gt`, `gte`, `lt`, `lte`, `range`.

**Lookup category:** `comparison`.

**Parameters:** `min_value`, `max_value`, `required`, `validators`,
`help_text`, `lookups`, `db_field`, `filter_by`, `method`.

### BooleanField

```python
from restflow.filters import BooleanField


class ProductFilterSet(FilterSet):
    in_stock: bool
    is_featured = BooleanField()
    available = BooleanField(method="filter_available")
    active = BooleanField(required=True)
```

**Accepts values:** `true`, `True`, `1`, `yes` for true; `false`,
`False`, `0`, `no` for false.

**Available lookups:** `exact`, `isnull`.

**Parameters:** `required`, `help_text`, `db_field`, `filter_by`,
`method`.

### DecimalField

```python
from restflow.filters import DecimalField


class ProductFilterSet(FilterSet):
    price = DecimalField(max_digits=10, decimal_places=2)

    amount = DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        lookups=["comparison"],
    )
```

**Available lookups:** `exact`, `gt`, `gte`, `lt`, `lte`, `range`.

**Lookup category:** `comparison`.

**Parameters:** `max_digits`, `decimal_places`, `min_value`,
`max_value`, `required`, `validators`, `help_text`, `lookups`,
`db_field`, `filter_by`, `method`.

### DateField

```python
from restflow.filters import DateField


class ProductFilterSet(FilterSet):
    created_date: date
    published_date = DateField(lookups=["comparison"])
    start_date = DateField(filter_by="created_at__date__gte")
    end_date = DateField(filter_by="created_at__date__lte")
```

**Accepts formats:** ISO 8601 (`2024-01-15`), and any format
configured in DRF settings.

**Available lookups:** `exact`, `gt`, `gte`, `lt`, `lte`, `year`,
`month`, `day`, `week`, `week_day`, `quarter`.

**Lookup categories:** `comparison`, `date`.

**Parameters:** `input_formats`, `required`, `validators`,
`help_text`, `lookups`, `db_field`, `filter_by`, `method`.

### DateTimeField

```python
from restflow.filters import DateTimeField


class ProductFilterSet(FilterSet):
    created_at: datetime
    published_at = DateTimeField(lookups=["comparison"])
```

**Accepts formats:** ISO 8601 (`2024-01-15T10:30:00Z`) and any
format configured in DRF settings.

**Available lookups:** all `DateField` lookups plus `hour`, `minute`,
`second`.

**Lookup categories:** `comparison`, `date`, `time`.

**Parameters:** `input_formats`, `default_timezone`, `required`,
`validators`, `help_text`, `lookups`, `db_field`, `filter_by`,
`method`.

### TimeField

```python
from restflow.filters import TimeField


class ProductFilterSet(FilterSet):
    opening_time: time
    closing_time = TimeField(lookups=["comparison"])
```

**Accepts formats:** `14:30:00`, `14:30`.

**Available lookups:** `exact`, `gt`, `gte`, `lt`, `lte`, `hour`,
`minute`, `second`.

**Lookup categories:** `comparison`, `time`.

**Parameters:** `input_formats`, `required`, `validators`,
`help_text`, `lookups`, `db_field`, `filter_by`, `method`.

### DurationField

```python
from restflow.filters import DurationField


class ProductFilterSet(FilterSet):
    duration = DurationField(lookups=["comparison"])
```

**Lookup categories:** `comparison`, `time`.

### ChoiceField

```python
from restflow.filters import ChoiceField


class ProductFilterSet(FilterSet):
    status = ChoiceField(
        choices=[
            ("draft", "Draft"),
            ("published", "Published"),
            ("archived", "Archived"),
        ],
    )

    priority: Literal["low", "medium", "high", "urgent"]
```

**Available lookups:** `exact`, `in`.

**Parameters:** `choices`, `required`, `help_text`, `lookups`,
`db_field`, `filter_by`, `method`.

### MultipleChoiceField

```python
from restflow.filters import MultipleChoiceField


class ProductFilterSet(FilterSet):
    statuses = MultipleChoiceField(
        choices=[("draft", "Draft"), ("published", "Published")],
        filter_by="status__in",
    )
```

**Accepts:** comma-separated values (`?statuses=draft,published`).

**Available lookups:** `in`.

**Parameters:** `choices`, `required`, `help_text`, `db_field`,
`filter_by`, `method`.

### ListField

```python
from restflow.filters import ListField, IntegerField, StringField


class ProductFilterSet(FilterSet):
    tags: List[int]
    # auto-generates filter_by="tags__in"

    tag_ids = ListField(
        child=IntegerField(),
        filter_by="tags__id__in",
    )

    categories = ListField(
        child=StringField(),
        filter_by="category__name__in",
    )

    product_ids = ListField(
        child=IntegerField(min_value=1),
        min_length=1,
        max_length=100,
    )
```

**Accepts:** comma-separated (`?tags=1,2,3`) or repeated parameters
(`?tags=1&tags=2&tags=3`).

**Available lookups:** `in`, plus PostgreSQL array lookups
(`overlap`, `contains`, `contained_by`).

**Lookup category:** `pg_array`.

**Parameters:** `child` (required), `min_length`, `max_length`,
`required`, `help_text`, `lookups`, `db_field`, `filter_by`,
`method`.

### EmailField

```python
from restflow.filters import EmailField, Email


class ContactFilterSet(FilterSet):
    contact_email = EmailField()
    primary: Email   # NewType-based annotation
```

**Lookup categories:** `basic`, `text`.

### IPAddressField

```python
from restflow.filters import IPAddressField, IPAddress


class ServerFilterSet(FilterSet):
    server_ip = IPAddressField()
    edge: IPAddress    # NewType-based annotation
```

**Lookup categories:** `basic`, `text`.

### OrderField

```python
from restflow.filters import OrderField


class ProductFilterSet(FilterSet):
    ordering = OrderField(
        fields=[
            ("name", "name"),
            ("price", "price"),
            ("created_at", "created_at"),
        ],
    )


# ?ordering=name
# ?ordering=-price
```

Usually defined in `Meta.order_fields` instead. See
[FilterSet Ordering](filterset.md#ordering).

### RelatedField

```python
from restflow.filters import RelatedField


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    sku = models.CharField(max_length=12)


class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)


class ProductFilterSet(FilterSet):
    category = RelatedField(
        model=Category,
        fields=["name", "description"],
        exclude=["sku"],
    )


# generates:
# - category__name
# - category__description
```

## Lookups

```python
class ProductFilterSet(FilterSet):
    # individual lookups
    name: str
    title = StringField(lookups=["exact", "icontains"])
    price = IntegerField(lookups=["gt", "gte", "lt", "lte"])
    created_at = DateTimeField(lookups=["gte", "lte", "year", "month"])

    # lookup categories
    description = StringField(lookups=["text"])
    views = IntegerField(lookups=["comparison"])
    tags = ListField(child=StringField(), lookups=["pg_array"])
```

### Available lookup categories

| Category | Lookups |
| --- | --- |
| `basic` | `exact`, `in`, `isnull` |
| `text` | `icontains`, `contains`, `startswith`, `endswith`, `iexact` |
| `comparison` | `gt`, `gte`, `lt`, `lte` |
| `date` | `date`, `year`, `month`, `day`, `week`, `week_day`, `quarter` |
| `time` | `time`, `hour`, `minute`, `second` |
| `postgres` | `search`, `trigram_similar`, `unaccent` |
| `pg_array` | `contains`, `overlaps`, `contained_by` |

### Alias-form lookups

`lookups` also accepts a dict that maps a friendly variant suffix to
an ORM lookup. Combine it with `lookup_separator` to control how
variants are named on the query string.

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(
        lookups={"max": "lte", "min": "gte"},
        lookup_separator="_",
    )


# generates: price_max -> queryset.filter(price__lte=value)
#            price_min -> queryset.filter(price__gte=value)
```

### Per-lookup help text

Each alias value may instead be a dict that carries the ORM lookup and an
optional `help_text`. This lets each generated variant document itself
independently in the OpenAPI schema.

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(
        lookups={
            "min": {"lookup": "gte", "help_text": "Lowest acceptable price"},
            "max": {"lookup": "lte"},
        },
        lookup_separator="_",
        help_text="Product price",
    )
```

A variant resolves its help text in three steps:

- An explicit per-lookup `help_text` is used as is, so `price_min` reads
   "Lowest acceptable price".
- Otherwise, when the field has a `help_text`, the variant appends a bound
   label, so `price_max` reads "Product price (Inclusive Upper Bound)".
- Otherwise the schema falls back to an auto-generated verb hint such as
   "price is less than or equal to".

## Negation

Every filter accepts a `!` suffix.

```bash
?status!=draft
?in_stock!=true
?price!=1000

?price__gte!=100
?name__icontains!=test
?created_at__year!=2024
```

`!` works alongside lookup variants, so a field with
`lookups=["gte", "lte"]` accepts both `field__gte!` and `field__lte!`.

## Custom lookup expressions

```python
class ProductFilterSet(FilterSet):
    category_name = StringField(filter_by="category__name")
    brand = StringField(filter_by="brand__name__iexact")
    department = StringField(filter_by="category__department__name")
```

### With lookups

When combining `lookups` with a custom `filter_by`, set `db_field`
so the generated variants have a base column to attach to.

```python
class ProductFilterSet(FilterSet):
    category_name = StringField(
        db_field="category__name",
        lookups=["icontains", "istartswith"],
    )


# generates:
# category_name__icontains -> queryset.filter(category__name__icontains=value)
# category_name__istartswith -> queryset.filter(category__name__istartswith=value)
```

### Nested relationships

```python
class Region(models.Model):
    name = models.CharField(max_length=100)


class City(models.Model):
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)


class Address(models.Model):
    street = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE)


class Store(models.Model):
    name = models.CharField(max_length=100)
    address = models.ForeignKey(Address, on_delete=models.CASCADE)


class Product(models.Model):
    name = models.CharField(max_length=200)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)


class ProductFilterSet(FilterSet):
    region = StringField(filter_by="store__address__city__region__name")
    city = StringField(filter_by="store__address__city__name")
```

### Date component lookups

```python
class ProductFilterSet(FilterSet):
    created_year = IntegerField(filter_by="created_at__year")
    created_month = IntegerField(filter_by="created_at__month")
    created_day = IntegerField(filter_by="created_at__day")

    published_year = IntegerField(
        db_field="published_at__year",
        lookups=["gte", "lte"],
    )
```

### Annotated field lookups

```python
from django.db.models import Avg, Count


def add_annotations(filterset, queryset):
    return queryset.annotate(
        review_count=Count("reviews"),
        avg_rating=Avg("reviews__rating"),
    )


class ProductFilterSet(FilterSet):
    min_reviews = IntegerField(filter_by="review_count__gte")
    max_reviews = IntegerField(filter_by="review_count__lte")

    class Meta:
        preprocessors = [add_annotations]
```

## Validation

### Automatic type validation

```python
class ProductFilterSet(FilterSet):
    price: int
    rating: float
    in_stock: bool


# ?price=abc  -> {"price": ["A valid integer is required."]}
# ?rating=xyz -> {"rating": ["A valid number is required."]}
```

### Built-in validators

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(min_value=0, max_value=1000000)
    sku = StringField(min_length=3, max_length=20)
    category = StringField(required=True)
```

### Custom validators

```python
from rest_framework.exceptions import ValidationError


def validate_positive_even(value):
    if value <= 0:
        raise ValidationError("Must be positive")
    if value % 2 != 0:
        raise ValidationError("Must be even")


class ProductFilterSet(FilterSet):
    batch_size = IntegerField(validators=[validate_positive_even])
```

### Choice validation

```python
class ProductFilterSet(FilterSet):
    status = ChoiceField(
        choices=[("draft", "Draft"), ("published", "Published")],
    )


# ?status=invalid -> {"status": ["\"invalid\" is not a valid choice."]}
```

### List validation

```python
class ProductFilterSet(FilterSet):
    tags = ListField(
        child=IntegerField(min_value=1),
        min_length=1,
        max_length=10,
    )


# ?tags=        -> {"tags": ["This list may not be empty."]}
# ?tags=0,1     -> nested validation on the integer child
```

## PostgreSQL fields

### Full-text search

```python
from django.contrib.postgres.search import (
    SearchVector, SearchQuery, SearchRank,
)


class ProductFilterSet(FilterSet):
    search = StringField(method="filter_fulltext")

    def filter_fulltext(self, queryset, value):
        vector = (
            SearchVector("name", weight="A")
            + SearchVector("description", weight="B")
        )
        query = SearchQuery(value)
        return queryset.annotate(
            search=vector,
            rank=SearchRank(vector, query),
        ).filter(search=query).order_by("-rank")
```

### Array fields

```python
from django.contrib.postgres.fields import ArrayField


class Product(models.Model):
    tags = ArrayField(models.CharField(max_length=50))


class ProductFilterSet(FilterSet):
    tags = ListField(child=StringField(), lookups=["pg_array"])


# ?tags__contains=wireless
# ?tags__overlap=wireless,bluetooth
# ?tags__contained_by=wireless,bluetooth,usb,hdmi
```

### JSON fields

```python
class Product(models.Model):
    metadata = models.JSONField()


class ProductFilterSet(FilterSet):
    brand = StringField(filter_by="metadata__brand")
    color = StringField(filter_by="metadata__specs__color")
    size = StringField(filter_by="metadata__specs__size")
    has_spec = StringField(filter_by="metadata__has_key")
```

### Range fields

```python
from django.contrib.postgres.fields import IntegerRangeField


class Product(models.Model):
    price_range = IntegerRangeField()


class ProductFilterSet(FilterSet):
    contains_price = IntegerField(method="filter_price_contains")

    def filter_price_contains(self, queryset, value):
        return queryset.filter(price_range__contains=value)
```

### Trigram similarity

```python
from django.contrib.postgres.search import TrigramSimilarity


class ProductFilterSet(FilterSet):
    fuzzy_name = StringField(method="filter_fuzzy_name")

    def filter_fuzzy_name(self, queryset, value):
        return queryset.annotate(
            similarity=TrigramSimilarity("name", value),
        ).filter(similarity__gt=0.3).order_by("-similarity")
```

## Field parameters reference

### Common parameters (every field)

```python
Field(
    db_field="",
    lookups=[...],
    filter_by="...",
    required=False,
    allow_null=False,
    validators=[...],
    help_text="...",
    label="...",
    method="method_name",
)
```

### StringField parameters

```python
StringField(
    min_length=None,
    max_length=None,
    trim_whitespace=True,
    allow_blank=False,
    # plus the common parameters above
)
```

### IntegerField, FloatField, DecimalField parameters

```python
IntegerField(
    min_value=None,
    max_value=None,
    # plus the common parameters above
)


DecimalField(
    max_digits=None,
    decimal_places=None,
    min_value=None,
    max_value=None,
    # plus the common parameters above
)
```

### DateField, DateTimeField, TimeField parameters

```python
DateTimeField(
    input_formats=None,
    default_timezone=None,
    format=None,
    # plus the common parameters above
)
```

### ChoiceField, MultipleChoiceField parameters

```python
ChoiceField(
    choices=[...],     # required
    allow_blank=False,
    # plus the common parameters above
)
```

### ListField parameters

```python
ListField(
    child=Field(),     # required
    min_length=None,
    max_length=None,
    allow_empty=True,
    # plus the common parameters above
)
```

## Important caveats

### Lookups need a base column

When using `lookups` together with `method` or a custom `filter_by`,
set `db_field` so the lookup variants have a base column to attach
to.

```python
class ProductFilterSet(FilterSet):
    # bad: method + lookups without db_field raises an assertion error
    price = IntegerField(method="custom_method", lookups=["gte", "lte"])

    # bad: filter_by + lookups without db_field raises an assertion error
    price = IntegerField(filter_by="price__exact", lookups=["gte", "lte"])

    # good: db_field gives the variants a column to use
    # ?price=1 runs queryset.filter(price__exact=1)
    # ?price__gte=1 runs queryset.filter(price__gte=1)
    price = IntegerField(
        filter_by="price__exact",
        db_field="price",
        lookups=["gte", "lte"],
    )
```

### Custom methods and operators

When `method` is used, return `Q` objects so the FilterSet's
`operator` setting applies. See
[FilterSet custom method caveat](filterset.md#custom-method-caveat).

The `method` callable may be `async def` when the FilterSet is driven
through `afilter_queryset`. See
[Async support](filterset.md#async-support).

### Type annotations cannot express validation

```python
# bad: no min/max with annotations alone
price: int

# good: use an explicit declaration to add validation
price = IntegerField(min_value=0, max_value=1000000)
```

### List field input

```python
tags: List[int]


# both shapes work:
?tags=1,2,3
?tags=1&tags=2&tags=3
```

Empty parameters validate as empty strings, not empty lists. Pass
`allow_empty=True` and handle the empty case in a custom method when
that matters:

```python
tags = ListField(
    child=IntegerField(),
    allow_empty=True,
    method="filter_tags",
)


def filter_tags(self, queryset, value):
    if not value:
        return Q()
    return Q(tags__id__in=value)
```

### Negation edge cases

`?price__gte!=1000` is `NOT (price >= 1000)`, equivalent to
`?price__lt=1000`. `?field__isnull!=true` is the same as
`?field__isnull=false`.

## Next steps

- [FilterSet](filterset.md): operators, processors, ordering,
  validation, and the FilterSet API.
- [DRF Integration](integration.md): plug a FilterSet into DRF.
