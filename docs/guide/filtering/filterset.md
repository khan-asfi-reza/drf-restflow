# FilterSet

`FilterSet` is the core class of the filtering subsystem. It validates
query parameters and applies filters to a Django queryset using
DRF's serializer infrastructure underneath.

## FilterSet

A `FilterSet` is a declarative class that validates incoming query
parameters and applies filters to a Django queryset.

```python
from restflow.filters import FilterSet


class ProductFilterSet(FilterSet):
    name: str
    price: int


# request: ?name=laptop&price=999
```

## Creating FilterSets

### Type annotations

```python
from datetime import datetime


class ProductFilterSet(FilterSet):
    name: str
    price: int
    in_stock: bool
    created_at: datetime
```

### Explicit field declarations

```python
from restflow.filters import FilterSet, StringField, IntegerField


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"], min_value=0)
    category = IntegerField(filter_by="category__id")
```

### Model-based generation

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = ["name", "price", "category"]
        # or
        fields = "__all__"
```

### Mixed approach

```python
from restflow.filters import FilterSet, StringField, BooleanField


class ProductFilterSet(FilterSet):
    search = StringField(method="filter_search")
    trending = BooleanField(method="filter_trending")

    class Meta:
        model = Product
        fields = ["category", "in_stock", "price"]

    def filter_search(self, queryset, value):
        return Q(name__icontains=value) | Q(description__icontains=value)

    def filter_trending(self, queryset, value):
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return Q(created_at__gte=week_ago, views__gte=100)
        return Q()
```

### InlineFilterSet

`InlineFilterSet` is a factory that builds a FilterSet class on the
fly. The signature mirrors the Meta options of a class-based
FilterSet, so the same knobs are available without writing the
class boilerplate.

```python
from restflow.filters import InlineFilterSet


ProductFilterSet = InlineFilterSet(
    model=Product,
    fields=["name", "price", "category"],
)

ProductFilterSet = InlineFilterSet(
    model=Product,
    fields=["name", "price"],
    extra_kwargs={
        "name": {"lookups": ["icontains"]},
        "price": {"min_value": 0},
    },
)
```

Either `model` or `fields` is required. Calling with neither raises
`ValueError`. The factory returns a `FilterSet` subclass that can
be used anywhere a class-based FilterSet works (`RestflowFilterBackend`,
direct `filter_queryset` calls, manual instantiation).

| Argument | Type | Default | Effect |
|---|---|---|---|
| `name` | `str` | derived from model name or `_FilterSet` | Class name on the generated subclass. |
| `fields` | `dict[str, Field \| type]` or `list[str]` | `None` | Explicit field declarations or a model field name list. |
| `extra_kwargs` | `dict[str, dict]` | `{}` | Per-field overrides applied to model-generated fields. |
| `model` | `type[Model]` | `None` | Django model the FilterSet filters against. |
| `order_param` | `str` | `""` | Query parameter name for ordering. Empty string disables auto-generation when `order_fields` is also empty. |
| `order_fields` | `list[tuple[str, str]]` | `None` | Pairs of (query value, model field) used by the auto-generated `OrderField`. |
| `default_order_fields` | `list[str]` | `None` | Ordering applied when the request does not pick one. |
| `order_field_labels` | `list[tuple[str, str]]` | `None` | Display labels for the ordering options. |
| `override_order_direction` | `"asc"` or `"desc"` or `None` | `None` | Forces direction regardless of the prefix on the query value. |
| `preprocessors` | `list[Callable]` | `None` | Functions that run before filters are applied. |
| `postprocessors` | `list[Callable]` | `None` | Functions that run after filters are applied. |
| `operator` | `"AND"` or `"OR"` or `"XOR"` | `"AND"` | Logical operator combining filter conditions. |
| `allow_negate` | `bool` | `True` | Generates negation variants for model and annotated fields. |

When `fields` is a dict, each value is either a `Field` instance or
a Python type. Type values go through the same resolution path as
class-level annotations, so `IntegerField`, `StringField`,
`BooleanField`, and the rest are picked up automatically.

### Field declaration priority

When the same field is declared in multiple ways, the priority is:

**Explicit declarations > Type annotations > Model fields**

```python
class ProductFilterSet(FilterSet):
    # this takes precedence
    name = StringField(lookups=["icontains"])

    # this is ignored
    name: str

    class Meta:
        model = Product
        fields = ["name"]            # ignored: explicit declaration wins
        extra_kwargs = {
            "name": {"allow_negate": False},  # also ignored
        }
