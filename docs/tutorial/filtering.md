# Tutorial: Filtering

A comprehensive step-by-step tutorial covering everything about filtering with drf-restflow, from basic concepts to production-ready implementations.

## Topics

- Creating FilterSets with type annotations and explicit fields
- Using lookups and operators
- Writing custom filter methods with Q objects
- Filtering across relationships
- Validation and ordering
- Performance optimization for production

## Prerequisites

- Django project set up


## Setup

Create a new Django app for this tutorial:

```bash
python manage.py startapp articles
```

Add to `INSTALLED_APPS`:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'articles',
]
```

## Part 1: Basic Filtering

### Create Models

```python
# articles/models.py
from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

class Article(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    views = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='articles')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='articles')
    tags = models.ManyToManyField(Tag, related_name='articles', blank=True)

    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
```

Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Your First FilterSet

Create a simple FilterSet with type annotations:

```python
# articles/filters.py
from restflow.filters import FilterSet

class ArticleFilterSet(FilterSet):
    # Type annotations create exact match filters
    title: str
    status: str

# This creates filters for:
# - title (exact match)
# - status (exact match)
```

### Create Serializer and View

```python
# articles/serializers.py
from rest_framework import serializers
from .models import Article

class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['id', 'title', 'content', 'status', 'views', 'created_at']
```

```python
# articles/views.py
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from .models import Article
from .serializers import ArticleSerializer
from .filters import ArticleFilterSet

