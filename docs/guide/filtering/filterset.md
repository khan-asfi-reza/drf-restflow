# FilterSet

Complete guide to FilterSet covering everything from basics to advanced usage, Meta options, ordering, fields overview, PostgreSQL features, and all important caveats.

## Table of Contents

- [What is FilterSet](#what-is-filterset)
- [Creating FilterSets](#creating-filtersets)
- [Meta Options](#meta-options)
- [Field Overview](#field-overview)
- [Using FilterSets](#using-filtersets)
- [Ordering](#ordering)
- [Operators](#operators)
- [Preprocessors](#preprocessors)
- [Postprocessors](#postprocessors)
- [Validation](#validation)
- [PostgreSQL Features](#postgresql-features)
- [Important Caveats](#important-caveats)
- [Best Practices](#best-practices)

## What is FilterSet

FilterSet is the core class in drf-restflow. It validates query parameters and applies filters to Django querysets using a declarative, type-safe syntax.

```python
from restflow.filters import FilterSet

class ProductFilterSet(FilterSet):
    name: str
    price: int

# Usage: ?name=laptop&price=999
```

## Creating FilterSets

### Type Annotations (Simplest)

```python
class ProductFilterSet(FilterSet):
    name: str
    price: int
    in_stock: bool
    created_at: datetime
```

### Explicit Field Declarations

```python
from restflow.filters import FilterSet, StringField, IntegerField


class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"], min_value=0)
    category = IntegerField(filter_by="category__id")
```

### Model-Based Generation

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = ['name', 'price', 'category']  # Specific fields
        # or
        fields = '__all__'  # All model fields
```

### Mixed Approach

Combine custom fields with model-based generation:

```python
class ProductFilterSet(FilterSet):
    # Custom fields
    search = StringField(method="filter_search")
    trending = BooleanField(method="filter_trending")

    # Model-based fields
    class Meta:
        model = Product
        fields = ['category', 'in_stock', 'price']

    def filter_search(self, filterset, queryset, value):
        return Q(name__icontains=value) | Q(description__icontains=value)

    def filter_trending(self, filterset, queryset, value):
        if value:
            week_ago = timezone.now() - timedelta(days=7)
            return Q(created_at__gte=week_ago, views__gte=100)
        return Q()
```

### InlineFilterSet (Dynamic)

Create FilterSets dynamically without class definition:

```python
from restflow.filters import InlineFilterSet

ProductFilterSet = InlineFilterSet(
    model=Product,
    fields=['name', 'price', 'category']
)

# Or with more options
ProductFilterSet = InlineFilterSet(
    model=Product,
    fields=['name', 'price'],
    extra_kwargs={
        'name': {'lookups': ['icontains']},
        'price': {'min_value': 0}
    }
)
```

## Meta Options

The `Meta` class configures FilterSet behavior. All options are optional.

### Complete Meta Options Reference

```python
class ProductFilterSet(FilterSet):
    class Meta:
        # Model configuration
        model = Product                    # Django model to generate fields from
        fields = ['name', 'price']         # Fields to include ('__all__' for all)
        exclude = ['internal_id']          # Fields to exclude

        # Field configuration
        extra_kwargs = {                   # Configure fields without explicit declaration
            'name': {
                'lookups': ['icontains', 'istartswith'],
                'required': True,
                'min_length': 2,
                'help_text': 'Product name'
            },
            'price': {
                'lookups': ['comparison'],
                'min_value': 0,
                'max_value': 1000000
            }
        }

        # Operator
        operator = "AND"                   # Combine filters with AND/OR/XOR (default: AND)

        # Ordering
        order_fields = [                   # Fields available for ordering
            ('name', 'name'),              # (model_field, query_param)
            ('price', 'price'),
            ('created_at', 'created_at'),
        ]
        default_order_fields = ["price"]     # Default order field
        order_param = "order_by"            # Order query parameter name
        override_order_dir = "asc"          # Overrides an order direction, if set to "desc" then `-field` will be in ascending order 
        # Processors
        preprocessors = [                  # Functions to run before filtering
            exclude_deleted,
            apply_permissions,
        ]
        postprocessors = [                 # Functions to run after filtering
            apply_default_ordering,
            ensure_distinct,
        ]
```

### model

Specify the Django model to generate fields from:

```python
class Meta:
    model = Product
```

### fields

Specify which fields to include:

```python
# Specific fields
class Meta:
    model = Product
    fields = ['name', 'price', 'category']

# All fields
class Meta:
    model = Product
    fields = '__all__'

# No fields (only custom fields)
class Meta:
    model = Product
    fields = []
```

### exclude

Exclude specific fields from generation:

```python
class Meta:
    model = Product
    fields = '__all__'
    exclude = ['internal_id', 'secret_key']
```

### extra_kwargs

Configure fields without explicit declarations:

```python
class Meta:
    model = Product
    fields = ['name', 'price', 'category', 'status']
    extra_kwargs = {
        'name': {
            'lookups': ['icontains', 'istartswith'],  # Add lookup variations
            'required': True,                         # Make required
            'min_length': 2,                          # Validation
            'max_length': 200,
            'help_text': 'Product name to search'
        },
        'price': {
            'lookups': ['comparison'],                # Add gt, gte, lt, lte
            'min_value': 0,                           # Must be >= 0
            'max_value': 1000000,                     # Must be <= 1000000
            'validators': [custom_validator]          # Custom validators
        },
        'category': {
            'filter_by': 'category__id',            # Custom lookup expression
            'required': False
        },
        'status': {
            'choices': [                              # Limit to choices
                ('draft', 'Draft'),
                ('published', 'Published')
            ]
        }
    }
```

**extra_kwargs options:**
- `db_field`: Corresponding model/queryset field
- `lookups`: List of lookup expressions to generate
- `filter_by`: Custom lookup expression
- `required`: Make field required
- `min_value`, `max_value`: Numeric validation
- `min_length`, `max_length`: String validation
- `validators`: List of custom validators
- `choices`: Limit to specific choices
- `help_text`: Description for API documentation
- `method`: Custom filter method name
- Any other DRF field parameter

### operator

Control how filters are combined (default: `"AND"`):

```python
# All filters must match (default)
class Meta:
    operator = "AND"

# Any filter can match
class Meta:
    operator = "OR"

# Exactly one filter must match
class Meta:
    operator = "XOR"
```

See [Operators](#operators) section for details.

### order_fields

Define which fields can be used for ordering:

```python
class Meta:
    order_param = "sort_by"    # Query param responsible for ordering 
    order_fields = [
        ('name', 'name'),               # Can order by:`?sort_by=name` or `?sort_by=-name`
        ('price', 'price'),
        ('created_at', 'created_at'),
        ('review_count', 'reviews'),   # Annotated field
    ]
    
    default_order_fields = ["price"]  # If the value is empty, the queryset will be ordered by price
    order_field_labels = [("Item Name", "name")]  # For schema generation / viewing
    override_order_dir = "desc"  # This will reverse the ordering, queryset.order_by("-price"), will order by price in ascending order
                                # and .order_by("price") will sort by price in descending order
```

See [Ordering](#ordering) section for details.

### preprocessors

Functions that run **before** filters are applied:

```python
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)

class Meta:
    preprocessors = [exclude_deleted]
```

See [Preprocessors](#preprocessors) section for details.

### postprocessors

Functions that run **after** filters are applied:

```python
def apply_default_ordering(filterset, queryset):
    if not queryset.ordered:
        return queryset.order_by('-created_at')
    return queryset

class Meta:
    postprocessors = [apply_default_ordering]
```

See [Postprocessors](#postprocessors) section for details.

## Field Overview

FilterSet supports various field types. See [Fields](fields.md) for complete details.

### Available Field Types

```python
from restflow.filters import (
    # Basic types
    StringField, IntegerField, FloatField, BooleanField, DecimalField,

    # Date/Time
    DateField, DateTimeField, TimeField,

    # Choices
    ChoiceField, MultipleChoiceField,

    # Lists
    ListField,

    # Special
    OrderField,
)
```

### Type Annotations

Use Python type annotations for automatic field generation:

```python
from typing import List, Literal
from datetime import datetime

class ProductFilterSet(FilterSet):
    # Basic types
    name: str                                    # StringField
    price: int                                   # IntegerField
    rating: float                                # FloatField
    in_stock: bool                               # BooleanField

    # Date/Time
    created_at: datetime                         # DateTimeField

    # Choices with Literal
    status: Literal["draft", "published"]        # ChoiceField

    # Lists
    tags: List[int]                              # ListField with IntegerField child
    categories: List[str]                        # ListField with StringField child
```

### Lookups

Fields can have lookup variations:

```python
class ProductFilterSet(FilterSet):
    # Single lookup
    name = StringField(lookups=["icontains"])
    # Creates: name__icontains

    # Multiple lookups
    price = IntegerField(lookups=["gte", "lte"])
    # Creates: price__gte, price__lte

    # Lookup categories
    title = StringField(lookups=["text"])
    # Creates: title__icontains, title__contains, title__startswith,
    #          title__endswith, title__iexact

    # Comparison category
    views = IntegerField(lookups=["comparison"])
    # Creates: views__gt, views__gte, views__lt, views__lte
```

**Available Categories:**

| Category Name | Lookups |
| --- | --- |
|`basic` | `["exact", "in", "isnull"]` |
|`text` | `["icontains", "contains", "startswith", "endswith", "iexact"]` |
|`comparison` | `["gt", "gte", "lt", "lte"]` |
|`date` | `["date", "year", "month", "day", "week", "week_day", "quarter"]` |
|`time` | `["time", "hour", "minute", "second"]` |
|`postgres` | `["search", "trigram_similar", "unaccent"]` |
|`pg_array` | `["contains", "overlaps", "contained_by"]` |



When using type annotations, drf-restflow maps Python types to appropriate fields:

| Python Type | Field Type | Lookup Categories |
|-------------|------------|-------------------|
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
| `Optional[T]` | Corresponding field | Same as T |


> Note: The priority of `filter_by` is higher than `db_field`, if both mentioned then `filter_by` will take precedence,
by default the field name is used as `db_field` which will perform the query

```python
class ProductFilter(FilterSet):
    # While filtering queryset it will perform queryset.filter(price=<value>)
    price = IntegerField()  
```

```python
class ProductFilter(FilterSet):
    # While filtering queryset it will perform queryset.filter(price=<value>)
    price_value = IntegerField(db_field="price")  
```


```python
class ProductFilter(FilterSet):
    # While filtering queryset it will perform queryset.filter(price__gte=<value>)
    price_value = IntegerField(filter_by="price__gte")  
```


### Lookups with method/filter_by
Cannot generate lookup variants if `db_field` is unset and `lookups` 
alongside `method` or `filter_by` is used. Always Set `db_field` 


```python
class ProductFilterSet(FilterSet):
    # ❌ WRONG - Will raise assertion error as method is used and db_field is unset
    price = IntegerField(method="custom_method", lookups=["gte", "lte"])
    # ❌ WRONG - Will raise assertion error as filter_by is used and db_field is unset
    price = IntegerField(filter_by="price__exact", lookups=["gte", "lte"])
    # ✅ CORRECT 
    # This will generate the lookup variants
    # And if query param contains ?price=1, it will perform queryset.filter(price__exact=1)
    # And for variants eg:
    # ?price__gte=1 will perform queryset.filter(price__gte=1)
    price = IntegerField(filter_by="price__exact", db_field="price", lookups=["gte", "lte"])
    

```


### Custom Lookup Expressions

```python
class ProductFilterSet(FilterSet):
    # Filter by related field
    category_name = StringField(filter_by="category__name__icontains")

    # Nested relationships
    department = StringField(filter_by="category__department__name")

    # Multiple levels
    region = StringField(filter_by="store__address__city__region__name")
```

### Negation

All filters automatically support negation with `!`:

```python
# No configuration needed - automatic!

# ?status!=draft              # NOT draft
# ?price__gte!=1000          # NOT >= 1000
# ?name__icontains!=test     # NOT containing test
```

## Using FilterSets

### In Views

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

### filter_queryset() Method

The `filter_queryset()` method applies all filters to a queryset:

```python
filterset = ProductFilterSet(request=request)
filtered_qs = filterset.filter_queryset(Product.objects.all())
```

**With ignore parameter:**

Skip specific filters when applying:

```python
# Ignore certain filters
filtered_qs = filterset.filter_queryset(
    Product.objects.all(),
    ignore=['search', 'trending']
)

# Useful when you want to apply some filters manually
# or conditionally skip certain filters
```

**Example use case:**

```python
class ProductListView(generics.ListAPIView):
    def get_queryset(self):
        queryset = Product.objects.all()
        filterset = ProductFilterSet(request=self.request)

        # Apply all filters except 'search'
        # We'll handle search separately
        queryset = filterset.filter_queryset(queryset, ignore=['search'])

        # Custom search logic with highlighting
        if 'search' in filterset.data:
            search_term = filterset.data['search']
            queryset = self.apply_custom_search(queryset, search_term)

        return queryset
```

### From Dictionary

```python
data = {'name__icontains': 'laptop', 'price__gte': 100}
filterset = ProductFilterSet(data=data)
```

### Accessing Data

```python
filterset = ProductFilterSet(request=request)

# Check if valid
if filterset.is_valid():
    # Get validated data
    data = filterset.validated_data
    # {'name': 'laptop', 'price__gte': 100}
else:
    # Get errors
    errors = filterset.errors
    # {'price': ['A valid integer is required.']}

# Get as dictionary
# Automatically does `.is_valid()`
data = filterset.model_dump()
```

## Ordering

Add ordering/sorting to your FilterSet.

### Using Meta.order_fields

```python
class ProductFilterSet(FilterSet):
    name: str
    price: int

    class Meta:
        # If the value is empty, the queryset will be ordered by price
        order_param = "sort_by"    # Query param responsible for ordering, by default set to 'order_by'
        order_fields = [
            ('name', 'name'),               # Can order by:`?sort_by=name` or `?sort_by=-name`
            ('price', 'price'),
            ('created_at', 'created_at'),
            ('review_count', 'reviews'),   # Annotated field
        ]
        
        default_order_fields = ["price"]  
        order_field_labels = [("Item Name", "name")]  # For schema generation / viewing
        override_order_dir = "asc"  

# Usage:
# ?sort_by=name          # Ascending
# ?sort_by=-name         # Descending
# ?sort_by=price         # By price ascending
# ?sort_by=-created_at   # Newest first
```

### Overriding order direction.

```python
class ProductFilterSet(FilterSet):
    name: str
    price: int

    class Meta:
        order_fields = [
            ('name', 'name'),               # Can order by:`?sort_by=name` or `?sort_by=-name`
            ('price', 'price'),
            ('created_at', 'created_at'),
            ('review_count', 'reviews'),   # Annotated field
        ]
        override_order_dir = "desc"  

# Usage:
# ?order_by=name          # Descending
# ?order_by=-name         # Ascending
# ?order_by=price         # By price descending
# ?order_by=-created_at   # Oldest first
```

### Ordering by Annotated Fields

```python
from django.db.models import Count

def add_annotations(filterset, queryset):
    return queryset.annotate(
        review_count=Count('reviews')
    )

class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [add_annotations]
        order_fields = [
            ('name', 'name'),
            ('review_count', 'reviews'),  # Order by annotation
        ]

# Usage:
# ?order_by=reviews       # Least reviews first
# ?order_by=-reviews      # Most reviews first
```

### Using OrderField Explicitly

```python
from restflow.filters import OrderField

class ProductFilterSet(FilterSet):
    ordering = OrderField(
        fields=[
            ('name', 'name'),
            ('price', 'price'),
            ('created_at', 'created_at'),
        ]
    )

# Usage same as Meta.order_fields
# ?ordering=name
# ?ordering=-price
```

### Default Ordering with Postprocessor

```python

class ProductFilterSet(FilterSet):
    class Meta:
        default_order_fields = ["price"]
        order_fields = [('name', 'name'), ('created_at', 'created_at')]
        postprocessors = [apply_default_ordering]

# Queries without ?order_by get default ordering by price
```

## Operators

Operators control how multiple filters are combined.

### AND Operator (Default)

All conditions must match:

```python
class ProductFilterSet(FilterSet):
    name: str
    category: str

    class Meta:
        operator = "AND"  # Default

# ?name=laptop&category=electronics
# SQL: WHERE name='laptop' AND category='electronics'
```

### OR Operator

Any condition can match:

```python
class ProductFilterSet(FilterSet):
    name: str
    description: str

    class Meta:
        operator = "OR"

# ?name__icontains=wireless&description__icontains=bluetooth
# SQL: WHERE name ILIKE '%wireless%' OR description ILIKE '%bluetooth%'
```

### XOR Operator

Exactly one condition must match:

```python
class ProductFilterSet(FilterSet):
    is_new: bool
    is_refurbished: bool

    class Meta:
        operator = "XOR"

# ?is_new=true&is_refurbished=true
# Returns items that are EITHER new OR refurbished (not both)
```

### Operator with Custom Methods

**⚠️ CRITICAL CAVEAT:** Operators only work correctly when custom methods return Q objects:

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")
    category: str

    class Meta:
        operator = "OR"

    # ✅ CORRECT - Returns Q object
    def filter_in_stock(self, filterset, queryset, value):
        if value:
            return Q(inventory__gt=0)
        return Q()

    # ❌ WRONG - Returns QuerySet (operator ignored!)
    def filter_in_stock_wrong(self, filterset, queryset, value):
        if value:
            return queryset.filter(inventory__gt=0)
        return queryset
```

See [Custom Method Caveat](#custom-method-caveat) for details.

## Preprocessors

Preprocessors transform querysets **before** filters are applied.

### Basic Usage

```python
def exclude_deleted(filterset, queryset):
    """Always exclude soft-deleted items"""
    return queryset.filter(deleted_at__isnull=True)

class ProductFilterSet(FilterSet):
    name: str

    class Meta:
        preprocessors = [exclude_deleted]
```

### Multiple Preprocessors

Run in order declared:

```python
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)

def apply_permissions(filterset, queryset):
    if filterset.request and not filterset.request.user.is_staff:
        return queryset.filter(status='published')
    return queryset

def optimize_queries(filterset, queryset):
    return queryset.select_related('category').prefetch_related('tags')

class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [
            exclude_deleted,      # 1. Filter deleted
            apply_permissions,    # 2. Apply permissions
            optimize_queries,     # 3. Optimize
        ]
```

### Adding Annotations

```python
from django.db.models import Count, Avg

def add_review_stats(filterset, queryset):
    return queryset.annotate(
        review_count=Count('reviews'),
        avg_rating=Avg('reviews__rating')
    )

class ProductFilterSet(FilterSet):
    min_reviews = IntegerField(method="filter_min_reviews")
    min_rating = FloatField(method="filter_min_rating")

    class Meta:
        preprocessors = [add_review_stats]

    def filter_min_reviews(self, filterset, queryset, value):
        return Q(review_count__gte=value)

    def filter_min_rating(self, filterset, queryset, value):
        return Q(avg_rating__gte=value)
```

### Request-Based Filtering

```python
def tenant_isolation(filterset, queryset):
    """Multi-tenant data isolation"""
    if not filterset.request or not filterset.request.user.is_authenticated:
        return queryset.none()

    tenant = filterset.request.user.tenant
    return queryset.filter(tenant=tenant)

class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [tenant_isolation]
```

### Conditional Optimization

```python
def smart_optimization(filterset, queryset):
    """Only optimize what's needed"""
    # Always select related ForeignKeys
    queryset = queryset.select_related('category', 'brand')

    # Conditionally prefetch M2M
    if 'tags' in filterset.data:
        queryset = queryset.prefetch_related('tags')

    if 'reviews' in filterset.request.query_params:
        queryset = queryset.prefetch_related('reviews')

    return queryset

class ProductFilterSet(FilterSet):
    class Meta:
        preprocessors = [smart_optimization]
```

## Postprocessors

Postprocessors transform querysets **after** filters are applied.

### Basic Usage

```python
def apply_default_ordering(filterset, queryset):
    if not queryset.ordered:
        return queryset.order_by('-created_at')
    return queryset

class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [apply_default_ordering]
```

### Ensure Distinct

```python
def ensure_distinct(filterset, queryset):
    """Remove duplicates from M2M filtering"""
    return queryset.distinct()

class ProductFilterSet(FilterSet):
    tags: List[int]

    class Meta:
        postprocessors = [ensure_distinct]
```


### Audit Logging

```python
import logging
logger = logging.getLogger(__name__)

def log_filter_usage(filterset, queryset):
    if filterset.request:
        user = getattr(filterset.request.user, 'username', 'anonymous')
        filters = dict(filterset.data)
        logger.info(f"User {user} filtered: {filters}")
    return queryset

class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [log_filter_usage]
```

### Performance Monitoring

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
            f"Slow query: {duration:.2f}s for {count} results. "
            f"Filters: {dict(filterset.data)}"
        )
    return queryset

class ProductFilterSet(FilterSet):
    class Meta:
        postprocessors = [monitor_performance]
```

## Validation

### Automatic Validation

FilterSet uses DRF serializers for automatic type validation:

```python
class ProductFilterSet(FilterSet):
    price: int  # Only accepts integers

# ?price=abc → {"price": ["A valid integer is required."]}
```

### Field-Level Validation

```python
from rest_framework.validators import MinValueValidator

class ProductFilterSet(FilterSet):
    price = IntegerField(
        min_value=0,
        max_value=1_000_000,
        validators=[MinValueValidator(0)]
    )

# ?price=-10 → {"price": ["Ensure this value is greater than or equal to 0."]}
```

### FilterSet-Level Validation

```python
from rest_framework.exceptions import ValidationError

class ProductFilterSet(FilterSet):
    min_price = IntegerField(filter_by="price__gte")
    max_price = IntegerField(filter_by="price__lte")

    def validate(self, data):
        if 'min_price' in data and 'max_price' in data:
            if data['min_price'] > data['max_price']:
                raise ValidationError({
                    'max_price': 'Must be greater than min_price'
                })
        return data

# ?min_price=1000&max_price=500 → 400 Bad Request
```

### Custom Validators

```python
from rest_framework.exceptions import ValidationError

def validate_even(value):
    if value % 2 != 0:
        raise ValidationError("Must be an even number")

class ProductFilterSet(FilterSet):
    batch_size = IntegerField(validators=[validate_even])
```

## PostgreSQL Features

drf-restflow supports PostgreSQL-specific features. See [Fields](fields.md) for complete PostgreSQL field details.

### Full-Text Search

```python
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

class ProductFilterSet(FilterSet):
    search = StringField(method="filter_fulltext_search")

    def filter_fulltext_search(self, filterset, queryset, value):
        vector = SearchVector('name', weight='A') + SearchVector('description', weight='B')
        query = SearchQuery(value)
        return queryset.annotate(
            search=vector,
            rank=SearchRank(vector, query)
        ).filter(search=query).order_by('-rank')

# ?search=wireless headphones
# Uses PostgreSQL full-text search with ranking
```

### Array Fields

```python
from django.contrib.postgres.fields import ArrayField

class Product(models.Model):
    tags = ArrayField(models.CharField(max_length=50))

class ProductFilterSet(FilterSet):
    tags = ListField(
        child=StringField(),
        lookups=["pg_array"]  # PostgreSQL array lookups
    )

# ?tags__contains=wireless       # Array contains value
# ?tags__overlap=wireless,bluetooth  # Array overlaps with values
# ?tags__contained_by=a,b,c     # Array contained by values
```

### JSON Fields

```python
from django.db import models

class Product(models.Model):
    metadata = models.JSONField()

class ProductFilterSet(FilterSet):
    # Filter by JSON key
    brand = StringField(filter_by="metadata__brand")
    color = StringField(filter_by="metadata__specs__color")

# ?brand=Apple
# ?color=red
```

### Using SearchVector in Preprocessor

```python
from django.contrib.postgres.search import SearchVector

def add_search_vector(filterset, queryset):
    """Add search vector for better full-text search"""
    if 'search' in filterset.data:
        return queryset.annotate(
            search_vector=SearchVector('name', 'description', 'tags')
        )
    return queryset

class ProductFilterSet(FilterSet):
    search = StringField(method="filter_search")

    class Meta:
        preprocessors = [add_search_vector]

    def filter_search(self, filterset, queryset, value):
        from django.contrib.postgres.search import SearchQuery
        return queryset.filter(search_vector=SearchQuery(value))
```

## Important Caveats

### Custom Method Caveat

**⚠️ CRITICAL:** When custom methods return QuerySet instead of Q objects, the FilterSet operator is **NOT applied**.

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")
    category: str

    class Meta:
        operator = "OR"  # ⚠️ Won't apply to QuerySet returns!

    # ❌ WRONG - Returns QuerySet
    def filter_in_stock(self, filterset, queryset, value):
        if value:
            return queryset.filter(inventory__gt=0)
        return queryset

# Query: ?in_stock=true&category=electronics
# Expected (OR): in_stock=true OR category=electronics
# Actual: in_stock=true AND category=electronics  (Operator ignored!)
```

**✅ SOLUTION:** Always return Q objects:

```python
def filter_in_stock(self, filterset, queryset, value):
    if value:
        return Q(inventory__gt=0)
    return Q()  # Empty Q matches everything
```

**Why Q objects?**
- Work correctly with ALL operators (AND, OR, XOR)
- Properly combined with other filters
- More predictable behavior
- Better for complex queries

### Annotation Performance

❌ **Don't annotate in each filter method:**

```python
def filter_min_reviews(self, filterset, queryset, value):
    # Bad - annotation repeated for each call
    return queryset.annotate(count=Count('reviews')).filter(count__gte=value)
```

✅ **Annotate once in preprocessor:**

```python
def add_annotations(filterset, queryset):
    return queryset.annotate(review_count=Count('reviews'))

class Meta:
    preprocessors = [add_annotations]

def filter_min_reviews(self, filterset, queryset, value):
    return Q(review_count__gte=value)
```

### Request Access

**Always check if request exists:**

```python
def user_filter(filterset, queryset):
    # ✅ Check request exists
    if not filterset.request:
        return queryset

    if not filterset.request.user.is_authenticated:
        return queryset.filter(is_public=True)

    return queryset
```

### Processor Return Values

**Always return queryset:**

```python
# ✅ Good
def my_processor(filterset, queryset):
    return queryset.filter(active=True)

# ❌ Bad - returns None
def my_processor(filterset, queryset):
    queryset.filter(active=True)  # Missing return!
```

## Best Practices

### Always Return Q Objects from Custom Methods

```python
# ✅ Always prefer Q objects
def filter_method(self, filterset, queryset, value):
    return Q(field=value)

# ❌ Avoid QuerySet returns (unless using AND operator, or you really need to)
def filter_method(self, filterset, queryset, value):
    return queryset.filter(field=value)
```

### Use extra_kwargs for Simple Configuration

```python
# ✅ Clean and maintainable
class Meta:
    model = Product
    fields = ['name', 'price']
    extra_kwargs = {
        'name': {'lookups': ['icontains']},
        'price': {'min_value': 0}
    }

# ❌ More verbose
name = StringField(lookups=['icontains'])
price = IntegerField(min_value=0)
```

### Keep Processors Simple

```python
# ✅ Single responsibility principle
def exclude_deleted(filterset, queryset):
    return queryset.filter(deleted_at__isnull=True)

# ❌ Too many responsibilities
def do_everything(filterset, queryset):
    queryset = queryset.filter(deleted_at__isnull=True)
    queryset = queryset.select_related('category')
    queryset = queryset.annotate(count=Count('items'))
    return queryset
```

### Processor Order Matters

```python
class Meta:
    preprocessors = [
        exclude_deleted,      # 1. Filter first
        apply_permissions,    # 2. Then permissions
        add_annotations,      # 3. Add annotations
        optimize_queries,     # 4. Finally optimize
    ]
```


### Use ignore Parameter Wisely

```python
# Useful for custom handling of specific filters
filtered_qs = filterset.filter_queryset(
    queryset,
    ignore=['search']  # Handle search separately with highlighting
)
```

## Next Steps

- **[Fields](fields.md)** - Complete guide to all field types, lookups, validation, and PostgreSQL features
- **[Filtering Tutorial](../../tutorial/filtering.md)** - Step-by-step tutorial with practical examples