```

## Meta options

The `Meta` class configures FilterSet behaviour. Every option is
optional.

```python
class ProductFilterSet(FilterSet):
    class Meta:
        # model configuration
        model = Product
        fields = ["name", "price"]
        exclude = ["internal_id"]

        # field configuration
        extra_kwargs = {
            "name": {
                "lookups": ["icontains", "istartswith"],
                "required": True,
                "min_length": 2,
                "help_text": "Product name",
            },
            "price": {
                "lookups": ["comparison"],
                "min_value": 0,
                "max_value": 1000000,
            },
        }

        # operator
        operator = "AND"

        # ordering
        order_fields = [
            ("name", "name"),
            ("price", "price"),
            ("created_at", "created_at"),
        ]
        default_order_fields = ["price"]
        order_param = "order_by"
        override_order_direction = "asc"
        order_field_labels = [("name", "Name"), ("price", "Price")]

        # processors
        preprocessors = [exclude_deleted, apply_permissions]
        postprocessors = [apply_default_ordering, ensure_distinct]
```

### model

```python
class Meta:
    model = Product
```

### fields

```python
class Meta:
    model = Product
    fields = ["name", "price", "category"]   # specific fields

class Meta:
    model = Product
    fields = "__all__"                        # all model fields

class Meta:
    model = Product
    fields = []                                # only custom fields
```

### exclude

```python
class Meta:
    model = Product
    fields = "__all__"
    exclude = ["internal_id", "secret_key"]
```

### extra_kwargs

Configures fields without explicit declarations.

```python
class Meta:
    model = Product
    fields = ["name", "price", "category", "status"]
    extra_kwargs = {
        "name": {
            "lookups": ["icontains", "istartswith"],
            "required": True,
            "min_length": 2,
            "max_length": 200,
            "help_text": "Product name to search",
        },
        "price": {
            "lookups": ["comparison"],
            "min_value": 0,
            "max_value": 1000000,
            "validators": [custom_validator],
        },
        "category": {
            "filter_by": "category__id",
            "required": False,
        },
        "status": {
            "choices": [("draft", "Draft"), ("published", "Published")],
        },
    }
```

`extra_kwargs` accepts:

- `db_field`, `lookups`, `filter_by`, `method`
- `required`, `min_value`, `max_value`, `min_length`, `max_length`,
  `validators`, `choices`, `help_text`
- Any other DRF field parameter

### operator

Controls how filters combine. The default is `"AND"`.

```python
class Meta:
    operator = "AND"   # all filters must match (default)

class Meta:
    operator = "OR"    # any filter can match

class Meta:
    operator = "XOR"   # exactly one filter must match
```

See [Operators](#operators).

### order_fields

```python
class Meta:
    order_param = "sort_by"
    order_fields = [
        ("name", "name"),
        ("price", "price"),
        ("created_at", "created_at"),
        ("review_count", "reviews"),
    ]
    default_order_fields = ["price"]
    order_field_labels = [("name", "Name"), ("price", "Price")]
    override_order_direction = "desc"
```

See [Ordering](#ordering).

### preprocessors

Functions that run before filters are applied.

```python
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)


class Meta:
    preprocessors = [exclude_deleted]
```

See [Preprocessors](#preprocessors).

### postprocessors

Functions that run after filters are applied.

```python
def apply_default_ordering(filterset, queryset):
    if not queryset.ordered:
        return queryset.order_by("-created_at")
    return queryset