class ArticleListView(generics.ListAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        filterset = ArticleFilterSet(request=self.request)
        return filterset.filter_queryset(queryset)
```

### Configure URLs

```python
# articles/urls.py
from django.urls import path
from .views import ArticleListView

urlpatterns = [
    path('articles/', ArticleListView.as_view(), name='article-list'),
]
```

```python
# project/urls.py
from django.urls import path, include

urlpatterns = [
    # ...
    path('api/', include('articles.urls')),
]
```

### Test It

```bash
python manage.py runserver

# Create some test data in shell:
python manage.py shell
>>> from articles.models import Article
>>> from django.contrib.auth.models import User
>>> user = User.objects.create_user('testuser')
>>> Article.objects.create(title="First Article", content="Content", status="published", author=user)
>>> Article.objects.create(title="Second Article", content="Content", status="draft", author=user)
```

Test the API:

```bash
curl http://localhost:8000/api/articles/
curl http://localhost:8000/api/articles/?status=published
curl http://localhost:8000/api/articles/?title=First%20Article
```

## Lookups and Operators

### Adding Lookups

Lookups allow flexible filtering beyond exact matches:

```python
# articles/filters.py
from restflow.filters import FilterSet, StringField, IntegerField, DateTimeField

class ArticleFilterSet(FilterSet):
    # Text lookups
    title = StringField(lookups=["icontains", "istartswith"])
    # Creates: title__icontains, title__istartswith

    # Numeric comparisons
    views = IntegerField(lookups=["comparison"])
    # Creates: views__gt, views__gte, views__lt, views__lte

    # Date comparisons
    published_at = DateTimeField(lookups=["comparison"])

    # Simple fields
    status: str
```

Test it:

```bash
# Search titles containing "article"
curl "http://localhost:8000/api/articles/?title__icontains=article"

# Articles with more than 100 views
curl "http://localhost:8000/api/articles/?views__gt=100"

# Articles published after a date
curl "http://localhost:8000/api/articles/?published_at__gte=2024-01-01T00:00:00Z"
```

### Lookup Categories

Instead of listing individual lookups, use categories:

```python
class ArticleFilterSet(FilterSet):
    # "text" category: icontains, contains, startswith, endswith, iexact
    title = StringField(lookups=["text"])

    # "comparison" category: gt, gte, lt, lte
    views = IntegerField(lookups=["comparison"])
    published_at = DateTimeField(lookups=["comparison"])

    status: str
```

### Automatic Negation

All filters automatically support negation with `!`:

```python
# No configuration needed!

# ?status!=draft              # NOT draft
# ?views__gte!=1000          # NOT >= 1000
# ?title__icontains!=test    # NOT containing "test"
```

### Operators

Operators control how multiple filters are combined.

**AND (default)** - All filters must match:

```python
class ArticleFilterSet(FilterSet):
    title = StringField(lookups=["icontains"])
    status: str

    class Meta:
        operator = "AND"  # Default, can be omitted

# ?title__icontains=django&status=published
# SQL: WHERE title ILIKE '%django%' AND status = 'published'
```

**OR** - Any filter can match:

```python
class ArticleFilterSet(FilterSet):
    title = StringField(lookups=["icontains"])
    content = StringField(lookups=["icontains"])

    class Meta:
        operator = "OR"

# ?title__icontains=django&content__icontains=python
# SQL: WHERE title ILIKE '%django%' OR content ILIKE '%python%'
```

## Custom Methods

Custom methods handle complex filtering logic that can't be expressed with simple lookups.

### Your First Custom Method

```python
from django.db.models import Q
from restflow.filters import FilterSet, StringField, IntegerField, BooleanField

class ArticleFilterSet(FilterSet):
    # Custom filter with method
    search = StringField(method="filter_search")

    # Regular filters
    status: str
    views = IntegerField(lookups=["comparison"])

    def filter_search(self, filterset, queryset, value):
        """Search across title and content"""
        return Q(
            title__icontains=value
        ) | Q(
            content__icontains=value
        )

# ?search=django  # Searches in both title and content
```

### Why Q Objects?

**✅ Always return Q objects from custom methods:**

```python
def filter_search(self, filterset, queryset, value):
    # ✅ Returns Q object - works with all operators
    return Q(title__icontains=value) | Q(content__icontains=value)
```

**❌ Avoid returning QuerySet ( unless you really need it ):**

```python
def filter_search(self, filterset, queryset, value):
    # ❌ Returns QuerySet - operator ignored!
    return queryset.filter(
        Q(title__icontains=value) | Q(content__icontains=value)
    )
```

**Why Q objects?**
- Works correctly with all operators (AND, OR, XOR)
- Properly combined with other filters
- More predictable behavior

### The QuerySet Return Caveat

⚠️ **CRITICAL:** When returning QuerySet instead of Q objects, the FilterSet operator is **NOT applied**:

```python
class ArticleFilterSet(FilterSet):
    popular = BooleanField(method="filter_popular")
    status: str

    class Meta:
        operator = "OR"  # ⚠️ Won't apply to QuerySet returns!

    def filter_popular(self, filterset, queryset, value):
        # ❌ Returns QuerySet - bypasses operator
        if value:
            return queryset.filter(views__gte=1000)
        return queryset

# ?popular=true&status=published
# Expected (OR): popular OR published
# Actual: popular AND published (operator ignored!)
```

**✅ Solution:**

```python
def filter_popular(self, filterset, queryset, value):
    if value:
        return Q(views__gte=1000)
    return Q()  # Empty Q matches everything
```

### Conditional Logic

```python
class ArticleFilterSet(FilterSet):
    search = StringField(method="filter_search")
    quality = StringField(method="filter_quality")

    def filter_search(self, filterset, queryset, value):
        return Q(title__icontains=value) | Q(content__icontains=value)

    def filter_quality(self, filterset, queryset, value):
        """Filter by quality level"""
        if value == "high":
            return Q(status='published', is_featured=True, views__gte=1000)
        elif value == "medium":
            return Q(status='published', views__gte=100)
        elif value == "low":
            return Q(views__lt=100)
        return Q()

# ?quality=high
```

### Accessing Request Data

```python
class ArticleFilterSet(FilterSet):
    my_articles = BooleanField(method="filter_my_articles")

    def filter_my_articles(self, filterset, queryset, value):
        """Filter articles by current user"""
        if value and filterset.request and filterset.request.user.is_authenticated:
            return Q(author=filterset.request.user)
        return Q()

# ?my_articles=true  (requires authentication)
```

## Related Fields

### ForeignKey Filtering

```python
class ArticleFilterSet(FilterSet):
    # Filter by category ID
    category = IntegerField(lookup_expr="category__id")

    # Filter by category slug
    category_slug = StringField(lookup_expr="category__slug")

    # Filter by author ID
    author = IntegerField(lookup_expr="author__id")

    # Filter by author username
    author_username = StringField(lookup_expr="author__username__icontains")

# ?category=1
# ?category_slug=python
# ?author_username=john
```

### ManyToMany Filtering

```python
from typing import List

class ArticleFilterSet(FilterSet):
    # Filter by tag IDs
    tags: List[int]
    # Auto-creates: tags__in

    # Or explicit
    tag_ids = ListField(
        child=IntegerField(),
        lookup_expr="tags__id__in"
    )

# ?tags=1,2,3
# ?tag_ids=1,2,3
```

### Filtering by Related Object Existence

```python
class ArticleFilterSet(FilterSet):
    has_category = BooleanField(method="filter_has_category")

    def filter_has_category(self, filterset, queryset, value):
        if value:
            return Q(category__isnull=False)
        return Q(category__isnull=True)

# ?has_category=true
```

### Counting Related Objects

Add a Comment model first:

```python
# articles/models.py
class Comment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
```

Then filter by count:

```python
from django.db.models import Count

def add_annotations(filterset, queryset):
    return queryset.annotate(
        comment_count=Count('comments')
    )

class ArticleFilterSet(FilterSet):
    min_comments = IntegerField(method="filter_min_comments")
    has_comments = BooleanField(method="filter_has_comments")

    class Meta:
        preprocessors = [add_annotations]

    def filter_min_comments(self, filterset, queryset, value):
        return Q(comment_count__gte=value)

    def filter_has_comments(self, filterset, queryset, value):
        if value:
            return Q(comment_count__gt=0)
        return Q(comment_count=0)

# ?min_comments=5
# ?has_comments=true
```

### Performance: select_related and prefetch_related

```python
def optimize_queries(filterset, queryset):
    """Optimize database queries"""
    return queryset.select_related(
        'author',
        'category'
    ).prefetch_related(
        'tags',
        'comments'
    )

class ArticleFilterSet(FilterSet):
    class Meta:
        preprocessors = [optimize_queries, add_annotations]

# Without optimization: 1 + N queries
# With optimization: 2-3 queries total
```

### Ensure Distinct for M2M

```python
def smart_distinct(filterset, queryset):
    """Remove duplicates from M2M filtering"""
    if 'tags' in filterset.data:
        return queryset.distinct()
    return queryset

class ArticleFilterSet(FilterSet):
    tags: List[int]

    class Meta:
        postprocessors = [smart_distinct]
```

## Validation and Ordering

### Field-Level Validation

```python
from rest_framework.validators import MinValueValidator

class ArticleFilterSet(FilterSet):
    title = StringField(
        min_length=2,
        max_length=200,
        lookups=["icontains"]
    )

    views = IntegerField(
        min_value=0,
        max_value=1_000_000,
        lookups=["comparison"],
        validators=[MinValueValidator(0)]
    )

# ?views=-10  →  {"views": ["Ensure this value >= 0."]}
# ?title=a    →  {"title": ["Ensure this has at least 2 characters."]}
```

### FilterSet-Level Validation

```python
from rest_framework.exceptions import ValidationError

class ArticleFilterSet(FilterSet):
    min_views = IntegerField(lookup_expr="views__gte")
    max_views = IntegerField(lookup_expr="views__lte")

    def validate(self, data):
        if 'min_views' in data and 'max_views' in data:
            if data['min_views'] > data['max_views']:
                raise ValidationError({
                    'max_views': 'Must be greater than min_views'
                })
        return data

# ?min_views=1000&max_views=500  →  400 Bad Request
```

### Ordering

```python
class ArticleFilterSet(FilterSet):
    title = StringField(lookups=["icontains"])
    status: str

    class Meta:
        order_fields = [
            ('title', 'title'),
            ('views', 'views'),
            ('created_at', 'created_at'),
        ]

# Usage:
# ?order_by=title          # Ascending
# ?order_by=-title         # Descending
# ?order_by=-views         # Most viewed first
# ?order_by=-created_at    # Newest first
```

### Ordering by Annotated Fields

```python
def add_annotations(filterset, queryset):
    return queryset.annotate(
        comment_count=Count('comments')
    )

class ArticleFilterSet(FilterSet):
    class Meta:
        preprocessors = [add_annotations]
        order_fields = [
            ('title', 'title'),
            ('views', 'views'),
            ('comment_count', 'comments'),
        ]

# ?order_by=-comments  # Most commented first
```

### Default Ordering

```python

class ArticleFilterSet(FilterSet):
    class Meta:
        order_fields = [('title', 'title'), ('created_at', 'created_at')]
        default_order_fields = ["created_at"]

# Queries without ?order_by get default ordering
```

### Pagination

```python
from rest_framework.pagination import PageNumberPagination

class ArticlePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class ArticleListView(generics.ListAPIView):
    serializer_class = ArticleSerializer
    pagination_class = ArticlePagination

    def get_queryset(self):
        queryset = Article.objects.all()
        filterset = ArticleFilterSet(request=self.request)
        return filterset.filter_queryset(queryset)

# ?page=1&page_size=20
# ?status=published&order_by=-views&page=2
```

##  Performance Optimization

### Query Optimization

```python
def optimize_queries(filterset, queryset):
    """Optimize all database queries"""
    # Select related ForeignKeys
    queryset = queryset.select_related('author', 'category')

    # Conditionally prefetch M2M
    if 'tags' in filterset.data:
        queryset = queryset.prefetch_related('tags')

    if 'min_comments' in filterset.data or 'has_comments' in filterset.data:
        queryset = queryset.prefetch_related('comments')

    # Only select needed fields
    queryset = queryset.only(
        'id', 'title', 'status', 'views',
        'created_at', 'author_id', 'category_id'
    )

    return queryset

class ArticleFilterSet(FilterSet):
    class Meta:
        preprocessors = [optimize_queries, add_annotations]
```

### Database Indexes

```python
# articles/models.py
class Article(models.Model):
    # ... fields ...

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['category', 'status']),
        ]
