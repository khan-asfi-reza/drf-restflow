# drf-restflow

A declarative library for Django REST Framework. Write type-safe REST APIs with Python annotations, automatic validation, and minimal boilerplate.

# Overview

`drf-restflow` works alongside DRF, not as a replacement. It leverages DRF's powerful serializer infrastructure and extends it with declarative patterns for common tasks.

Heavily inspired by [FastAPI](https://fastapi.tiangolo.com/) and [django-filter](https://django-filter.readthedocs.io), bringing modern Python features and intuitive API design to Django REST Framework.

Full documentation is live at:
[Restflow Documentation](https://khan-asfi-reza.github.io/drf-restflow)


**Current Release:** (Alpha)

**Available Features:** 
- [Filtering]()

# Table of Contents

- [Motivation](#motivation)
- [Installation](#installation)
- [Key Features](#key-features)
- [Quick Example](#quick-example)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

# Motivation

> **Hi, I’m Khan, the author of drf-restflow.**
>
> This library was born from the realities of building APIs in a fast-moving startup environment. 
> Most of my work involved large database tables, 
> constantly evolving product requirements, and the challenge of exposing clean, 
> reliable REST APIs. 
> While, also ensuring that new developers could onboard quickly and understand the 
> codebase and business logic as early as possible.
> 
> I started with **django-filter**, which is an excellent and very mature tool. But as our product grew 
> (and pivoted repeatedly), the FilterSets became harder to maintain. They were getting long, repetitive, 
> and full of boilerplate.
>
> Some might say this was a *skill issue*, and honestly, I agree.
>
> But the truth is, **I’m a lazy developer.**
>
> I like writing less code. I like being fast. I like tools that let me declare what I want instead of wiring everything by hand. Over time, 
> I built small internal utilities to reduce repetition and make filtering easier. Those tools worked well for my case,
>, So I decided to compile all those internal utilities into a proper library, so I can use it for other projects as well.
> 
> Many of the internal toolsets created were built from scratch, which brought some inconsistency, instead of reinventing the wheel,
> I later decided to use what is already available and battle tested and borrowed ideas from different libraries, for example 
> FastAPI, django-filter, and django-ninja. 
> That's how I started drf-restflow, a library that doesn't replace Django Rest Framework but uses its powerful features.
> One sidenote, there might be other libraries that do exactly what drf-restflow promises to do, or maybe do more than that, I might be unaware, 
> So, Feel free to contribute or provide any insights, and constructive criticism, thank you. 
> 


# Installation

```bash
pip install drf-restflow
```

or using uv

```bash
uv add drf-restflow
```

# Requirements

- Python 3.10+
- Django 3.2+
- Django REST Framework 3.14+
- PostgreSQL (optional, for PostgreSQL-specific features)


# Key Features

## Filtering

The current release focuses on declarative filtering with these capabilities:

### Declarative Field Definitions
Define filters using type annotations, explicit field declarations, or automatic model generation:

```python
from restflow.filters import FilterSet

class ProductFilterSet(FilterSet):
    name: str                                    # Type annotation
    price = IntegerField(lookups=["comparison"]) # Explicit field

    class Meta:
        model = Product                          # Model-based generation
```

### Automatic Lookup Generation
Generate multiple filter variants from a single field definition:

```python
class ProductFilterSet(FilterSet):
    price = IntegerField(lookups=["comparison"])

# Automatically generates:
# - price (exact match)
# - price__gt, price__gte, price__lt, price__lte (comparisons)
# - price!, price__gt!, price__gte!, ... (negations)
```


### Lookup generation using `db_field`
Generate multiple filter variants from a single field definition:

```python
class ProductFilterSet(FilterSet):
    product_price = IntegerField(db_field="price", lookups=["comparison"])

# Automatically generates:
# - product_price (exact match)
# - product_price__gt, product_price__gte, product_price__lt, product_price__lte (comparisons)
# - product_price!, product_price__gt!, product_price__gte!, ... (negations)
# But these filters will internally run orm filter by the following method `queryset.filter_by(price=<value>)`
```



### Type-Safe Validation
Built on DRF's validation system with automatic type conversion and detailed error messages:

```python
# GET /api/products?price__gte=invalid
# Returns: {"price__gte": ["A valid integer is required."]}

# GET /api/products?price=-10
# Returns: {"price": ["Ensure this value is greater than or equal to 0."]}
```

### Universal Negation Support
Exclude values using the `!` suffix on any filter:

```python
# Exclude categories
GET /api/products?category!=electronics&category!=books

# Exclude price range
GET /api/products?price__gte!=1000  # NOT >= 1000 (i.e., < 1000)

# Exclude keywords
GET /api/products?name__icontains!=refurbished
```

### Custom Filter Methods
Implement complex filtering logic with custom methods using Q objects:

```python
from django.db.models import Q

class ProductFilterSet(FilterSet):
    in_stock = BooleanField(method="filter_in_stock")
    search = StringField(method="filter_search")

    def filter_in_stock(self, filterset, queryset, value):
        if value:
            return Q(inventory__gt=0)
        return Q(inventory=0)

    def filter_search(self, filterset, queryset, value):
        return Q(name__icontains=value) | Q(description__icontains=value)
```

### PostgreSQL Features
First-class support for PostgreSQL-specific functionality:

```python
from django.contrib.postgres.search import SearchVector, SearchQuery

class ProductFilterSet(FilterSet):
    # Array fields
    tags = ListField(child=StringField(), lookups=["pg_array"])
    # Generates: tags__contains, tags__overlap, tags__contained_by

    # Full-text search
    search = StringField(method="filter_fulltext")

    def filter_fulltext(self, filterset, queryset, value):
        vector = SearchVector('name', 'description')
        query = SearchQuery(value)
        return queryset.filter(search_vector=query)
```

### Operators & Processors
Control filter combination logic and queryset transformations:

```python
class ProductFilterSet(FilterSet):
    name: str
    category: str

    class Meta:
        operator = "OR"  # Combine filters with OR instead of AND

        preprocessors = [      # Run before filtering
            exclude_deleted,
            apply_permissions,
            optimize_queries,
        ]

        postprocessors = [     # Run after filtering
            apply_default_ordering,
            ensure_distinct,
        ]
```

### Quick Example

```python
from django.db import models
from restflow.filters import FilterSet, StringField, IntegerField
from rest_framework.decorators import api_view
from rest_framework.response import Response

# Model
class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField()
    category = models.CharField(max_length=50)
    in_stock = models.BooleanField(default=True)

# FilterSet
class ProductFilterSet(FilterSet):
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"])
    category: str

    class Meta:
        model = Product
        order_fields = [("price", "price"), ("name", "name")]

# View
@api_view(['GET'])
def product_list(request):
    queryset = Product.objects.all()
    filterset = ProductFilterSet(request=request)
    filtered_qs = filterset.filter_queryset(queryset)
    return Response({
        'count': filtered_qs.count(),
        'results': list(filtered_qs.values())
    })
```

**API Usage:**
```bash
# Filter by name containing "laptop"
GET /api/products?name__icontains=laptop

# Filter by price range
GET /api/products?price__gte=100&price__lte=500

# Exclude categories
GET /api/products?category!=electronics

# Order by price descending
GET /api/products?order_by=-price

# Combine filters
GET /api/products?name__icontains=laptop&price__lte=1000&category!=refurbished&order_by=price
```

# Roadmap

## Current Release: Alpha
**Filtering** : Declarative query parameter filtering with type annotations

## Future
- **Serializer enhancements**: Declarative serializers with type annotations
- **API / View**: FastAPI style api / view declaration
- **Async Support**: Async filters and views

---

**Alpha Notice:** This is the first alpha release. The filtering API is mostly stable, but breaking changes may occur as we add features and gather community feedback.

# Contributing

Contributions are welcome! Check out the [Contributing Guide](CONTRIBUTING.md) for guidelines.

# License

BSD 3-Clause License [LICENSE](LICENSE)