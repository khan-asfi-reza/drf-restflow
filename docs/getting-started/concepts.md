# Basic Concepts

This guide covers the core concepts and design philosophy of `drf-restflow`.

## What is drf-restflow?

`drf-restflow` is a declarative library for Django REST Framework that brings modern Python features and FastAPI-like ergonomics to Django. The library is being built in phases, with each release adding new declarative capabilities.

**Current Features:**
- **Filtering** - Declarative query parameter filtering with type annotations

## Core Philosophy

drf-restflow follows these principles:

1. **Declarative over Imperative**: Define what you want, not how to do it
2. **Type Safety**: Leverage Python type annotations for validation and IDE support
3. **Less Boilerplate**: Reduce repetitive code while maintaining flexibility
4. **DRF Integration**: Work alongside DRF, not replace it
5. **Modern Python**: Take advantage of Python 3.10+ features

## Filtering

### FilterSet

A `FilterSet` is the main abstraction in drf-restflow. It's a declarative class that:

1. Defines filterable fields
2. Validates query parameters
3. Applies filters to Django querysets

```python
from restflow.filters import FilterSet

class ProductFilterSet(FilterSet):
    name: str
    price: int

    class Meta:
        model = Product
```

### How It Works

When you use a FilterSet:

1. **Initialization**: FilterSet receives query parameters from the request
2. **Validation**: Parameters are validated using DRF field validators
3. **Filtering**: Validated data is converted into Django ORM filters
4. **Execution**: Filters are applied to the queryset

```python
# Step 1: Initialize
filterset = ProductFilterSet(request=request)

# Step 2 & 3: Validate and get filtered queryset
filtered_qs = filterset.filter_queryset(Product.objects.all())
```

## Fields

Fields define what can be filtered and how. Each field corresponds to a query parameter.

### Field Declaration Styles

drf-restflow supports multiple ways to declare fields:

#### 1. Type Annotations

```python
class ProductFilterSet(FilterSet):
    name: str
    price: int
    in_stock: bool
```

#### 2. Explicit Field Objects

```python
from restflow.filters import StringField, IntegerField

class ProductFilterSet(FilterSet):
    name = StringField()
    price = IntegerField()
```

#### 3. Model-Based Generation

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = "__all__"  # or ['name', 'price', 'category']
```

#### 4. Mixed Style

```python
from restflow.filters import Field

class ProductFilterSet(FilterSet):
    name: str = Field(lookups=["icontains"])
    price: int = Field(lookups=["comparison"])
    category = StringField()
```

### Field Priority

When the same field is declared in multiple ways, this priority applies:

**Explicit declarations > Type annotations > Model fields**

```python
class ProductFilterSet(FilterSet):
    # This takes precedence
    name = StringField(lookups=["icontains"])

    # This would be ignored
    name: str

    class Meta:
        model = Product
        fields = ['name']  # This is ignored since name is explicitly declared
        extra_kwargs = {
            "name": {
                "allow_negate": False # This is also ignored since name is explicitly declared
            }
        }
```

## Lookup Expressions

Lookups define *how* to filter. They correspond to Django ORM lookup expressions.

### Basic Lookups

```python
price = IntegerField()
# Query: ?price=100
# ORM: Product.objects.filter(price=100)
```

### Field Lookups

```python
price = IntegerField(lookups=["gte", "lte"])
# Query: ?price__gte=100
# ORM: Product.objects.filter(price__gte=100)
```

### Lookup Categories

Instead of listing individual lookups, use categories:

```python
price = IntegerField(lookups=["comparison"])
# Expands to: ["gt", "gte", "lt", "lte"]

