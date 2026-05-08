import datetime
from typing import Literal

import pytest
from rest_framework.test import APIRequestFactory

from restflow.filters import (
    DecimalField,
    EmailField,
    FilterSet,
    IntegerField,
    RestflowFilterBackend,
    StringField,
)
from tests.models import SampleModel


class _View:
    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


@pytest.fixture
def request_factory():
    return APIRequestFactory()



@pytest.mark.django_db
def test_filter_queryset_applies_filterset(request_factory):
    SampleModel.objects.create(integer_field=1, string_field="alpha")
    SampleModel.objects.create(integer_field=2, string_field="beta")
    SampleModel.objects.create(integer_field=3, string_field="gamma")

    class SampleFilter(FilterSet):
        integer_field = IntegerField(lookups=["gte"])

    backend = RestflowFilterBackend()
    request = request_factory.get("/?integer_field__gte=2")
    view = _View(filterset_class=SampleFilter)

    qs = backend.filter_queryset(request, SampleModel.objects.all(), view)
    assert set(qs.values_list("integer_field", flat=True)) == {2, 3}


@pytest.mark.django_db
def test_filter_queryset_passthrough_without_filterset(request_factory):
    SampleModel.objects.create(integer_field=1)
    SampleModel.objects.create(integer_field=2)

    backend = RestflowFilterBackend()
    request = request_factory.get("/")
    view = _View()  # no filterset_class

    qs = backend.filter_queryset(request, SampleModel.objects.all(), view)
    assert qs.count() == 2


@pytest.mark.django_db
def test_get_filterset_class_method_takes_precedence(request_factory):
    class FilterA(FilterSet):
        integer_field = IntegerField()

    class FilterB(FilterSet):
        integer_field = IntegerField(lookups=["gte"])

    backend = RestflowFilterBackend()
    view = _View(
        filterset_class=FilterA,
        get_filterset_class=lambda: FilterB,
    )

    assert backend.get_filterset_class(view) is FilterB



def test_schema_emits_no_params_without_filterset_class():
    backend = RestflowFilterBackend()
    assert backend.get_schema_operation_parameters(_View()) == []


def _params_by_name(params):
    return {p["name"]: p for p in params}


def test_schema_basic_field_types():
    class F(FilterSet):
        count: int
        ratio: float
        is_active: bool
        name: str

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(
            _View(filterset_class=F)
        )
    )

    assert params["count"]["schema"] == {"type": "integer"}
    assert params["ratio"]["schema"] == {
        "type": "number",
        "format": "float",
    }
    assert params["is_active"]["schema"] == {"type": "boolean"}
    assert params["name"]["schema"] == {"type": "string"}
    for p in params.values():
        assert p["in"] == "query"
        assert "required" in p


def test_schema_string_formats_for_datetime_email():
    class F(FilterSet):
        created_at: datetime.datetime
        contact = EmailField()

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    assert params["created_at"]["schema"]["format"] == "date-time"
    assert params["contact"]["schema"]["format"] == "email"


def test_schema_decimal_field_carries_precision():
    class F(FilterSet):
        price = DecimalField(max_digits=8, decimal_places=2)

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    schema = params["price"]["schema"]
    assert schema["type"] == "string"
    assert schema["format"] == "decimal"
    assert schema["x-maxDigits"] == 8
    assert schema["x-decimalPlaces"] == 2


def test_schema_choice_field_emits_enum():
    class F(FilterSet):
        status: Literal["active", "inactive", "pending"]

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    schema = params["status"]["schema"]
    assert schema["type"] == "string"
    assert set(schema["enum"]) == {"active", "inactive", "pending"}


def test_schema_list_field_uses_array_form_style():
    class F(FilterSet):
        ids: list[int]

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    p = params["ids"]
    assert p["schema"] == {
        "type": "array",
        "items": {"type": "integer"},
    }
    assert p["explode"] is False
    assert p["style"] == "form"


def test_schema_lookup_variants_are_emitted():
    class F(FilterSet):
        price = IntegerField(lookups=["comparison"])

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )

    expected = {"price", "price__gt", "price__gte", "price__lt", "price__lte"}
    assert expected.issubset(params.keys())
    for name in expected:
        assert params[name]["schema"]["type"] == "integer"


def test_schema_negation_variants_are_emitted_with_description():
    class F(FilterSet):
        category = StringField()

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )

    assert "category" in params
    assert "category!" in params
    description = params["category!"].get("description", "")
    assert description.lower().startswith("exclude where")


def test_schema_lookup_variant_description_includes_verb():
    class F(FilterSet):
        price = IntegerField(lookups=["gte"])

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    desc = params["price__gte"]["description"]
    assert "greater than or equal to" in desc


def test_schema_order_field_emits_enum_array():
    class F(FilterSet):
        class Meta:
            model = SampleModel
            order_fields = [
                ("integer_field", "integer_field"),
                ("string_field", "string_field"),
            ]

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )

    p = params["order_by"]
    assert p["schema"]["type"] == "array"
    enum = set(p["schema"]["items"]["enum"])
    assert {"integer_field", "-integer_field"}.issubset(enum)


def test_schema_required_flag_propagates():
    class F(FilterSet):
        slug = StringField(required=True)

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )

    assert params["slug"]["required"] is True


def test_schema_help_text_appears_in_description():
    class F(FilterSet):
        name = StringField(help_text="Filter by product name")

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )
    assert params["name"]["description"] == "Filter by product name"


