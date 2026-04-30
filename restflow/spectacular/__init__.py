from restflow.spectacular.parameters import (
    build_filterset_parameters,
    resolve_filterset_class,
)

# drf-spectacular is an optional dependency. Importing the schema-side
# helpers (RestflowAutoSchema, add_filterset_parameters, extensions) is
# guarded so that downstream modules (e.g. restflow.filters.backends)
# can pull schema-parameter helpers without forcing every consumer to
# install drf-spectacular.
try:
    import drf_spectacular

    from restflow.spectacular import extensions
    from restflow.spectacular.hooks import add_filterset_parameters
    from restflow.spectacular.schema import RestflowAutoSchema

    _SPECTACULAR_AVAILABLE = True
except ImportError:  # pragma: no cover - drf-spectacular not installed
    add_filterset_parameters = None
    RestflowAutoSchema = None
    _SPECTACULAR_AVAILABLE = False


__all__ = [
    "RestflowAutoSchema",
    "add_filterset_parameters",
    "build_filterset_parameters",
    "resolve_filterset_class",
]