name = StringField(lookups=["text"])
# Expands to: ["icontains", "contains", "startswith", "endswith", "iexact"]
```

**Available Categories:**

- `basic`: `["exact", "in", "isnull"]`
- `text`: `["icontains", "contains", "startswith", "endswith", "iexact"]`
- `comparison`: `["gt", "gte", "lt", "lte"]`
- `date`: `["date", "year", "month", "day", "week", "week_day", "quarter"]`
- `time`: `["time", "hour", "minute", "second"]`
- `postgres`: `["search", "trigram_similar", "unaccent"]`
- `pg_array`: `["contains", "overlaps", "contained_by"]`

## Field Variants

Each field declaration can generate multiple filter fields:

### Base Field

```python
name = StringField()
```

Generates: `name` filter (exact match)

### With Lookups

```python
price = IntegerField(lookups=["gte", "lte"])
```

Generates:
- `price` (exact match)
- `price__gte` (greater than or equal)
- `price__lte` (less than or equal)

### With Negation

```python
category = StringField(allow_negate=True)  # Default is True
```

Generates:
- `category` (include)
- `category!` (exclude)

### Complete Example

```python
price = IntegerField(lookups=["gte", "lte"])
```

Generates all these fields:
- `price`
- `price__gte`
- `price__lte`
- `price!`
- `price__gte!`
- `price__lte!`

## Negation

Negation allows excluding values using the `!` suffix:

```python
# Include only electronics
?category=electronics

# Exclude electronics
?category!=electronics

# Exclude multiple categories
?category!=electronics&category!=books
```

### Disabling Negation

```python
# For individual fields
category = StringField(allow_negate=False)

# For all annotated and model-generated fields
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = "__all__"
        allow_negate = False
```

## Ordering

FilterSets can generate OrderField for sorting results:

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        order_fields = [("price", "price"), ("name", "name")]
```

Usage:

```bash
?order_by=price      # Ascending
?order_by=-price     # Descending
?order_by=name,-price  # Multiple fields
```

## Validation

FilterSets use DRF's validation system:

```python
# Valid request
?price=100  # ✓ Validated as integer

# Invalid request
?price=abc  # ✗ Returns: {"price": ["A valid integer is required."]}
```

### Custom Validation

Add custom validation using DRF field validators:

```python
from rest_framework.validators import MinValueValidator

class ProductFilterSet(FilterSet):
    price = IntegerField(validators=[MinValueValidator(0)])
```

## InlineFilterSet

Create FilterSets dynamically without defining a class:

```python
from restflow.filters import InlineFilterSet

# Simple model-based FilterSet
ProductFilterSet = InlineFilterSet(
    name="ProductFilterSet",
    model=Product
)

# With specific fields
ProductFilterSet = InlineFilterSet(
    model=Product,
    fields=["name", "price", "category"]
)

# With field definitions
ProductFilterSet = InlineFilterSet(
    fields={
        "name": StringField(lookups=["icontains"]),
        "price": IntegerField(lookups=["comparison"]),
        "category": str
    }
)

# With ordering
ProductFilterSet = InlineFilterSet(
    model=Product,
    order_fields=[("price", "price"), ("name", "name")]
)

# Use it like a regular FilterSet
filterset = ProductFilterSet(request=request)
```

**Use cases:**
- Quick prototyping
- Dynamic FilterSet generation
- Programmatic FilterSet creation
- Testing

## Meta Options

The `Meta` class configures FilterSet behavior:

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product                    # Model to filter
        fields = "__all__"                 # Fields to include
        exclude = ['internal_id']          # Fields to exclude
        order_fields = [...]               # Enable ordering
        order_param = "order_by"           # Order query parameter name
        operator = "AND"                   # Filter combination logic
        extra_kwargs = {...}               # Field configuration
        allow_negate = True                # Enable negation
        related_fields = [...]             # Enable related field filtering
```

### extra_kwargs

Configure field behavior without explicit declarations:

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = ["name", "price", "category", "created_at"]
        extra_kwargs = {
            "name": {
                "lookups": ["icontains"],
                "required": True
            },
            "price": {
                "lookups": ["comparison"],
                "min_value": 0,
                "max_value": 1000000
            },
            "category": {
                "lookups": ["exact", "in"],
                "allow_negate": False
            },
            "created_at": {
                "lookups": ["date"],
                "input_formats": ["%Y-%m-%d"]
            }
        }
```

**Common use cases:**