class Meta:
    postprocessors = [apply_default_ordering]
```

See [Postprocessors](#postprocessors).

### allow_negate

Controls whether negation variants (`field!`) are generated for
fields. The default is `True`. Set to `False` to drop the variants
across the whole FilterSet, or override per field by passing
`allow_negate=False` to a field.

```python
class Meta:
    model = Product
    fields = "__all__"
    allow_negate = False
```

The Meta value applies to fields generated from the model and from
type annotations. Explicitly declared fields keep the value passed
to the field constructor. See [Negation](#negation).

### lookup_separator

The separator placed between a field name and its lookup variant
suffix. Defaults to Django's `LOOKUP_SEP` (`"__"`), so the variant
of `price` with `gte` is `price__gte`.

```python
class Meta:
    model = Product
    fields = "__all__"
    lookup_separator = "_"
```

A field-level `lookup_separator` overrides the Meta value, so the
final precedence is field > Meta > `LOOKUP_SEP`. The result with
the example above is `price_gte` instead of `price__gte`.

## filter_by and db_field

Two parameters control how a field maps to the ORM.

- `filter_by` is the lookup expression applied to the queryset. It
  can be a Django ORM string (`"name__icontains"`,
  `"category__id"`), a callable that returns a `Q` object, or a
  callable that returns a filter dict.
- `db_field` is the column name used when generating lookup variants.
  It defaults to the field name on the FilterSet.

`filter_by` takes precedence over `db_field`. By default, the field
name is used as `db_field`, which produces
`queryset.filter(field_name=value)`.

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

When combining `lookups` with `method` or a custom `filter_by`, set
`db_field` so the lookup variants have a base column to attach to.

```python
class ProductFilterSet(FilterSet):
    # bad: lookups + filter_by without db_field raises an assertion error
    # because there is no base column for the variant names to attach to.
    price = IntegerField(filter_by="price__exact", lookups=["gte", "lte"])

    # good: db_field gives the variants a column to use.
    # ?price=1 runs queryset.filter(price__exact=1)
    # ?price__gte=1 runs queryset.filter(price__gte=1)
    price = IntegerField(
        filter_by="price__exact",
        db_field="price",
        lookups=["gte", "lte"],
    )
```

The same applies when combining `lookups` with `method`:

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(
        method="custom_method",
        db_field="price",
        lookups=["gte", "lte"],
    )

    def custom_method(self, queryset, value):
        return Q(price=value)
```

## Field overview

```python
from restflow.filters import (
    StringField, IntegerField, FloatField, BooleanField, DecimalField,
    DateField, DateTimeField, TimeField, DurationField,
    ChoiceField, MultipleChoiceField,
    ListField, OrderField, RelatedField,
    EmailField, IPAddressField, Field,
)
```

### Type annotations

```python
from typing import List, Literal
from datetime import datetime


class ProductFilterSet(FilterSet):
    name: str
    price: int
    rating: float
    in_stock: bool
    created_at: datetime
    status: Literal["draft", "published"]
    tags: List[int]
    categories: List[str]
```

### Lookups

```python
class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["gte", "lte"])
    title = StringField(lookups=["text"])      # category
    views = IntegerField(lookups=["comparison"])  # category
```

Available categories:

| Category | Lookups |
| --- | --- |
| `basic` | `exact`, `in`, `isnull` |
| `text` | `icontains`, `contains`, `startswith`, `endswith`, `iexact` |
| `comparison` | `gt`, `gte`, `lt`, `lte` |
| `date` | `date`, `year`, `month`, `day`, `week`, `week_day`, `quarter` |
| `time` | `time`, `hour`, `minute`, `second` |
| `postgres` | `search`, `trigram_similar`, `unaccent` |
| `pg_array` | `contains`, `overlaps`, `contained_by` |

### Type annotation mapping

