# RestflowFilterBackend

The DRF filter backend that plugs a `FilterSet` into a view and
emits OpenAPI parameters. See the
[DRF Integration guide](../../guide/filtering/integration.md) for
an overview and worked examples.

::: restflow.filters.RestflowFilterBackend
    options:
      members:
        - get_filterset_class
        - get_filterset
        - filter_queryset
        - get_schema_operation_parameters
