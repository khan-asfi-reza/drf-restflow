import pytest

spectacular = pytest.importorskip("drf_spectacular")

from django.urls import path
from drf_spectacular.generators import SchemaGenerator
from rest_framework import serializers as drf_serializers

from restflow.filters import FilterSet
from restflow.filters.fields import IntegerField, StringField
from restflow.spectacular import RestflowAutoSchema
from restflow.spectacular.hooks import add_filterset_parameters
from restflow.spectacular.parameters import resolve_filterset_class
from restflow.views import AsyncListAPIView
from tests.models import SampleModel


class SampleSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SampleModel
        fields = ["id", "integer_field", "string_field"]


class SampleFilterSet(FilterSet):
    integer_field = IntegerField(
        db_field="integer_field", lookups=["gte", "lte"]
    )
    string_field = StringField(
        db_field="string_field", lookups=["icontains"]
    )


class FilterableView(AsyncListAPIView):
    serializer_class = SampleSerializer
    filterset_class = SampleFilterSet
    schema = RestflowAutoSchema()

    def get_queryset(self):
        return SampleModel.objects.all().order_by("id")


def build_schema(view_callable, hook=None):
    urlpatterns = [path("widgets/", view_callable, name="widgets-list")]
    generator = SchemaGenerator(patterns=urlpatterns)
    schema = generator.get_schema(request=None, public=True)
    if hook is not None:
        schema = hook(schema, generator)
    return schema


def test_filterset_parameters_appear_in_schema():
    schema = build_schema(FilterableView.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert "integer_field__gte" in parameter_names
    assert "integer_field__lte" in parameter_names
    assert "string_field__icontains" in parameter_names


def test_postprocessing_hook_injects_filter_params():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(HookView.as_view(), hook=add_filterset_parameters)
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert "integer_field__gte" in parameter_names


def test_postprocessing_hook_skips_views_without_filterset():
    class PlainView(AsyncListAPIView):
        serializer_class = SampleSerializer
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(PlainView.as_view(), hook=add_filterset_parameters)
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert "integer_field__gte" not in parameter_names


def test_postprocessing_hook_does_not_duplicate_existing_keys():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(HookView.as_view(), hook=add_filterset_parameters)
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert parameter_names.count("integer_field__gte") == 1


def test_postprocessing_hook_swallows_filterset_build_failure():
    class BrokenFilterSet:
        pass

    class BrokenView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = BrokenFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(BrokenView.as_view(), hook=add_filterset_parameters)
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_resolve_filterset_class_swallows_exceptions_in_getter():
    class BrokenView:
        def get_filterset_class(self):
            msg = "boom"
            raise RuntimeError(msg)

        filterset_class = SampleFilterSet

    assert resolve_filterset_class(BrokenView()) is SampleFilterSet


def test_resolve_filterset_class_uses_getter_when_returns_class():
    class GetterView:
        def get_filterset_class(self):
            return SampleFilterSet

    assert resolve_filterset_class(GetterView()) is SampleFilterSet


def test_resolve_filterset_class_falls_back_when_getter_returns_none():
    class GetterView:
        def get_filterset_class(self):
            return None

        filterset_class = SampleFilterSet

    assert resolve_filterset_class(GetterView()) is SampleFilterSet


def test_resolve_filterset_class_returns_none_for_unconfigured_view():
    class PlainView:
        pass

    assert resolve_filterset_class(PlainView()) is None


class EmptyFilterSet(FilterSet):
    class Meta:
        model = SampleModel
        fields = []


def test_postprocessing_hook_skips_when_filterset_yields_no_params():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = EmptyFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(HookView.as_view(), hook=add_filterset_parameters)
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert "integer_field__gte" not in parameter_names


def test_postprocessing_hook_skips_path_with_no_matching_method():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    urlpatterns = [path("widgets/", HookView.as_view(), name="widgets-list")]
    generator = SchemaGenerator(patterns=urlpatterns)
    schema = generator.get_schema(request=None, public=True)
    schema["paths"]["/widgets/"].pop("get", None)
    schema["paths"]["/extra/"] = {}
    schema = add_filterset_parameters(schema, generator)
    assert "/extra/" in schema["paths"]


def test_postprocessing_hook_idempotent_on_repeated_call():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    urlpatterns = [path("widgets/", HookView.as_view(), name="widgets-list")]
    generator = SchemaGenerator(patterns=urlpatterns)
    schema = generator.get_schema(request=None, public=True)
    schema = add_filterset_parameters(schema, generator)
    schema = add_filterset_parameters(schema, generator)
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert parameter_names.count("integer_field__gte") == 1


def test_schema_get_filter_parameters_swallows_build_failure():
    class BrokenFilterSet:
        pass

    class BrokenView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = BrokenFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    schema = build_schema(BrokenView.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


class DuplicateProducingBackend:
    def get_schema_operation_parameters(self, view):
        return [{"name": "integer_field__gte", "in": "query"}]

    def filter_queryset(self, request, queryset, view):
        return queryset


def test_schema_dedupes_filterset_param_when_backend_already_emits_it():
    from rest_framework.generics import ListAPIView

    class DupView(ListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        filter_backends = [DuplicateProducingBackend]
        schema = RestflowAutoSchema()
        queryset = SampleModel.objects.all().order_by("id")

    schema = build_schema(DupView.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    parameter_names = [p["name"] for p in op.get("parameters", [])]
    assert parameter_names.count("integer_field__gte") == 1


def test_postprocessing_hook_skips_param_already_in_operation():
    class HookView(AsyncListAPIView):
        serializer_class = SampleSerializer
        filterset_class = SampleFilterSet
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return SampleModel.objects.all().order_by("id")

    urlpatterns = [path("widgets/", HookView.as_view(), name="widgets-list")]
    generator = SchemaGenerator(patterns=urlpatterns)
    schema = generator.get_schema(request=None, public=True)
    op = schema["paths"]["/widgets/"]["get"]
    op["parameters"] = [
        {"name": "integer_field__gte", "in": "query"}
    ]
    schema = add_filterset_parameters(schema, generator)
    parameter_names = [p["name"] for p in op["parameters"]]
    assert parameter_names.count("integer_field__gte") == 1