| Python type | Field type | Lookup categories |
| --- | --- | --- |
| `str` | `StringField` | basic, text |
| `int` | `IntegerField` | basic, comparison |
| `float` | `FloatField` | basic, comparison |
| `bool` | `BooleanField` | basic |
| `datetime.date` | `DateField` | basic, comparison, date |
| `datetime.datetime` | `DateTimeField` | basic, comparison, date, time |
| `datetime.time` | `TimeField` | basic, comparison, time |
| `decimal.Decimal` | `DecimalField` | basic, comparison |
| `List[T]` | `ListField` | basic |
| `Literal[...]` | `ChoiceField` | basic |
| `Optional[T]` / `T \| None` | corresponding field for `T` | same as `T` |

### Negation

Every filter automatically supports negation with the `!` suffix.

```bash
?status!=draft
?price__gte!=1000
?name__icontains!=test
```

## Using FilterSets

### Through RestflowFilterBackend

The DRF integration handles the wiring automatically:

```python
from rest_framework import generics
from restflow.filters import RestflowFilterBackend


class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet
```

See the [DRF Integration guide](integration.md) for the full
backend behaviour.

### Manual filter_queryset

For lower-level control, or use cases outside DRF generic views:

```python
from rest_framework import generics
from rest_framework.exceptions import ValidationError


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = Product.objects.all()
        filterset = ProductFilterSet(request=self.request)

        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        return filterset.filter_queryset(queryset)
```

### filter_queryset() with ignore

Skip specific filters when applying:

```python
filtered_qs = filterset.filter_queryset(
    Product.objects.all(),
    ignore=["search", "trending"],
)
```

### From a dictionary

```python
data = {"name__icontains": "laptop", "price__gte": 100}
filterset = ProductFilterSet(data=data)
```

### Accessing data

```python
filterset = ProductFilterSet(request=request)

if filterset.is_valid():
    data = filterset.validated_data
    # {"name": "laptop", "price__gte": 100}
else:
    errors = filterset.errors
    # {"price": ["A valid integer is required."]}

# model_dump() runs is_valid() and returns the validated data, or
# raises ValidationError on failure.
data = filterset.model_dump()
```

## Ordering

Add ordering through `Meta.order_fields`.

```python
class ProductFilterSet(FilterSet):
    name: str
    price: int

    class Meta:
        order_param = "sort_by"
        order_fields = [
            ("name", "name"),
            ("price", "price"),
            ("created_at", "created_at"),
            ("review_count", "reviews"),    # annotated field
        ]
        default_order_fields = ["price"]
        order_field_labels = [("name", "Item Name")]
        override_order_direction = "asc"
```

```bash
?sort_by=name
?sort_by=-price
?sort_by=name,-created_at
```

### override_order_direction

`override_order_direction="desc"` reverses the meaning of the `-`
prefix. With this set, `?order_by=name` orders descending and
`?order_by=-name` orders ascending.

```python
class Meta:
    order_fields = [("name", "name"), ("price", "price")]
    override_order_direction = "desc"
```

### Annotated fields

```python
from django.db.models import Count


def add_annotations(filterset, queryset):
    return queryset.annotate(review_count=Count("reviews"))


class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [add_annotations]
        order_fields = [
            ("name", "name"),
            ("review_count", "reviews"),
        ]
```

### Explicit OrderField

```python
from restflow.filters import OrderField


class ProductFilterSet(FilterSet):
    ordering = OrderField(
        fields=[("name", "name"), ("price", "price")],
    )
```

```bash
?ordering=name
?ordering=-price
```

### Default ordering with a postprocessor

```python
def apply_default_ordering(filterset, queryset):
    if not queryset.ordered:
        return queryset.order_by("-created_at")
    return queryset


class Meta:
    default_order_fields = ["price"]
    order_fields = [("name", "name"), ("created_at", "created_at")]
    postprocessors = [apply_default_ordering]
```

## Operators

