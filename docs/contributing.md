# Contributing to Restflow

Thanks for considering contributing to Restflow. This is a
declarative library on top of Django REST Framework.


# The Vision

Restflow works on top of DRF. The project
leverages DRF's serializer and validation infrastructure and adds
declarative classes for the parts of an API that turn into
boilerplate over time. Any new idea is welcome.

The library covers:

- **Caching**: declarative cache-key construction, model-signal-driven
  invalidation, and a pluggable dispatcher layer.
- **Filtering**: declarative `FilterSet` classes with type
  annotations, automatic lookup and negation variants, and a DRF
  backend that emits OpenAPI parameters.
- **Serializers**: type-driven `Serializer`, `ModelSerializer`,
  `HyperlinkedModelSerializer`, and `InlineSerializer` with an async
  surface (`ais_valid`, `asave`, `acreate`, `aupdate`).
- **Authentication**: async-native JWT auth with PyJWT, built-in
  obtain/refresh/blacklist views, plus async wrappers for the standard
  DRF authenticators and an optional adapter for
  djangorestframework-simplejwt.
- **Permissions**: async-aware permission classes and async-native
  subclasses of DRF's `&`, `|`, `~` operator classes.
- **Views**: full async stack (`AsyncAPIView`, eight generic views,
  five mixins, four viewsets) with `ActionConfig` for per-action
  overrides and `PostFetch` for after-pagination joins.
- **Pagination**: async page-number, limit-offset, cursor, and fast
  paginators that drive `apaginate_queryset()`.
- **Throttling**: async throttle classes backed by Django's async
  cache.
- **Responses**: streaming JSON, NDJSON, and Server-Sent Events
  responses for large or open-ended payloads.
- **Exception handler**: drop-in DRF exception handler that renders
  every error as a stable envelope.
- **Spectacular**: drf-spectacular adapter for restflow view
  conventions.
- **Testing**: `AsyncAPIClient`, `AsyncAPIRequestFactory`, four async
  test case bases, and `force_authenticate`.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Familiarity with Django and Django REST Framework

### Setting Up Development Environment

1. **Fork and Clone**

Fork the repo from github, [Restflow](https://github.com/khan-asfi-reza/drf-restflow)

2. **Install Development Dependencies**

Using uv [Recommended]

```bash
uv sync --all-groups
```

Or using pip and virtual env

```bash
pip install -r requirements/requirements-dev.txt
``````

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/branch-name
# or
git checkout -b fix/branch-name
```

### 2. Make Changes

Follow the project's coding standards and write tests for new features.

### 3. Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/filters/test_fields.py

# Run with coverage
pytest --cov=restflow --cov-report=html

# Run tox for all Python versions
tox
```

### 4. Lint the Code

```bash
ruff check restflow
```

To fix

```bash
ruff check resflow --fix
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: add new feature"
```

Follow conventional commit messages:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test changes
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

### 6. Push and Create Pull Request

```bash
git push origin feature/branch-name
```

Then create a pull request on GitHub.

## Code Standards

### Python Style

- Follow PEP 8
- Use type hints
- Maximum line length: 80 characters
- Use ruff for linting and formatting

### Docstrings

Use Google-style docstrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """
    Short description of the function.

    Longer description if needed, explaining the function's behavior,
    edge cases, and usage examples.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: Description of when this error is raised.

    Examples:
        >>> function_name("test", 42)
        True
    """
    pass
```

### Tests

- Write tests for all new features
- Maintain or improve code coverage
- Use descriptive test names

```python
def test_field_generates_lookup_variants():
    field = IntegerField(lookups=["gte", "lte"])
    variants = field.get_lookup_variants()
    assert "gte" in variants
    assert "lte" in variants
```


## Project Structure

```
drf-restflow/
├── restflow/
│   ├── __init__.py
│   ├── exceptions.py
│   ├── helpers.py
│   ├── settings.py
│   ├── tasks.py
│   ├── authentication/
│   ├── caching/
│   ├── filters/
│   ├── pagination/
│   ├── permissions/
│   ├── responses/
│   ├── serializers/
│   ├── spectacular/
│   ├── test/
│   ├── throttling/
│   └── views/
├── tests/
│   ├── conftest.py
│   ├── models.py
│   ├── smoke/
│   ├── unit/
│   └── integration/
├── docs/
├── pyproject.toml
├── tox.ini
└── README.md
```

## Running Tests

### All Tests

```bash
python runtests.py
```

### Specific Test Module

```bash
python runtests.py tests/filters/test_fields.py
```

### With Coverage

```bash
python runtests.py --cov=restflow --cov-report=html
open htmlcov/index.html
```

### PostgreSQL Tests

```bash
# Set up PostgreSQL database
export POSTGRES_DB_URL="postgresql://user:password@localhost:5432/test_db"

# Run PostgreSQL tests
pytest -m postgres
```

### Tox (Multiple Python Versions)

```bash
# Run all environments
tox

# Run specific environment
tox -e py312

# Run PostgreSQL tests
tox -e py312-postgres
```

## Documentation

### Building Documentation

```bash
# Install docs dependencies
pip install mkdocs mkdocs-material

# Serve locally
mkdocs serve

# Build
mkdocs build
```

## Writing Documentation

- Use clear, concise language
- Include code examples
- Add usage patterns and common pitfalls
- Update API reference when adding new features

## Pull Request Process

1. **Ensure tests pass**: All tests must pass
2. **Update documentation**: Document new features
3. **Add changelog entry**: Update CHANGELOG.md
4. **Code review**: Address review feedback
5. **Squash commits**: Clean up commit history if needed

### PR Checklist

- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] Code passes linting
- [ ] All tests pass
- [ ] Commit messages follow conventions

## Reporting Issues

When reporting bugs, include:

1. **Description**: Clear description of the issue
2. **Steps to reproduce**: Minimal code to reproduce
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happens
5. **Environment**:
   - Python version
   - Django version
   - DRF version
   - Restflow version

Example:

```
**Bug Description**
FilterSet raises TypeError when using List[int] annotation.

**To Reproduce**
```python
class MyFilterSet(FilterSet):
    ids: List[int]
```

**Expected**: Should create ListField with IntegerField child
**Actual**: Raises TypeError

**Environment**
- Python 3.12
- Django 5.0
- DRF 3.14
- drf-restflow 


## Feature Requests

When proposing features, include:

1. **Use case**: Why is this needed?
2. **Proposed API**: How should it work?
3. **Alternatives**: Other approaches considered
4. **Implementation**: Ideas for implementation


## Versioning

Following semantic versioning:

- **Major versions** (x.0.0): May include breaking changes
- **Minor versions** (0.x.0): New features, backward compatible
- **Patch versions** (0.0.x): Bug fixes, backward compatible
- **Pre-Release versions** (0.0.0(a|b|rc)x): Pre-release candidates, eg: 1.0.0a1 -> alpha release, 1.0.0b1 -> beta release