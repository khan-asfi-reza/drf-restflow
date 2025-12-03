# Fields

Complete guide to all field types, lookups, type annotations, PostgreSQL features, and every nitpick detail about fields in drf-restflow.

## Quick Navigation

### Getting Started
- [Field Basics](#field-basics) - How to declare and use fields
- [Type Annotations](#type-annotations) - Automatic field generation with Python types

### Field Types by Category

**Basic Fields**
- [StringField](#stringfield) - Text filtering with text lookups
- [IntegerField](#integerfield) - Integer filtering with comparison lookups
- [FloatField](#floatfield) - Floating-point number filtering
- [BooleanField](#booleanfield) - True/False filtering

**Numeric Fields**
- [DecimalField](#decimalfield) - Precise decimal number filtering

**Date & Time Fields**
- [DateField](#datefield) - Date filtering with year/month/day lookups
- [DateTimeField](#datetimefield) - DateTime filtering with timestamp lookups
- [TimeField](#timefield) - Time-only filtering

**Choice Fields**
- [ChoiceField](#choicefield) - Single choice from predefined options
- [MultipleChoiceField](#multiplechoicefield) - Multiple choices from options

**Collection Fields**
- [ListField](#listfield) - List/array filtering with `__in` lookup

**Ordering**
- [OrderField](#orderfield) - Sorting and ordering results

**Relational Fields**
- [RelatedField](#relatedfield) - Filters across relationship fields in django model



**PostgreSQL Fields**
- [Full-Text Search](#full-text-search) - SearchVector and SearchQuery
- [Array Fields](#array-fields) - PostgreSQL array operations
- [JSON Fields](#json-fields) - JSONField filtering
- [Range Fields](#range-fields) - Date/Integer ranges
- [Trigram Search](#trigram-similarity-search) - Fuzzy text matching

### Advanced Topics
- [Lookups](#lookups) - Lookup variations and categories
- [Negation](#negation) - `!` suffix for NOT operations
- [Custom Lookup Expressions](#custom-lookup-expressions) - Related field filtering
- [Validation](#validation) - Field validation and error handling
- [Field Parameters Reference](#field-parameters-reference) - Complete parameter lists
- [Important Caveats](#important-caveats) - Common pitfalls and warnings
- [Best Practices](#best-practices) - Recommended patterns

## Field Basics

### Field basic arguments

| Field | Description                                                                                     |
| ---- |-------------------------------------------------------------------------------------------------|
| `db_field` | corresponds to the model/queryset field                                                         |
| `filter_by` | custom filter by expression, can be a string, or callable that returns a Q Object or Dictionary |
| `lookups` | list of lookups eg: gte, lte, etc                                                               |
| `method` | custom filter method, can return queryset or Q object                                           |
| `negate` | Will perform negation, eg: queryset.exclude()                                                   |
| `required` | If field is required, and value not passed then will raise validation error                     |
| `allow_negate` | allow creating negation variant                                                                 |

Note: The priority of `filter_by` is higher than `db_field`, if both mentioned then `filter_by` will take precedence,
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



Fields define what query parameters your FilterSet accepts and how they filter the queryset.

### Three Ways to Declare Fields

```python
from restflow.filters import FilterSet, StringField

class ProductFilterSet(FilterSet):
    # 1. Type annotation (simplest)
    name: str

    # 2. Explicit field
    description = StringField(lookups=["icontains"])

    # 3. Model-based with extra_kwargs
    class Meta:
        model = Product
        fields = ['price']
        extra_kwargs = {
            'price': {'min_value': 0}
        }
```

### Field Generation

Each field can generate multiple filter parameters:

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(lookups=["comparison"])

# Generates:
# - price           (exact match)
# - price__gt       (greater than)
# - price__gte      (greater than or equal)
# - price__lt       (less than)
# - price__lte      (less than or equal)
# - price!          (not equal - negation)
# - price__gt!      (not greater than)
# - price__gte!     (not greater than or equal)
# - price__lt!      (not less than)
# - price__lte!     (not less than or equal)
```

## Type Annotations

Use Python type annotations for automatic field generation.

### Basic Types

```python
from typing import List, Literal
from datetime import datetime, date, time
from decimal import Decimal

class ProductFilterSet(FilterSet):
    # String → StringField
    name: str
    description: str

    # Integer → IntegerField
    quantity: int
    views: int

    # Float → FloatField
    rating: float
    score: float

    # Boolean → BooleanField
    in_stock: bool
    is_featured: bool

    # Decimal → DecimalField
    price: Decimal

    # Date/Time → DateField/DateTimeField/TimeField
    created_date: date
    created_at: datetime
    opening_time: time
```

### Choice Types with Literal

```python
from typing import Literal

class ProductFilterSet(FilterSet):
    # ChoiceField
    status: Literal["draft", "published", "archived"]

    # Also works with numbers
    priority: Literal[1, 2, 3, 4, 5]
```

### List Types

```python
from typing import List

class ProductFilterSet(FilterSet):
    # ListField with IntegerField child
    tags: List[int]

    # ListField with StringField child
    categories: List[str]

    # Can specify lookup expression
    tag_ids: List[int]  # Becomes tags__in by default
```

### Optional Types

```python
from typing import Optional

class ProductFilterSet(FilterSet):
    # Optional fields (not required)
    category: Optional[str]
    brand: Optional[int]
    
    # Or Modern style
    price : int | None
```

## All Field Types

### StringField

For text filtering.

```python
from restflow.filters import StringField


class ProductFilterSet(FilterSet):
    # Basic string field
    name = StringField()

    # With lookups
    title = StringField(lookups=["icontains", "istartswith"])

    # With validation
    sku = StringField(
        min_length=3,
        max_length=20,
        required=True
    )

    # Custom lookup expression
    category_name = StringField(filter_by="category__name__icontains")
```

**Available lookups:**
- `exact`: Exact match (default)
- `iexact`: Case-insensitive exact match
- `contains`: Contains substring
- `icontains`: Case-insensitive contains
- `startswith`: Starts with
- `istartswith`: Case-insensitive starts with
- `endswith`: Ends with
- `iendswith`: Case-insensitive ends with
- `regex`: Regular expression
- `iregex`: Case-insensitive regex

**Lookup category:**
- `text`: Expands to `icontains`, `contains`, `startswith`, `endswith`, `iexact`

**Parameters:**
- `min_length`: Minimum string length
- `max_length`: Maximum string length
- `required`: Make field required
- `validators`: List of custom validators
- `help_text`: Description
- `trim_whitespace`: Remove leading/trailing whitespace (default: True)
- `allow_blank`: Allow empty strings
- `lookups`: List of lookup variations
- `filter_by`: Custom Django ORM lookup expression
- `method`: Custom filter method

### IntegerField

For integer number filtering.

```python
from restflow.filters import IntegerField


class ProductFilterSet(FilterSet):
    # Basic integer field
    quantity: int

    # With lookups
    price = IntegerField(lookups=["comparison"])
    # Creates: price, price__gt, price__gte, price__lt, price__lte

    # With validation
    stock = IntegerField(
        min_value=0,
        max_value=10000,
        required=False
    )

    # Related field
    category_id = IntegerField(filter_by="category__id")
```

**Available lookups:**
- `exact`: Exact match (default)
- `gt`: Greater than
- `gte`: Greater than or equal
- `lt`: Less than
- `lte`: Less than or equal
- `in`: In list
- `range`: Between two values

**Lookup category:**
- `comparison`: Expands to `gt`, `gte`, `lt`, `lte`

**Parameters:**
- `min_value`: Minimum allowed value
- `max_value`: Maximum allowed value
- `required`: Make field required
- `validators`: List of custom validators
- `help_text`: Description
- `lookups`: List of lookup variations
- `filter_by`: Custom lookup expression
- `method`: Custom filter method

### FloatField

For floating-point number filtering.

```python
from restflow.filters import FloatField

class ProductFilterSet(FilterSet):
    # Basic float field
    rating: float

    # With lookups
    score = FloatField(lookups=["comparison"])

    # With validation
    discount = FloatField(
        min_value=0.0,
        max_value=100.0
    )

    # Average rating (annotated field)
    min_rating = FloatField(
        method="filter_min_rating",
        min_value=0.0,
        max_value=5.0
    )
```

**Available lookups:**
- `exact`: Exact match (default)
- `gt`, `gte`, `lt`, `lte`: Comparison
- `range`: Between two values

**Lookup category:**
- `comparison`: Expands to `gt`, `gte`, `lt`, `lte`

**Parameters:**
- `min_value`: Minimum value
- `max_value`: Maximum value
- `required`: Make field required
- `validators`: List of validators
- `help_text`: Description
- `lookups`: Lookup variations
- `filter_by`: Custom lookup
- `method`: Custom method

### BooleanField

For boolean filtering.

```python
from restflow.filters import BooleanField

class ProductFilterSet(FilterSet):
    # Basic boolean
    in_stock: bool

    # Explicit declaration
    is_featured = BooleanField()

    # With custom method
    available = BooleanField(method="filter_available")

    # Required boolean
    active = BooleanField(required=True)
```

**Accepts values:**
- True: `true`, `True`, `1`, `yes`
- False: `false`, `False`, `0`, `no`

**Available lookups:**
- `exact`: Exact match (default)
- `isnull`: Check if null

**Parameters:**
- `required`: Make field required
- `help_text`: Description
- `filter_by`: Custom lookup
- `method`: Custom method

### DecimalField

For precise decimal number filtering (e.g., money).

```python
from restflow.filters import DecimalField

class ProductFilterSet(FilterSet):
    # Basic decimal
    price = DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # With lookups and validation
    amount = DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        lookups=["comparison"]
    )
```

**Available lookups:**
- `exact`, `gt`, `gte`, `lt`, `lte`, `range`

**Lookup category:**
- `comparison`

**Parameters:**
- `max_digits`: Total digits (including decimal places)
- `decimal_places`: Number of decimal places
- `min_value`, `max_value`: Validation
- `required`, `validators`, `help_text`, `lookups`, `filter_by`, `method`

### DateField

For date filtering.

```python
from restflow.filters import DateField


class ProductFilterSet(FilterSet):
    # Basic date
    created_date: date

    # With lookups
    published_date = DateField(lookups=["comparison"])
    # Creates: published_date, published_date__gt, __gte, __lt, __lte

    # Date range
    start_date = DateField(filter_by="created_at__date__gte")
    end_date = DateField(filter_by="created_at__date__lte")
```

**Accepts formats:**
- ISO 8601: `2024-01-15`
- Other formats configured in DRF settings

**Available lookups:**
- `exact`, `gt`, `gte`, `lt`, `lte`
- `year`, `month`, `day`
- `week`, `week_day`
- `quarter`

**Lookup category:**
- `comparison`

**Parameters:**
- `input_formats`: List of accepted date formats
- `required`, `validators`, `help_text`, `lookups`, `filter_by`, `method`

### DateTimeField

For datetime filtering.

```python
from restflow.filters import DateTimeField

class ProductFilterSet(FilterSet):
    # Basic datetime
    created_at: datetime

    # With lookups
    published_at = DateTimeField(lookups=["comparison"])

    # With timezone support
    updated_at = DateTimeField()
```

**Accepts formats:**
- ISO 8601: `2024-01-15T10:30:00Z`
- Other formats configured in DRF settings

**Available lookups:**
- Same as DateField plus time-specific
- `hour`, `minute`, `second`

**Lookup category:**
- `comparison`

**Parameters:**
- `input_formats`: Accepted datetime formats
- `default_timezone`: Timezone for naive datetimes
- `required`, `validators`, `help_text`, `lookups`, `filter_by`, `method`

### TimeField

For time filtering.

```python
from restflow.filters import TimeField

class ProductFilterSet(FilterSet):
    # Basic time
    opening_time: time

    # With lookups
    closing_time = TimeField(lookups=["comparison"])
```

**Accepts formats:**
- `14:30:00`
- `14:30`

**Available lookups:**
- `exact`, `gt`, `gte`, `lt`, `lte`
- `hour`, `minute`, `second`

**Parameters:**
- `input_formats`, `required`, `validators`, `help_text`, `lookups`, `filter_by`, `method`

### ChoiceField

For fields with limited choices.

```python
from restflow.filters import ChoiceField

class ProductFilterSet(FilterSet):
    # Basic choices
    status = ChoiceField(
        choices=[
            ('draft', 'Draft'),
            ('published', 'Published'),
            ('archived', 'Archived')
        ]
    )

    # With Literal type annotation
    priority: Literal["low", "medium", "high", "urgent"]

    # With tuple choices
    size = ChoiceField(
        choices=[
            ('S', 'Small'),
            ('M', 'Medium'),
            ('L', 'Large'),
            ('XL', 'Extra Large')
        ]
    )
```

**Available lookups:**
- `exact` (default)
- `in`

**Parameters:**
- `choices`: List of (value, label) tuples or list of values
- `required`, `help_text`, `lookups`, `filter_by`, `method`

### MultipleChoiceField

For selecting multiple choices.

```python
from restflow.filters import MultipleChoiceField


class ProductFilterSet(FilterSet):
    # Multiple statuses
    statuses = MultipleChoiceField(
        choices=[
            ('draft', 'Draft'),
            ('published', 'Published')
        ],
        filter_by="status__in"
    )

    # Multiple categories
    categories = MultipleChoiceField(
        choices=[
            ('electronics', 'Electronics'),
            ('books', 'Books'),
            ('clothing', 'Clothing')
        ]
    )
```

**Accepts:**
- Comma-separated values: `?statuses=draft,published`

**Available lookups:**
- `in` (default)

**Parameters:**
- `choices`: List of (value, label) tuples
- `required`, `help_text`, `filter_by`, `method`

### ListField

For filtering by list of values.

```python
from restflow.filters import ListField, IntegerField, StringField


class ProductFilterSet(FilterSet):
    # List of integers
    tags: List[int]
    # Auto-generates: tags__in

    # Explicit declaration
    tag_ids = ListField(
        child=IntegerField(),
        filter_by="tags__id__in"
    )

    # List of strings
    categories = ListField(
        child=StringField(),
        filter_by="category__name__in"
    )

    # With validation
    product_ids = ListField(
        child=IntegerField(min_value=1),
        min_length=1,
        max_length=100
    )
```

**Accepts:**
- Comma-separated: `?tags=1,2,3`
- Multiple params: `?tags=1&tags=2&tags=3`

**Available lookups:**
- `in` (default)
- `overlap` (PostgreSQL arrays)
- `contains` (PostgreSQL arrays)
- `contained_by` (PostgreSQL arrays)

**Lookup category:**
- `pg_array`: PostgreSQL array lookups

**Parameters:**
- `child`: Field type for list items
- `min_length`: Minimum number of items
- `max_length`: Maximum number of items
- `required`, `help_text`, `lookups`, `filter_by`, `method`

### OrderField

For ordering/sorting.

```python
from restflow.filters import OrderField

class ProductFilterSet(FilterSet):
    ordering = OrderField(
        fields=[
            ('name', 'name'),
            ('price', 'price'),
            ('created_at', 'created_at')
        ]
    )

# Usage:
# ?ordering=name           # Ascending
# ?ordering=-price         # Descending
```

**Note:** Usually defined in `Meta.order_fields` instead. See [FilterSet guide](filterset.md#ordering).


### RelatedField

Filter across relationships:

```python
from restflow.filters import RelatedField

class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    
class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    sku = models.CharField(max_length=12)

# FilterSet with related fields
class ProductFilterSet(FilterSet):
    category = RelatedField(
        model=Category,
        fields=["name", "description"],
        exclude=["sku"]
    )

# Generates filters:
# - category__name
# - category__name__icontains (if lookups configured)
# - category__description
# - category__description__icontains

# Usage
?category__name=Electronics
?category__name__icontains=elec
```


## Lookups

Lookups allow creating variations of a field for different filter operations.

### Individual Lookups

```python
class ProductFilterSet(FilterSet):
    # Exact match only (default)
    name: str

    # Exact + contains
    title = StringField(lookups=["exact", "icontains"])
    # Creates: title, title__icontains

    # Comparison lookups
    price = IntegerField(lookups=["gt", "gte", "lt", "lte"])
    # Creates: price__gt, price__gte, price__lt, price__lte

    # Date lookups
    created_at = DateTimeField(lookups=["gte", "lte", "year", "month"])
    # Creates: created_at__gte, created_at__lte, created_at__year, created_at__month
```

### Lookup Categories

Use predefined groups instead of listing individual lookups:

```python
class ProductFilterSet(FilterSet):
    # "text" category
    name = StringField(lookups=["text"])
    # Expands to: icontains, contains, startswith, endswith, iexact

    # "comparison" category
    price = IntegerField(lookups=["comparison"])
    # Expands to: gt, gte, lt, lte

    # "pg_array" category (PostgreSQL)
    tags = ListField(child=StringField(), lookups=["pg_array"])
    # Expands to: contains, overlap, contained_by
```

**Available categories:**

- **`text`** (StringField): `icontains`, `contains`, `startswith`, `endswith`, `iexact`
- **`comparison`** (Numeric/Date fields): `gt`, `gte`, `lt`, `lte`
- **`pg_array`** (PostgreSQL arrays): `contains`, `overlap`, `contained_by`
- **`pg_json`** (PostgreSQL JSON): JSON-specific lookups

### All Django Lookup Expressions

```python
# Text lookups
exact, iexact
contains, icontains
startswith, istartswith
endswith, iendswith
regex, iregex

# Numeric/Date lookups
gt, gte, lt, lte
range
in

# Null checks
isnull

# Date component lookups
year, month, day
week, week_day, quarter
hour, minute, second

# PostgreSQL-specific
contains (array/range)
contained_by (array/range)
overlap (array/range)
has_key, has_keys, has_any_keys (JSON)

# Geographic (GeoDjango)
distance_lt, distance_lte, distance_gt, distance_gte
dwithin
```

### Negation with Lookups

Every lookup automatically gets a negation variant:

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(lookups=["gte", "lte"])

# Generates:
# price__gte      # Greater than or equal
# price__gte!     # NOT greater than or equal
# price__lte      # Less than or equal
# price__lte!     # NOT less than or equal
```

## Negation

All fields automatically support negation with `!` suffix.

### Basic Negation

```python
# ?status!=draft              # Status NOT draft
# ?in_stock!=true            # NOT in stock
# ?price!=1000               # Price NOT 1000
```

### Negation with Lookups

```python
# ?price__gte!=100           # NOT (price >= 100)  →  price < 100
# ?name__icontains!=test     # Name does NOT contain "test"
# ?created_at__year!=2024    # NOT created in 2024
```

### Negation Examples

```python
class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"])
    status: str

# All work:
# ?name!=laptop                  # Name not "laptop"
# ?name__icontains!=wireless     # Name doesn't contain "wireless"
# ?price!=99                     # Price not 99
# ?price__gte!=1000             # Price NOT >= 1000 (i.e., < 1000)
# ?status!=draft                # Status not draft
```

### Multiple Negations

```python
# Combine multiple negations
?status!=draft&status!=archived&in_stock!=false

# With AND operator: NOT draft AND NOT archived AND in_stock
```

## Custom Lookup Expressions

Override the default lookup expression to filter by related fields or custom paths.

### Basic Custom Expressions

```python
class ProductFilterSet(FilterSet):
    # Filter by related field
    category_name = StringField(filter_by="category__name")

    # Case-insensitive related field
    brand = StringField(filter_by="brand__name__iexact")

    # Multiple relationship levels
    department = StringField(filter_by="category__department__name")

# Usage:
# ?category_name=Electronics
# ?brand=apple
# ?department=Technology
```

### With Lookups

```python
class ProductFilterSet(FilterSet):
    # Use db_field to point out which field to use while performing filter/exclude
    category_name = StringField(
        db_field="category__name",
        lookups=["icontains", "istartswith"]
    )

# Generates:
# category_name__icontains       → category__name__icontains
# category_name__istartswith     → category__name__istartswith
```

### Nested Relationships

```python
# Models
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

# FilterSet
class ProductFilterSet(FilterSet):
    # Traverse multiple relationships
    region = StringField(filter_by="store__address__city__region__name")
    city = StringField(filter_by="store__address__city__name")


# FilterSet Or using db_field
class ProductFilterSet(FilterSet):
    # Traverse multiple relationships
    region = StringField(db_field="store__address__city__region__name")
    city = StringField(db_field="store__address__city__name")

    
# Or Can be done using related field

# Usage:
# ?region=California
# ?city=San Francisco
```

### Date Component Lookups

```python
class ProductFilterSet(FilterSet):
    # Filter by date components
    created_year = IntegerField(filter_by="created_at__year")
    created_month = IntegerField(filter_by="created_at__month")
    created_day = IntegerField(filter_by="created_at__day")

    # Or with lookups
    published_year = IntegerField(
        db_field="published_at__year",
        lookups=["gte", "lte"]
    )

# Usage:
# ?created_year=2024
# ?created_month=6
# ?published_year__gte=2020
```

Or using `db_field`

```python
class ProductFilterSet(FilterSet):
    # Filter by date components
    created_year = IntegerField(db_field="created_at__year")
    created_month = IntegerField(db_field="created_at__month")
    created_day = IntegerField(db_field="created_at__day")

    # Or with lookups
    published_year = IntegerField(
        db_field="published_at__year",
        lookups=["gte", "lte"]
    )

# Usage:
# ?created_year=2024
# ?created_month=6
# ?published_year__gte=2020
```

### Annotated Field Lookups

```python
from django.db.models import Count

def add_annotations(filterset, queryset):
    return queryset.annotate(
        review_count=Count('reviews'),
        avg_rating=Avg('reviews__rating')
    )

class ProductFilterSet(FilterSet):
    # Filter by annotated fields
    min_reviews = IntegerField(filter_by="review_count__gte")
    max_reviews = IntegerField(filter_by="review_count__lte")

    class Meta:
        preprocessors = [add_annotations]

# Usage:
# ?min_reviews=10
# ?max_reviews=100
```

## Validation

### Automatic Type Validation

```python
class ProductFilterSet(FilterSet):
    price: int        # Only accepts integers
    rating: float     # Only accepts floats
    in_stock: bool    # Only accepts true/false

# Invalid input returns 400:
# ?price=abc  →  {"price": ["A valid integer is required."]}
# ?rating=xyz →  {"rating": ["A valid number is required."]}
```

### Built-in Validators

```python
from restflow.filters import StringField, IntegerField

class ProductFilterSet(FilterSet):
    # Min/max value
    price = IntegerField(min_value=0, max_value=1000000)

    # Min/max length
    sku = StringField(min_length=3, max_length=20)

    # Required
    category = StringField(required=True)

# Validation errors:
# ?price=-10      →  {"price": ["Ensure this value is >= 0."]}
# ?sku=ab         →  {"sku": ["Ensure this has at least 3 characters."]}
# (no category)   →  {"category": ["This field is required."]}
```

### Custom Validators

```python
from rest_framework.exceptions import ValidationError

def validate_positive_even(value):
    if value <= 0:
        raise ValidationError("Must be positive")
    if value % 2 != 0:
        raise ValidationError("Must be even")

class ProductFilterSet(FilterSet):
    batch_size = IntegerField(validators=[validate_positive_even])

# ?batch_size=-2  →  {"batch_size": ["Must be positive"]}
# ?batch_size=3   →  {"batch_size": ["Must be even"]}
```

### Choice Validation

```python
class ProductFilterSet(FilterSet):
    status = ChoiceField(
        choices=[('draft', 'Draft'), ('published', 'Published')]
    )

# ?status=invalid  →  {"status": ["\"invalid\" is not a valid choice."]}
```

### List Validation

```python
class ProductFilterSet(FilterSet):
    tags = ListField(
        child=IntegerField(min_value=1),
        min_length=1,
        max_length=10
    )

# ?tags=           →  {"tags": ["This list may not be empty."]}
# ?tags=1,2,...,20 →  {"tags": ["Ensure this list has at most 10 elements."]}
# ?tags=0,1        →  {"tags": {"0": ["Ensure >= 1"]}}
```

## PostgreSQL Fields

### Full-Text Search

```python
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

class ProductFilterSet(FilterSet):
    search = StringField(method="filter_fulltext")

    def filter_fulltext(self, filterset, queryset, value):
        vector = SearchVector('name', weight='A') + \
                 SearchVector('description', weight='B')
        query = SearchQuery(value)

        return queryset.annotate(
            search=vector,
            rank=SearchRank(vector, query)
        ).filter(search=query).order_by('-rank')

# Usage:
# ?search=wireless headphones
```

**Weighted Search:**

```python
def filter_weighted_search(self, filterset, queryset, value):
    # Weight: A (highest) > B > C > D (lowest)
    vector = \
        SearchVector('title', weight='A') + \
        SearchVector('description', weight='B') + \
        SearchVector('tags', weight='C')

    query = SearchQuery(value)

    return queryset.annotate(
        rank=SearchRank(vector, query)
    ).filter(search=vector_for_filter).order_by('-rank')
```

**Search Configuration:**

```python
from django.contrib.postgres.search import SearchVector

# English search configuration
vector = SearchVector('description', config='english')

# Different languages
vector = SearchVector('description', config='spanish')
```

### Array Fields

```python
from django.contrib.postgres.fields import ArrayField

# Model
class Product(models.Model):
    tags = ArrayField(models.CharField(max_length=50))
    sizes = ArrayField(models.CharField(max_length=10))

# FilterSet
class ProductFilterSet(FilterSet):
    # Basic array filtering
    tags = ListField(
        child=StringField(),
        lookups=["pg_array"]
    )

# Available lookups:
# ?tags__contains=wireless        # Array contains value
# ?tags__overlap=a,b,c           # Array overlaps with list
# ?tags__contained_by=a,b,c,d    # Array is subset of list
```

**Array Operations:**

```python
# Contains (array must contain ALL values)
?tags__contains=wireless

# Overlaps (array has ANY of these values)
?tags__overlap=wireless,bluetooth

# Contained by (array is subset of these values)
?tags__contained_by=wireless,bluetooth,usb,hdmi
```

**All Tags (AND logic):**

```python
class ProductFilterSet(FilterSet):
    all_tags = ListField(child=StringField(), method="filter_all_tags")

    def filter_all_tags(self, filterset, queryset, value):
        """Product must have ALL specified tags"""
        q = Q()
        for tag in value:
            q &= Q(tags__contains=[tag])
        return q

# ?all_tags=wireless,bluetooth  # Must have BOTH
```

### JSON Fields

```python
from django.db import models

# Model
class Product(models.Model):
    metadata = models.JSONField()
    # Example: {"brand": "Apple", "specs": {"color": "red", "size": "large"}}

# FilterSet
class ProductFilterSet(FilterSet):
    # Filter by JSON keys
    brand = StringField(filter_by="metadata__brand")

    # Nested JSON keys
    color = StringField(filter_by="metadata__specs__color")
    size = StringField(filter_by="metadata__specs__size")

    # JSON contains
    has_spec = StringField(filter_by="metadata__has_key")

# Usage:
# ?brand=Apple
# ?color=red
# ?has_spec=warranty
```

**JSON Lookups:**

```python
# Has key
?metadata__has_key=warranty

# Has all keys
?metadata__has_keys=warranty,certificate

# Has any keys
?metadata__has_any_keys=warranty,certificate

# Contains (exact match)
?metadata__contains={"brand": "Apple"}
```

### Range Fields (PostgreSQL)

```python
from django.contrib.postgres.fields import IntegerRangeField, DateRangeField

# Model
class Product(models.Model):
    price_range = IntegerRangeField()
    available_dates = DateRangeField()

# FilterSet
class ProductFilterSet(FilterSet):
    # Contains value
    min_price = IntegerField(method="filter_price_contains")

    def filter_price_contains(self, filterset, queryset, value):
        return queryset.filter(price_range__contains=value)

# ?min_price=100  # Products with price range containing 100
```

### Trigram Similarity (PostgreSQL)

```python
from django.contrib.postgres.search import TrigramSimilarity

class ProductFilterSet(FilterSet):
    fuzzy_name = StringField(method="filter_fuzzy_name")

    def filter_fuzzy_name(self, filterset, queryset, value):
        return queryset.annotate(
            similarity=TrigramSimilarity('name', value)
        ).filter(similarity__gt=0.3).order_by('-similarity')

# ?fuzzy_name=lapto  # Finds "laptop" with typo
```

## Field Parameters Reference

### Common Parameters (All Fields)

```python
Field(
    # Lookup configuration
    db_field="",                # Corresponding database table field
    lookups=[...],              # List of lookup expressions to generate
    filter_by="...",          # Custom Django ORM lookup expression

    # Validation
    required=False,             # Make field required
    allow_null=False,           # Allow null values
    validators=[...],           # List of validator functions

    # Documentation
    help_text="...",            # Field description
    label="...",                # Field label

    # Custom filtering
    method="method_name",       # Custom filter method
)
```

### StringField Parameters

```python
StringField(
    min_length=None,            # Minimum string length
    max_length=None,            # Maximum string length
    trim_whitespace=True,       # Remove leading/trailing whitespace
    allow_blank=False,          # Allow empty strings

    # Common parameters
    db_field, lookups, filter_by, required, validators, help_text, method
)
```

### IntegerField / FloatField / DecimalField Parameters

```python
IntegerField(
    min_value=None,             # Minimum value
    max_value=None,             # Maximum value

    # Common parameters
    db_field, lookups, filter_by, required, validators, help_text, method
)

DecimalField(
    max_digits=None,            # Total digits (required)
    decimal_places=None,        # Decimal places (required)
    min_value=None,
    max_value=None,
    # ...
)
```

### DateField / DateTimeField / TimeField Parameters

```python
DateTimeField(
    input_formats=None,         # List of accepted input formats
    default_timezone=None,      # Timezone for naive datetimes
    format=None,                # Output format

    # Common parameters
    db_field, lookups, filter_by, required, validators, help_text, method
)
```

### ChoiceField / MultipleChoiceField Parameters

```python
ChoiceField(
    choices=[...],              # List of (value, label) tuples (required)
    allow_blank=False,          # Allow empty selection

    # Common parameters
    db_field, filter_by, required, help_text, method
)
```

### ListField Parameters

```python
ListField(
    child=Field(),              # Child field type (required)
    min_length=None,            # Minimum list length
    max_length=None,            # Maximum list length
    allow_empty=True,           # Allow empty list

    # Common parameters
    db_field, lookups, filter_by, required, help_text, method
)
```

## Important Caveats

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


### Custom Method with Fields

When using `method` parameter, return Q objects for operator compatibility:

```python
class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")

    class Meta:
        operator = "OR"

    # ✅ CORRECT - Returns Q object
    def filter_in_stock(self, filterset, queryset, value):
        if value:
            return Q(inventory__gt=0)
        return Q()

    # ❌ WRONG - Returns QuerySet (operator ignored)
    def filter_in_stock_wrong(self, filterset, queryset, value):
        if value:
            return queryset.filter(inventory__gt=0)
        return queryset
```

See [FilterSet guide](filterset.md#custom-method-caveat) for details.

### Type Annotation Limitations

Type annotations can't express all configurations:

```python
# ❌ Can't add validation with type annotation
price: int  # No min/max

# ✅ Use explicit declaration
price = IntegerField(min_value=0, max_value=1000000)
```

### List Field Caveats

**Comma-separated vs Multiple Parameters:**

```python
tags: List[int]

# Both work:
?tags=1,2,3           # Comma-separated
?tags=1&tags=2&tags=3 # Multiple parameters

# But behave differently with some backends
```

**Empty Lists:**

```python
# ?tags=  → Empty string, not empty list!
# Validation error: "A valid integer is required."

# Solution: Use allow_empty=True and handle in method
tags = ListField(child=IntegerField(), allow_empty=True, method="filter_tags")

def filter_tags(self, filterset, queryset, value):
    if not value:  # Empty list
        return Q()
    return Q(tags__id__in=value)
```

### Negation Edge Cases

**Double Negation:**

```python
# ⚠️ Watch out for logic
?price__gte!=1000  # NOT (price >= 1000) → price < 1000

# Equivalent to:
?price__lt=1000
```

**Null Checks:**

```python
# Check if null
?field__isnull=true

# Check if NOT null
?field__isnull!=true  # or ?field__isnull=false
```

## Best Practices

### Use Type Annotations for Simple Fields

```python
# Clean and readable
class ProductFilterSet(FilterSet):
    name: str
    price: int
    in_stock: bool
```

### Use Explicit Declarations for Complex Fields

```python
# Clear and configurable
class ProductFilterSet(FilterSet):
    name = StringField(
        lookups=["icontains", "istartswith"],
        min_length=2,
        help_text="Product name search"
    )
```

### Use Lookup Categories

```python
# Concise
price = IntegerField(lookups=["comparison"])

# Verbose
price = IntegerField(lookups=["gt", "gte", "lt", "lte"])
```

### Use extra_kwargs for Model Fields

```python
# Maintainable
class Meta:
    model = Product
    fields = ['name', 'price']
    extra_kwargs = {
        'name': {'lookups': ['icontains']},
        'price': {'min_value': 0}
    }
```

### Add Validation

```python
# Validate early
price = IntegerField(min_value=0, max_value=1000000)
sku = StringField(min_length=3, max_length=20, required=True)
```

### Document Fields

```python
class ProductFilterSet(FilterSet):
    search = StringField(
        method="filter_search",
        help_text="Search in name, description, and tags"
    )
    min_price = IntegerField(
        filter_by="price__gte",
        min_value=0,
        help_text="Minimum price filter"
    )
```

### Use PostgreSQL Features When Available

```python
# Use full-text search instead of icontains
search = StringField(method="filter_fulltext")

# Use array fields for tags
tags = ListField(child=StringField(), lookups=["pg_array"])
```

## Next Steps

- **[FilterSet](filterset.md)** - Complete FilterSet guide with custom methods, operators, preprocessors, postprocessors, and performance optimization
- **[Filtering Tutorial](../../tutorial/filtering.md)** - Step-by-step tutorial covering all filtering concepts