```

Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Monitor Performance

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

class ArticleFilterSet(FilterSet):
    class Meta:
        postprocessors = [smart_distinct, monitor_performance]
```

### Complete Production-Ready FilterSet

```python
from django.db.models import Count, Q
from rest_framework.validators import MinValueValidator
from rest_framework.exceptions import ValidationError
from restflow.filters import (
    FilterSet,
    StringField,
    IntegerField,
    BooleanField,
    DateTimeField,
    ListField,
)
import logging

logger = logging.getLogger(__name__)

# Preprocessors
def optimize_queries(filterset, queryset):
    queryset = queryset.select_related('author', 'category')

    if 'tags' in filterset.data:
        queryset = queryset.prefetch_related('tags')

    if 'min_comments' in filterset.data or 'has_comments' in filterset.data:
        queryset = queryset.prefetch_related('comments')

    queryset = queryset.only(
        'id', 'title', 'status', 'views',
        'created_at', 'author_id', 'category_id'
    )

    return queryset

def add_annotations(filterset, queryset):
    return queryset.annotate(
        comment_count=Count('comments')
    )

# Postprocessors
def smart_distinct(filterset, queryset):
    if 'tags' in filterset.data:
        return queryset.distinct()
    return queryset


def monitor_performance(filterset, queryset):
    import time
    start = time.time()
    count = queryset.count()
    duration = time.time() - start

    if duration > 1.0:
        logger.warning(
            f"Slow query: {duration:.2f}s for {count} results. "
            f"Filters: {dict(filterset.data)}"
        )

    return queryset

# FilterSet
class ArticleFilterSet(FilterSet):
    # Text search
    search = StringField(method="filter_search")

    # Basic filters with validation
    title = StringField(min_length=2, lookups=["icontains"])
    status: str
    views = IntegerField(min_value=0, lookups=["comparison"])

    # Related filters
    author = IntegerField(lookup_expr="author__id")
    category_slug = StringField(lookup_expr="category__slug")
    tags: ListField[int]

    # Custom filters
    my_articles = BooleanField(method="filter_my_articles")
    has_comments = BooleanField(method="filter_has_comments")
    min_comments = IntegerField(method="filter_min_comments")

    # Date filters
    published_at = DateTimeField(lookups=["comparison"])
    created_at = DateTimeField(lookups=["comparison"])

    class Meta:
        preprocessors = [
            optimize_queries,
            add_annotations,
        ]

        postprocessors = [
            smart_distinct,
            monitor_performance,
        ]

        order_fields = [
            ('title', 'title'),
            ('views', 'views'),
            ('created_at', 'created_at'),
            ('comment_count', 'comments'),
        ]

        operator = "AND"

    def validate(self, data):
        # Add custom validation here
        return data

    def filter_search(self, filterset, queryset, value):
        return Q(title__icontains=value) | Q(content__icontains=value)

    def filter_my_articles(self, filterset, queryset, value):
        if value and filterset.request and filterset.request.user.is_authenticated:
            return Q(author=filterset.request.user)
        return Q()

    def filter_has_comments(self, filterset, queryset, value):
        if value:
            return Q(comment_count__gt=0)
        return Q(comment_count=0)

    def filter_min_comments(self, filterset, queryset, value):
        return Q(comment_count__gte=value)
```