def test_schema_suppresses_drf_autogenerated_labels_for_variants():
    class F(FilterSet):
        price = IntegerField(lookups=["gte"])

    backend = RestflowFilterBackend()
    params = _params_by_name(
        backend.get_schema_operation_parameters(_View(filterset_class=F))
    )

    assert params["price__gte"]["description"] == (
        "price is greater than or equal to"
    )
    assert params["price__gte!"]["description"] == (
        "exclude where price is greater than or equal to"
    )


def test_schema_drf_autoschema_round_trip():
    from rest_framework import generics
    from rest_framework.schemas.openapi import AutoSchema
    from rest_framework.test import APIRequestFactory

    class ProductFilter(FilterSet):
        name: str
        price = IntegerField(lookups=["comparison"])

    class ProductView(generics.GenericAPIView):
        filter_backends = [RestflowFilterBackend]
        filterset_class = ProductFilter
        schema = AutoSchema()

    view = ProductView()
    view.request = APIRequestFactory().get("/")
    view.kwargs = {}
    view.format_kwarg = None
    view.schema.view = view

    params = view.schema.get_filter_parameters("/products/", "GET")
    by_name = {p["name"]: p for p in params}

    expected = {
        "name", "name!",
        "price", "price__gt", "price__gte", "price__lt", "price__lte",
        "price!", "price__gt!", "price__gte!", "price__lt!", "price__lte!",
    }
    assert expected.issubset(by_name.keys())
    assert by_name["price__gte"]["schema"]["type"] == "integer"


def test_get_filterset_uses_view_hook_when_defined(request_factory):
    captured = {}

    class SampleFilter(FilterSet):
        integer_field = IntegerField()

    def view_get_filterset(cls):
        captured["cls"] = cls
        return cls(request=request_factory.get("/?integer_field=99"))

    backend = RestflowFilterBackend()
    request = request_factory.get("/?integer_field=1")
    view = _View(
        filterset_class=SampleFilter,
        get_filterset=view_get_filterset,
    )
    fs = backend.get_filterset(request, None, view)
    assert captured["cls"] is SampleFilter
    assert fs is not None


def test_field_description_uses_explicit_label_when_not_autogenerated():
    from restflow.filters.backends import get_field_description

    field = IntegerField(label="A meaningful label")
    description = get_field_description("integer_field", field, "__")
    assert description is not None and "A meaningful label" in description


def test_schema_for_ip_address_field():
    from restflow.filters import IPAddressField
    from restflow.filters.backends import field_to_schema

    schema = field_to_schema(IPAddressField())
    assert schema == {"type": "string"}


def test_schema_for_datetime_field():
    from restflow.filters import DateTimeField
    from restflow.filters.backends import field_to_schema

    schema = field_to_schema(DateTimeField())
    assert schema == {"type": "string", "format": "date-time"}


def test_schema_for_date_field():
    from restflow.filters import DateField
    from restflow.filters.backends import field_to_schema

    schema = field_to_schema(DateField())
    assert schema == {"type": "string", "format": "date"}


def test_schema_for_time_field():
    from restflow.filters import TimeField
    from restflow.filters.backends import field_to_schema

    schema = field_to_schema(TimeField())
    assert schema == {"type": "string", "format": "time"}


def test_schema_for_duration_field():
    from restflow.filters import DurationField
    from restflow.filters.backends import field_to_schema

    schema = field_to_schema(DurationField())
    assert schema == {"type": "string", "format": "duration"}


def test_numeric_schema_includes_min_and_max_when_set():
    from restflow.filters.backends import field_to_schema

    field = IntegerField(min_value=1, max_value=10)
    schema = field_to_schema(field)
    assert schema["minimum"] == 1
    assert schema["maximum"] == 10


def test_string_schema_includes_min_and_max_length_when_set():
    from restflow.filters.backends import field_to_schema

    field = StringField(min_length=2, max_length=8)
    schema = field_to_schema(field)
    assert schema["minLength"] == 2
    assert schema["maxLength"] == 8


def test_list_schema_falls_back_to_string_for_non_field_child():
    from restflow.filters import ListField
    from restflow.filters.backends import field_to_schema

    field = ListField(child=IntegerField())
    field.child = object()
    schema = field_to_schema(field)
    assert schema == {"type": "array", "items": {"type": "string"}}


def test_schema_default_for_unknown_field_type():
    from restflow.filters.backends import field_to_schema
    from restflow.filters.fields import Field

    class _Unknown(Field):
        pass

    schema = field_to_schema(_Unknown())
    assert schema == {"type": "string"}


@pytest.mark.django_db
def test_afilter_queryset_passthrough_without_filterset(request_factory):
    import asyncio

    SampleModel.objects.create(integer_field=1)

    backend = RestflowFilterBackend()
    request = request_factory.get("/")
    view = _View()
    qs = asyncio.run(
        backend.afilter_queryset(request, SampleModel.objects.all(), view)
    )
    assert qs.count() == 1


@pytest.mark.django_db
def test_afilter_queryset_applies_filterset(request_factory):
    import asyncio

    SampleModel.objects.create(integer_field=1)
    SampleModel.objects.create(integer_field=5)

    class SampleFilter(FilterSet):
        integer_field = IntegerField(lookups=["gte"])

    backend = RestflowFilterBackend()
    request = request_factory.get("/?integer_field__gte=3")
    view = _View(filterset_class=SampleFilter)

    qs = asyncio.run(
        backend.afilter_queryset(request, SampleModel.objects.all(), view)
    )
    assert set(qs.values_list("integer_field", flat=True)) == {5}
