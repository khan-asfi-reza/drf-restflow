# Quick Start

This guide will help you get started with `drf-restflow`.

## About This Guide

`drf-restflow` is a declarative library for Django REST Framework with multiple planned features. This quickstart focuses on **Filtering** - the first available feature.

**What you'll learn:**
- Creating FilterSets with type annotations
- Integrating filters into DRF views
- Using query parameters for filtering and ordering

**Future releases will add:**
- Declarative Annotated Serializer
- FastAPI-Style Views
- Advanced Caching

Let's build your first FilterSet!

## Prerequisites

Make sure you have:

- Django and DRF installed and configured
- A Django model to filter
- Basic understanding of Django REST Framework


# Examples

Let's quickly view the features of drf-restflow


## FilterSet

Filterset helps you create a filter domain and helps filter queryset. 

### Define Your Model

Let's start with a simple Product model:

```python
# models.py
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100)
    in_stock = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
```

### Create a FilterSet

Now create a FilterSet to enable filtering:

```python
# filters.py
from restflow.filters import FilterSet, StringField, IntegerField, BooleanField

class ProductFilterSet(FilterSet):
    # Explicit field declarations with lookups
    name = StringField(lookups=["icontains"])
    price = IntegerField(lookups=["comparison"])  # gt, gte, lt, lte

    # Type annotation style
    category: str
    in_stock: bool

    class Meta:
        model = Product
        order_fields = [("price", "price"), ("name", "name"), ("created_at", "created_at")]
```

### Use in a View

####  Function-Based View

```python
# views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .filters import ProductFilterSet
from .models import Product

@api_view(['GET'])
def product_list(request):
    # Get base queryset
    queryset = Product.objects.all()

    # Apply filters
    filterset = ProductFilterSet(request=request)
    filtered_queryset = filterset.filter_queryset(queryset)

    # Return response
    return Response({
        'count': filtered_queryset.count(),
        'results': list(filtered_queryset.values())
    })
```

#### Class-Based View

```python
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from .filters import ProductFilterSet
from .models import Product

class ProductListView(APIView):
    def get(self, request):
        queryset = Product.objects.all()
        filterset = ProductFilterSet(request=request)
        filtered_queryset = filterset.filter_queryset(queryset)

        return Response({
            'count': filtered_queryset.count(),
            'results': list(filtered_queryset.values())
        })
```

#### With DRF Generic Views

```python
# views.py
from rest_framework import generics
from .filters import ProductFilterSet
from .models import Product
from .serializers import ProductSerializer

class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        filterset = ProductFilterSet(request=self.request)
        return filterset.filter_queryset(queryset)
```

### Add URL Pattern

```python
# urls.py
from django.urls import path
from .views import product_list

urlpatterns = [
    path('products/', product_list, name='product-list'),
]
```

### Test Your API

Now you can filter products using query parameters:

#### Basic Filtering

```bash
# Get all products
GET /api/products/

# Filter by exact category
GET /api/products?category=electronics

# Filter by name containing "laptop"
GET /api/products?name__icontains=laptop

# Filter in-stock products
GET /api/products?in_stock=true
```

#### Range Filtering

```bash
# Products with price greater than or equal to 100
GET /api/products?price__gte=100

# Products with price less than 500
GET /api/products?price__lt=500

# Products in price range 100-500
GET /api/products?price__gte=100&price__lte=500
```

#### Negation (Exclusion)

```bash
# Exclude electronics category
GET /api/products?category!=electronics

# Products NOT named "laptop"
GET /api/products?name!=laptop

# Out of stock products
GET /api/products?in_stock!=true
```

#### Ordering

```bash
# Order by price ascending
GET /api/products?order_by=price

# Order by price descending
GET /api/products?order_by=-price

# Order by multiple fields
GET /api/products?order_by=category,-price
```

#### Combined Filtering

```bash
# Complex filter: laptops under $1000, in stock, ordered by price
GET /api/products?name__icontains=laptop&price__lte=1000&in_stock=true&order_by=price
```

### Understanding the Generated Fields

The FilterSet automatically generates multiple filter fields:

| Declaration | Generated Fields |
|-------------|------------------|
| `name = StringField(lookups=["icontains"])` | `name`, `name__icontains`, `name!`, `name__icontains!` |
| `price = IntegerField(lookups=["comparison"])` | `price`, `price__gt`, `price__gte`, `price__lt`, `price__lte`, `price!`, `price__gt!`, ... |
| `category: str` | `category`, `category!` |
| `in_stock: bool` | `in_stock`, `in_stock!` |

## Validation

The FilterSet automatically validates query parameters:

```bash
# Invalid integer
GET /api/products?price__gte=invalid
# Response: {"price__gte": ["A valid integer is required."]}

# Invalid boolean
GET /api/products?in_stock=maybe
# Response: {"in_stock": ["Must be a valid boolean."]}
```

## Next Steps

Congratulations! You've created your first FilterSet with drf-restflow. Here's what to explore next:

**Dive Deeper into Filtering:**
- [Basic Concepts](concepts.md) - Understand the library's philosophy
- [Filtering Tutorial](../tutorial/filtering.md) - Complete walkthrough with real examples
- [FilterSet Guide](../guide/filtering/filterset.md) - Comprehensive FilterSet documentation
- [Fields Guide](../guide/filtering/fields.md) - All field types, lookups, and PostgreSQL features

**Stay Updated:**
- Watch the [GitHub repository](https://github.com/khan-asfi-reza/drf-restflow) for new releases
- Future features: Declarative Annotations, FastAPI-Style Views, Advanced Caching