Operators control how multiple filters combine.

### AND (default)

```python
class ProductFilterSet(FilterSet):
    name: str
    category: str

    class Meta:
        operator = "AND"


# ?name=laptop&category=electronics
# SQL: WHERE name = 'laptop' AND category = 'electronics'
```

### OR

```python
class ProductFilterSet(FilterSet):
    name: str
    description: str

    class Meta:
        operator = "OR"


# ?name__icontains=wireless&description__icontains=bluetooth
# SQL: WHERE name ILIKE '%wireless%' OR description ILIKE '%bluetooth%'
```

### XOR

```python
class ProductFilterSet(FilterSet):
    is_new: bool
    is_refurbished: bool

    class Meta:
        operator = "XOR"


# ?is_new=true&is_refurbished=true
# returns rows where exactly one of the conditions matches
```

### Operator with custom methods

Operators only apply when custom methods return `Q` objects, not
querysets.

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")
    category: str

    class Meta:
        operator = "OR"

    # good: returning a Q object lets the FilterSet operator combine
    # this with other filters.
    def filter_in_stock(self, queryset, value):
        if value:
            return Q(inventory__gt=0)
        return Q()

    # bad: returning a queryset bypasses the operator setting.
    def filter_in_stock_wrong(self, queryset, value):
        if value:
            return queryset.filter(inventory__gt=0)
        return queryset
```

See [Custom method caveat](#custom-method-caveat).

## Preprocessors

Preprocessors transform the queryset before filters are applied.

### Basic usage

```python
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)


class ProductFilterSet(FilterSet):
    name: str

    class Meta:
        preprocessors = [exclude_deleted]
```

### Multiple preprocessors

They run in declaration order.

```python
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)


def apply_permissions(filterset, queryset):
    if filterset.request and not filterset.request.user.is_staff:
        return queryset.filter(status="published")
    return queryset


def optimize_queries(filterset, queryset):
    return queryset.select_related("category").prefetch_related("tags")


class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [
            exclude_deleted,
            apply_permissions,
            optimize_queries,
        ]
```

### Adding annotations

```python
from django.db.models import Avg, Count


def add_review_stats(filterset, queryset):
    return queryset.annotate(
        review_count=Count("reviews"),
        avg_rating=Avg("reviews__rating"),
    )


class ProductFilterSet(FilterSet):
    min_reviews = IntegerField(method="filter_min_reviews")
    min_rating = FloatField(method="filter_min_rating")

    class Meta:
        preprocessors = [add_review_stats]

    def filter_min_reviews(self, queryset, value):
        return Q(review_count__gte=value)

    def filter_min_rating(self, queryset, value):
        return Q(avg_rating__gte=value)
```

### Request-based filtering

```python
def tenant_isolation(filterset, queryset):
    if not filterset.request or not filterset.request.user.is_authenticated:
        return queryset.none()

    tenant = filterset.request.user.tenant
    return queryset.filter(tenant=tenant)


class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [tenant_isolation]
```

### Conditional optimization

```python
def smart_optimization(filterset, queryset):
    queryset = queryset.select_related("category", "brand")

    if "tags" in filterset.data:
        queryset = queryset.prefetch_related("tags")

    if filterset.request and "reviews" in filterset.request.query_params:
        queryset = queryset.prefetch_related("reviews")

    return queryset


class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [smart_optimization]
```

## Postprocessors

Postprocessors transform the queryset after filters are applied.

### Basic usage

```python
def apply_default_ordering(filterset, queryset):
    if not queryset.ordered:
        return queryset.order_by("-created_at")
    return queryset


class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [apply_default_ordering]
```

### Ensure distinct

```python
def ensure_distinct(filterset, queryset):
    return queryset.distinct()


class ProductFilterSet(FilterSet):
    tags: List[int]

    class Meta:
        postprocessors = [ensure_distinct]
```

### Audit logging

```python
import logging

logger = logging.getLogger(__name__)