### Testing

```python
from django.test import TestCase
from django.test.utils import override_settings
from django.db import connection
from rest_framework.test import APIClient

class ArticleFilterPerformanceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create test data...

    @override_settings(DEBUG=True)
    def test_query_count(self):
        """Ensure no N+1 queries"""
        connection.queries_log.clear()

        response = self.client.get('/api/articles/?status=published')

        # Should be 2-3 queries max (with select_related)
        query_count = len(connection.queries)
        self.assertLessEqual(query_count, 3)

    def test_large_dataset_performance(self):
        """Ensure filters are fast"""
        import time

        start = time.time()
        response = self.client.get('/api/articles/?status=published')
        duration = time.time() - start

        # Should complete in under 100ms
        self.assertLess(duration, 0.1)
        self.assertEqual(response.status_code, 200)
```

## Summary

1. **Basic Filtering**: Type annotations and explicit fields
2. **Lookups**: Text, numeric, date lookups and categories
3. **Custom Methods**: Q objects, conditional logic, and the QuerySet caveat
4. **Related Fields**: ForeignKey, ManyToMany, counting, and optimization
5. **Validation**: Field and FilterSet-level validation
6. **Ordering**: Basic and annotated field ordering
7. **Performance**: Query optimization, indexes, and monitoring

## Next Steps

- **[FilterSet Guide](../guide/filtering/filterset.md)** - Complete FilterSet reference with all Meta options, operators, preprocessors, postprocessors, custom methods, and performance patterns
- **[Fields Guide](../guide/filtering/fields.md)** - Every field type, lookup, validation, and PostgreSQL feature
