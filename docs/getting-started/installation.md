# Installation

Install `drf-restflow`, a declarative library for Django REST Framework that brings modern Python features and FastAPI-like ergonomics to your Django projects.

## Requirements

Before installing `drf-restflow`, ensure you have:

- **Python 3.10 or higher**
- **Django 3.2 or higher**
- **Django REST Framework 3.14 or higher**

## Installation via pip

Install the latest stable release:

Using uv

```bash
uv add drf-restflow
```

```bash
pip install drf-restflow
```


## Optional Dependencies

### PostgreSQL Support

For PostgreSQL-specific features (array fields, full-text search, etc.):

```bash
pip install drf-restflow psycopg2-binary
```

Or if you're already using PostgreSQL with Django, `drf-restflow` will automatically detect it.

## Verifying Installation

Verify the installation by importing the package:

```python
import restflow
print(restflow.__version__)
```

## Django Configuration

No special configuration is needed in Django settings. `drf-restflow` works out of the box with any Django project that has DRF installed.

However, you may want to configure DRF settings if you haven't already:

```python
# settings.py

INSTALLED_APPS = [
    ...
    'rest_framework',
    ...
]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    # Other DRF settings...
}
```

## Compatibility Matrix

| Python | Django | DRF | drf-restflow |
|--------|--------|-----|--------------|
| 3.10   | 3.2-5.1| 3.14+| {{ version }}     |
| 3.11   | 3.2-5.1| 3.14+| {{ version }}     |
| 3.12   | 4.0-5.2| 3.14+| {{ version }}     |
| 3.13   | 4.2-5.2| 3.14+| {{ version }}     |
| 3.14   | 5.1-5.2| 3.14+| {{ version }}     |

## Troubleshooting

### Import Error

If you get an import error:

```python
ImportError: No module named 'restflow'
```

Make sure you've installed the package in the correct environment:

```bash
pip list | grep drf-restflow
```

### Version Conflicts

If you encounter version conflicts with Django or DRF:

```bash
# Check current versions
pip show django djangorestframework

# Upgrade if needed
pip install --upgrade django djangorestframework
```

## What's Next?

Now that you've installed `drf-restflow`, explore the available features:

**Understanding drf-restflow:**
- 📖 [Basic Concepts](concepts.md) - Learn the library's philosophy and design principles
- 📚 [Filtering Tutorial](../tutorial/filtering.md) - Complete walkthrough of filtering features