def log_filter_usage(filterset, queryset):
    if filterset.request:
        user = getattr(filterset.request.user, "username", "anonymous")
        filters = dict(filterset.data)
        logger.info("User %s filtered: %s", user, filters)
    return queryset


class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [log_filter_usage]
```

### Performance monitoring

```python
import time
import logging

logger = logging.getLogger(__name__)


def monitor_performance(filterset, queryset):
    start = time.time()
    count = queryset.count()
    duration = time.time() - start

    if duration > 1.0:
        logger.warning(
            "Slow query: %.2fs for %s results. Filters: %s",
            duration, count, dict(filterset.data),
        )
    return queryset


class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [monitor_performance]
```

## Validation

### Automatic validation

```python
class ProductFilterSet(FilterSet):
    price: int


# ?price=abc
# {"price": ["A valid integer is required."]}
```

### Field-level validation

```python
from rest_framework.validators import MinValueValidator


class ProductFilterSet(FilterSet):
    price = IntegerField(
        min_value=0,
        max_value=1_000_000,
        validators=[MinValueValidator(0)],
    )


# ?price=-10
# {"price": ["Ensure this value is greater than or equal to 0."]}
```

### FilterSet-level validation

```python
from rest_framework.exceptions import ValidationError


class ProductFilterSet(FilterSet):
    min_price = IntegerField(filter_by="price__gte")
    max_price = IntegerField(filter_by="price__lte")

    def validate(self, data):
        if "min_price" in data and "max_price" in data:
            if data["min_price"] > data["max_price"]:
                raise ValidationError({
                    "max_price": "Must be greater than min_price",
                })
        return data


# ?min_price=1000&max_price=500 -> 400 Bad Request
```

### Custom validators

```python
from rest_framework.exceptions import ValidationError


def validate_even(value):
    if value % 2 != 0:
        raise ValidationError("Must be an even number")


class ProductFilterSet(FilterSet):
    batch_size = IntegerField(validators=[validate_even])
```

## Async support

`FilterSet` exposes a parallel async entry point, `afilter_queryset`. Use it
from async views and Channels consumers, or anywhere `method=`,
preprocessor, or postprocessor callables are `async def`.

The sync `filter_queryset` and async `afilter_queryset` build the same Q
objects and apply them with `queryset.filter(...)`. The queryset itself
remains lazy in both cases. An async terminator like `aiter()`, `acount()`,
or `aget()` is still required to actually hit the database.

### Basic async use

```python
from restflow.filters import FilterSet, IntegerField


class ProductFilterSet(FilterSet):
    price = IntegerField(lookups=["gte", "lte"])


async def list_products(request):
    filterset = ProductFilterSet(request=request)
    queryset = await filterset.afilter_queryset(Product.objects.all())
    return [p async for p in queryset.aiter()]
```

### Async user callables

`method=` callables, preprocessors, and postprocessors may be `async def`.
The signature is the same as the sync version.

```python
from django.db.models import Q


async def attach_inventory(filterset, queryset):
    return await sync_to_async(some_blocking_lookup)(queryset)


class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")

    class Meta:
        preprocessors = [attach_inventory]

    async def filter_in_stock(self, queryset, value):
        if value:
            return Q(inventory__gt=0)
        return Q()
```

### Mixing sync and async

A single FilterSet can mix sync and async callables freely. Async
`afilter_queryset` runs sync callables directly and awaits async ones.
Order is preserved; processors still chain (each consumes the prior
queryset), so they run sequentially.

```python
def fast_sync_filter(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)


async def attach_external_data(filterset, queryset):
    return await sync_to_async(slow_lookup)(queryset)


class Meta:
    preprocessors = [fast_sync_filter, attach_external_data]
