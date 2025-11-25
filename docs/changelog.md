# Changelog

All notable changes to drf-restflow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0a1] - 2025-11-25

### Added

#### Core Features
- **FilterSet**: Declarative filtering system for Django REST Framework
- **Field Types**: Comprehensive set of filter fields
  - StringField, IntegerField, FloatField, DecimalField
  - BooleanField, DateField, DateTimeField, TimeField, DurationField
  - ChoiceField, MultipleChoiceField
  - EmailField, IPAddressField
  - ListField for array filtering
  - OrderField for result ordering
  - RelatedField for related fields in models
  - Field base class for custom filters

#### Declaration Styles
- Type annotation support (`name: str`, `price: int`)
- Explicit field declarations
- Model-based automatic field generation
- Mixed declaration styles

#### Lookup System
- Automatic lookup generation from field definitions
- Lookup categories (basic, text, comparison, date, time, postgres, pg_array)
- Custom lookup expressions via strings or callables
- Field variants (base field + lookups + negations)

#### Filtering Features
- Negation support via `!` suffix
- Multiple filter operators (AND, OR, XOR)
- Custom filter methods
- Preprocessors and postprocessors
- Related field filtering

#### Ordering
- OrderField for flexible result ordering
- Ascending/descending support
- Multiple field ordering
- Configurable ordering direction

#### PostgreSQL Support
- PostgreSQL array field filtering
- Array lookups (contains, overlaps, contained_by)
- Full-text search support
- Trigram similarity

#### Model Integration
- Automatic field generation from Django models
- Support for model field types
- ForeignKey and OneToOneField filtering
- Model choice field detection

#### Validation
- Built on DRF's validation system
- Automatic type conversion
- Field-level and custom validators
- Detailed error messages

#### Type Safety
- Python type hint support
- Automatic field type inference
- Type mapping for common Python types
- Literal type for choices

### Documentation
- Comprehensive user guide
- API reference
- Quick start tutorial
- PostgreSQL guide
- Migration guide from django-filter

### Testing
- Test suite with 95%+ coverage
- PostgreSQL-specific tests
- Multiple Python version support (3.10-3.14)
- Multiple Django version support (3.2-5.2)
- CI/CD with GitHub Actions

### Developer Experience
- Modern Python features (type hints, dataclasses)
- Clear error messages
- Extensive docstrings
- IDE-friendly API

## Version Support

| Version | Python | Django | DRF | Status |
|---------|--------|--------|-----|--------|
| 1.0.0a1 | 3.10-3.14 | 3.2-5.2 | 3.14+ | Alpha |

## Migration from django-filter

drf-restflow offers similar functionality to django-filter with a more modern, declarative API. Key differences:

- **Type annotations**: Use Python type hints instead of explicit field declarations
- **Automatic negation**: Built-in `!` suffix support for all filters
- **Lookup categories**: Group related lookups (e.g., "comparison" for gt/gte/lt/lte)
- **Better validation**: Integrated with DRF's validation system

For migration assistance, refer to the [FilterSet Guide](guide/filtering/filterset.md) and [Fields Guide](guide/filtering/fields.md) for comprehensive documentation.

## Deprecation Policy

Following semantic versioning:

- **Major versions** (x.0.0): May include breaking changes
- **Minor versions** (0.x.0): New features, backward compatible
- **Patch versions** (0.0.x): Bug fixes, backward compatible

Deprecation warnings will be issued for at least one minor version before removal.

## Reporting Issues

Found a bug or have a feature request? Please open an issue on [GitHub](https://github.com/khan-asfi-reza/drf-restflow/issues).

## Contributing

See [Contributing Guide](contributing.md) for information on how to contribute to this changelog and the project.