```python
# Add lookups to model fields
extra_kwargs = {
    "name": {"lookups": ["icontains", "startswith"]},
    "price": {"lookups": ["comparison"]}
}

# Add validation
extra_kwargs = {
    "price": {
        "min_value": 0,
        "validators": [custom_price_validator]
    }
}

# Configure field behavior
extra_kwargs = {
    "status": {
        "required": True,
        "allow_negate": False
    }
}

# Override default settings
extra_kwargs = {
    "description": {
        "max_length": 500,
        "trim_whitespace": True
    }
}
```

### Operators

Control how multiple filters are combined:

```python
class ProductFilterSet(FilterSet):
    class Meta:
        operator = "AND"  # All filters must match (default)

# AND - All conditions must be true
?name=laptop&price__gte=100&in_stock=true
# SQL: WHERE name='laptop' AND price>=100 AND in_stock=true
```

**OR Operator:**
```python
class ProductFilterSet(FilterSet):
    class Meta:
        operator = "OR"  # Any condition can match

# Any condition matches
?name=laptop&category=electronics
# SQL: WHERE name='laptop' OR category='electronics'
```

**XOR Operator:**
```python
class ProductFilterSet(FilterSet):
    class Meta:
        operator = "XOR"  # Exactly one condition must match

# Exactly one condition must be true
?is_featured=true&on_sale=true
# SQL: WHERE (is_featured=true) XOR (on_sale=true)
```

**Use cases:**
- `AND`: Standard filtering (most common)
- `OR`: Search across multiple fields
- `XOR`: Mutually exclusive conditions

### OrderField

Enable result ordering via query parameters:

```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        order_fields = [
            ("price", "price"),
            ("name", "name"),
            ("date", "created_at")
        ]
        order_field_labels = [
            ("price", "Price"),
            ("name", "Product Name"),
            ("date", "Date Created")
        ]
        order_param = "order_by"  # Custom parameter name (default: "order_by")
        default_order_fields = ["created_at"]  # Default ordering

# Usage
?order_by=price        # Ascending by price
?order_by=-price       # Descending by price
?order_by=name,-price  # Name asc, then price desc
```

**Explicit OrderField:**
```python
from restflow.filters import OrderField

class ProductFilterSet(FilterSet):
    sort = OrderField(
        fields=[("price", "price"), ("name", "name")],
        labels=[("price", "Price"), ("name", "Name")],
        override_order_dir="asc"  # or "desc"
    )

# Custom parameter name
?sort=price
?sort=-name
```

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

# FilterSet with related fields
class ProductFilterSet(FilterSet):
    category = RelatedField(
        model=Category,
        fields=["name", "description"]
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

**Via Meta:**
```python
class ProductFilterSet(FilterSet):
    class Meta:
        model = Product
        fields = ["name", "price"]
        related_fields = ["category"]  # Auto-expand category fields
        extra_kwargs = {
            "category": {
                "exclude": ["internal_id"],  # Exclude from related fields
                "name": {"lookups": ["icontains"]}
            }
        }
```

## Request Integration

### From Request Object

```python
filterset = ProductFilterSet(request=request)
```

Automatically extracts `request.query_params` or `request.GET`.

### From Dictionary

```python
data = {'name': 'laptop', 'price__gte': 100}
filterset = ProductFilterSet(data=data)
```

## Queryset Filtering

Apply filters to any Django queryset:

```python
# Basic usage
queryset = Product.objects.all()
filterset = ProductFilterSet(request=request)
filtered_qs = filterset.filter_queryset(queryset)

# With prefetch/select_related
queryset = Product.objects.select_related('category').prefetch_related('tags')
filterset = ProductFilterSet(request=request)
filtered_qs = filterset.filter_queryset(queryset)  # Preserves optimizations

# With annotations
queryset = Product.objects.annotate(total_reviews=Count('reviews'))
filterset = ProductFilterSet(request=request)
filtered_qs = filterset.filter_queryset(queryset)
```

## Type Safety

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

## Next Steps

- [Quick Start](quickstart.md) - Build your first FilterSet
- [Filtering Tutorial](../tutorial/filtering.md) - Complete filtering walkthrough
- [FilterSet Guide](../guide/filtering/filterset.md) - Comprehensive FilterSet documentation
- [Fields Guide](../guide/filtering/fields.md) - All field types and options