```

### Sync entry point and async callables

The sync `filter_queryset` raises `TypeError` if any user callable returns
a coroutine. The error message points at `afilter_queryset`. This is
deliberate: silently bridging sync to async via `async_to_sync` from inside
an already-running event loop deadlocks, so the framework refuses to guess.

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")

    async def filter_in_stock(self, queryset, value):
        return Q(inventory__gt=0)


# This raises TypeError pointing at afilter_queryset:
# ProductFilterSet(data={"in_stock": "true"}).filter_queryset(qs)
```

### Validation stays sync

`is_valid()` and `model_dump()` are pure-Python validation; no DB. They
are safe to call from an async context. Custom DRF validators must remain
sync; async validators are not supported.

## PostgreSQL features

Restflow supports PostgreSQL-specific features. See the
[Fields guide](fields.md) for the field-level details.

### Full-text search

```python
from django.contrib.postgres.search import (
    SearchVector, SearchQuery, SearchRank,
)


class ProductFilterSet(FilterSet):
    search = StringField(method="filter_fulltext_search")

    def filter_fulltext_search(self, queryset, value):
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
    tags = ListField(
        child=StringField(),
        lookups=["pg_array"],
    )


# ?tags__contains=wireless
# ?tags__overlap=wireless,bluetooth
# ?tags__contained_by=a,b,c
```

### JSON fields

```python
class Product(models.Model):
    metadata = models.JSONField()


class ProductFilterSet(FilterSet):
    brand = StringField(filter_by="metadata__brand")
    color = StringField(filter_by="metadata__specs__color")
```

### Search vector in a preprocessor

```python
from django.contrib.postgres.search import SearchVector, SearchQuery


def add_search_vector(filterset, queryset):
    if "search" in filterset.data:
        return queryset.annotate(
            search_vector=SearchVector("name", "description", "tags"),
        )
    return queryset


class ProductFilterSet(FilterSet):
    search = StringField(method="filter_search")

    class Meta:
        preprocessors = [add_search_vector]

    def filter_search(self, queryset, value):
        return queryset.filter(search_vector=SearchQuery(value))
```

## Important caveats

### Custom method caveat

When custom methods return `QuerySet` instead of `Q` objects, the
FilterSet's `operator` setting is not applied to that filter.

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")
    category: str

    class Meta:
        operator = "OR"

    # bad: queryset return bypasses the operator
    def filter_in_stock(self, queryset, value):
        if value:
            return queryset.filter(inventory__gt=0)
        return queryset


# ?in_stock=true&category=electronics
# expected: in_stock = true OR category = electronics
# actual:   in_stock = true AND category = electronics
```

The fix is to return `Q` objects:

```python
def filter_in_stock(self, queryset, value):
    if value:
        return Q(inventory__gt=0)
    return Q()   # empty Q matches everything
```

`Q` objects compose under every operator (`AND`, `OR`, `XOR`).

### Annotation performance

Annotate once in a preprocessor instead of repeating the annotation
inside each custom method.

```python
# bad: annotation repeated for each call
def filter_min_reviews(self, queryset, value):
    return queryset.annotate(count=Count("reviews")).filter(count__gte=value)

# good: annotate once, filter cheaply
def add_annotations(filterset, queryset):
    return queryset.annotate(review_count=Count("reviews"))


class Meta:
    preprocessors = [add_annotations]


def filter_min_reviews(self, queryset, value):
    return Q(review_count__gte=value)
```

### Request access

Always check that `filterset.request` exists before reading from it.

```python
def user_filter(filterset, queryset):
    if not filterset.request:
        return queryset

    if not filterset.request.user.is_authenticated:
        return queryset.filter(is_public=True)

    return queryset
```

### Processor return values

Always return the queryset from a processor.

```python
# good
def my_processor(filterset, queryset):
    return queryset.filter(active=True)

# bad: returns None
def my_processor(filterset, queryset):
    queryset.filter(active=True)
```

## Next steps

- [Fields](fields.md): every field type, lookup, validation, and
  PostgreSQL feature.
- [DRF Integration](integration.md): plug the FilterSet into DRF's
  filter pipeline.
