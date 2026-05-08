from types import NoneType
from typing import Optional, Union

import pytest
from django.db.models import Q, QuerySet

from restflow.filters.fields import (
    IntegerField,
    MultipleChoiceField,
    OrderField,
    build_filter_field,
)
from tests.models import SampleModel


@pytest.mark.django_db
def test_field_apply_filter_with_method_returning_queryset():
    def filter_method(request, queryset, value):
        return queryset.filter(integer_field=value)

    field = IntegerField(method=filter_method)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_field_apply_filter_with_method_returning_q():
    def filter_method(request, queryset, value):
        return Q(integer_field=value)

    field = IntegerField(method=filter_method)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_field_apply_filter_with_string_filter_by():
    field = IntegerField(filter_by="integer_field__gte")
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_returning_dict():
    def lookup_func(value):
        return {"integer_field__gte": value}

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_returning_q():
    def lookup_func(value):
        return Q(integer_field__gte=value)

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_invalid_return():
    def lookup_func(value):
        return "invalid"

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()

    with pytest.raises(AssertionError) as exc:
        field.apply_filter(None, qs, 10)
    assert "Invalid lookup expression" in str(exc.value)


@pytest.mark.django_db
def test_field_apply_filter_with_exclude():
    field = IntegerField(filter_by="integer_field", negate=True)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)
    assert isinstance(q, Q)
    assert str(q).startswith("(NOT")


@pytest.mark.django_db
def test_order_field_apply_filter():
    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_descending():
    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["-integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_override():
    field = OrderField(
        fields=[("integer_field", "integer_field")], override_order_direction="desc"
    )
    qs = SampleModel.objects.all()
    result_qs, _q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_order_field_apply_filter_with_method():
    def custom_order(request, queryset, value):
        return queryset.order_by(*value)

    field = OrderField(fields=[("integer_field", "integer_field")], method=custom_order)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_string_method_on_filterset():
    from restflow.filters import FilterSet

    class FS(FilterSet):
        sort = OrderField(
            fields=[("integer_field", "integer_field")],
            method="custom_order",
        )

        def custom_order(self, queryset, value):
            return queryset.order_by(*value)

    fs = FS(data={"sort": "integer_field"})
    field = fs.fields["sort"]
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(fs, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.parametrize("dt", [None, Optional[None], Union[None], Union[NoneType]])
@pytest.mark.django_db
def test_get_field_from_type_with_optional_invalid(dt):
    with pytest.raises(AssertionError):
        build_filter_field(dt)


@pytest.mark.django_db
def test_multiple_choice_field():
    field = MultipleChoiceField(
        choices=[("a", "Option A"), ("b", "Option B")], filter_by="choices"
    )
    result = field.run_validation(["a", "b"])
    assert sorted(result) == ["a", "b"]


@pytest.mark.django_db
def test_order_field_multi_value_orders_by_all_fields_in_order():
    SampleModel.objects.create(integer_field=2, string_field="a")
    SampleModel.objects.create(integer_field=2, string_field="b")
    SampleModel.objects.create(integer_field=1, string_field="z")

    field = OrderField(
        fields=[
            ("integer_field", "integer_field"),
            ("string_field", "string_field"),
        ],
    )
    qs = SampleModel.objects.all()
    result_qs, _q = field.apply_filter(None, qs, ["integer_field", "-string_field"])

    pairs = list(result_qs.values_list("integer_field", "string_field"))
    assert pairs == [(1, "z"), (2, "b"), (2, "a")]


def test_filterset_metaclass_rejects_unknown_method_string():
    from django.core.exceptions import ImproperlyConfigured

    from restflow.filters.fields import IntegerField
    from restflow.filters.filters import FilterSet

    with pytest.raises(ImproperlyConfigured, match="does not define"):

        class _BadFS(FilterSet):
            count = IntegerField(method="missing_method")
