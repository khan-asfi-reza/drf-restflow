"""
Some pieces of code taken from:
  - Project Name: django-rest-framework
  - Source URL: https://github.com/encode/django-rest-framework
  - File: tests/test_fields.py

Testing the essential things, as the fields are inherited from `djangorestframework`, only testing basic and
minimal cases.
"""

import datetime
from decimal import Decimal
from types import NoneType
from typing import Optional, Union

import pytest
import pytz
from django.db.models import Q
from rest_framework import serializers

from restflow.filters import (
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    EmailField,
    Field,
    FilterSet,
    FloatField,
    IntegerField,
    StringField,
    TimeField,
    fields,
)


class CustomType(type):
    pass


@pytest.mark.parametrize(
    "data_type",
    [int, float, str, bool, CustomType],
)
def test_get_child_drf_field_from_data_type(data_type):
    if data_type == CustomType:
        with pytest.raises(AssertionError) as error:
            fields.get_field_from_type(data_type)
            assert error.value == fields.DRF_DATA_TYPE_CHILD_ASSERTION_ERROR
    else:
        child = fields.get_field_from_type(data_type)
        assert isinstance(child, serializers.Field)


def get_items(item):
    if isinstance(item, dict):
        return item.items()
    return item


class FieldBaseTest:
    field: type[Field]

    field_kwargs = {}
    valid_inputs = {}
    invalid_inputs = {}
    outputs = {}

    def get_field(self, **kwargs):
        return self.field(**self.field_kwargs, **kwargs)

    def test_valid_inputs(self):
        """
        Ensure that valid values return the expected validated data.
        """
        field = self.get_field(lookup_expr="lookup")
        for input_value, expected_output in get_items(self.valid_inputs):
            assert (
                field.run_validation(input_value) == expected_output
            ), f"input value: {input_value!r}"

    def test_invalid_inputs(self):
        """
        Ensure that invalid values raise the expected validation error.
        """
        field = self.get_field(lookup_expr="lookup")
        for input_value, expected_failure in get_items(self.invalid_inputs):
            with pytest.raises(serializers.ValidationError) as exc_info:
                field.run_validation(input_value)
            assert exc_info.value.detail == expected_failure, f"input value: {input_value!r}"

    @pytest.mark.parametrize(
        ("lookup_param", "val"),
        [
            ("lookup_expr", "val"),
            ("lookup_expr", lambda v: Q(a=v)),
        ],
    )
    def test_field_lookup_expr_param(self, lookup_param, val):
        """
        Ensure that both lookup field and param name is correct.
        """
        field = self.get_field(**{lookup_param: val})
        assert field.lookup_expr == val

    def test_field_lookup_expr_method(self):
        """
        Ensure that lookup_expr or lookup_expr or method is set
        """
        field = self.get_field(
            method="lk",
        )
        assert field.method == "lk"


class TestBooleanField(FieldBaseTest):
    field = fields.BooleanField
    invalid_inputs = {
        "foo": ["Must be a valid boolean."],
        None: ["This field may not be null."],
    }
    valid_inputs = {
        "True": True,
        "TRUE": True,
        "tRuE": True,
        "t": True,
        "T": True,
        "true": True,
        "on": True,
        "ON": True,
        "oN": True,
        "False": False,
        "FALSE": False,
        "fALse": False,
        "f": False,
        "F": False,
        "false": False,
        "off": False,
        "OFF": False,
        "oFf": False,
        "1": True,
        "0": False,
        1: True,
        0: False,
    }


class TestIntegerField(FieldBaseTest):
    field = fields.IntegerField
    invalid_inputs = {
        "foo": ["A valid integer is required."],
        None: ["This field may not be null."],
    }
    valid_inputs = {
        1: 1,
        "1": 1,
        "1.0": 1,
        10: 10,
    }


class TestFloatField(FieldBaseTest):
    field = fields.FloatField
    invalid_inputs = {
        "foo": ["A valid number is required."],
        None: ["This field may not be null."],
    }
    valid_inputs = {
        1.0: 1.0,
        "1.1": 1.1,
        "1.5": 1.5,
        "1.55": 1.55,
        10.76: 10.76,
    }


class TestStringField(FieldBaseTest):
    field = fields.StringField
    invalid_inputs = {}
    valid_inputs = {
        "foo": "foo",
        "1.1": "1.1",
    }


class TestDateTimeField(FieldBaseTest):
    field = fields.DateTimeField
    invalid_inputs = {
        "foo": [
            "Datetime has wrong format. Use one of these formats instead: YYYY-MM-DDThh:mm[:ss[.uuuuuu]]["
            "+HH:MM|-HH:MM|Z]."
        ]
    }
    valid_inputs = {
        "2025-01-01T01:01:01+00:00": datetime.datetime(
            year=2025, month=1, day=1, hour=1, minute=1, second=1, tzinfo=pytz.UTC
        ),
    }


class TestTimeField(FieldBaseTest):
    field = fields.TimeField
    invalid_inputs = {
        "foo": [
            "Time has wrong format. Use one of these formats instead: hh:mm[:ss[.uuuuuu]]."
        ]
    }
    valid_inputs = {
        "01:01:01": datetime.time(hour=1, minute=1, second=1),
    }


class TestDateField(FieldBaseTest):
    field = fields.DateField
    invalid_inputs = {
        "foo": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]
    }
    valid_inputs = {
        "2025-01-01": datetime.date(year=2025, month=1, day=1),
    }


class TestDurationField(FieldBaseTest):
    field = fields.DurationField
    invalid_inputs = {
        "abc": [
            "Duration has wrong format. Use one of these formats instead: [DD] [HH:[MM:]]ss[.uuuuuu]."
        ],
        "3 08:32 01.123": [
            "Duration has wrong format. Use one of these formats instead: [DD] [HH:[MM:]]ss[.uuuuuu]."
        ],
        "-1000000000 00": [
            "The number of days must be between -999999999 and 999999999."
        ],
        "1000000000 00": [
            "The number of days must be between -999999999 and 999999999."
        ],
    }
    valid_inputs = {
        "13": datetime.timedelta(seconds=13),
        "3 08:32:01.000123": datetime.timedelta(
            days=3, hours=8, minutes=32, seconds=1, microseconds=123
        ),
        "08:01": datetime.timedelta(minutes=8, seconds=1),
        datetime.timedelta(
            days=3, hours=8, minutes=32, seconds=1, microseconds=123
        ): datetime.timedelta(days=3, hours=8, minutes=32, seconds=1, microseconds=123),
        3600: datetime.timedelta(hours=1),
        "-999999999 00": datetime.timedelta(days=-999999999),
        "999999999 00": datetime.timedelta(days=999999999),
    }


class TestEmailField(FieldBaseTest):
    field = fields.EmailField
    invalid_inputs = {"foo": ["Enter a valid email address."]}
    valid_inputs = {"user@example.com": "user@example.com"}


class TestDecimalField(FieldBaseTest):
    valid_inputs = {
        "12.3": Decimal("12.3"),
        "0.1": Decimal("0.1"),
        10: Decimal("10"),
        0: Decimal("0"),
        12.3: Decimal("12.3"),
        0.1: Decimal("0.1"),
        "2E+1": Decimal("20"),
    }
    invalid_inputs = (
        (None, ["This field may not be null."]),
        ("", ["A valid number is required."]),
        (" ", ["A valid number is required."]),
        ("abc", ["A valid number is required."]),
        (Decimal("Nan"), ["A valid number is required."]),
        (Decimal("Snan"), ["A valid number is required."]),
        (Decimal("Inf"), ["A valid number is required."]),
        ("12.345", ["Ensure that there are no more than 3 digits in total."]),
        (200000000000.0, ["Ensure that there are no more than 3 digits in total."]),
        ("0.01", ["Ensure that there are no more than 1 decimal places."]),
        (
            123,
            ["Ensure that there are no more than 2 digits before the decimal point."],
        ),
        (
            "2E+2",
            ["Ensure that there are no more than 2 digits before the decimal point."],
        ),
    )
    field = fields.DecimalField
    field_kwargs = {
        "max_digits": 3,
        "decimal_places": 1,
    }


class TestIPAddressField(FieldBaseTest):
    valid_inputs = {
        "127.0.0.1": "127.0.0.1",
        "192.168.33.255": "192.168.33.255",
        "2001:0db8:85a3:0042:1000:8a2e:0370:7334": "2001:db8:85a3:42:1000:8a2e:370:7334",
        "2001:cdba:0:0:0:0:3257:9652": "2001:cdba::3257:9652",
        "2001:cdba::3257:9652": "2001:cdba::3257:9652",
    }
    invalid_inputs = {
        "127001": ["Enter a valid IPv4 or IPv6 address."],
        "127.122.111.2231": ["Enter a valid IPv4 or IPv6 address."],
        "2001:::9652": ["Enter a valid IPv4 or IPv6 address."],
        "2001:0db8:85a3:0042:1000:8a2e:0370:73341": [
            "Enter a valid IPv4 or IPv6 address."
        ],
        1000: ["Enter a valid IPv4 or IPv6 address."],
    }
    field = fields.IPAddressField


class BaseListFieldTest(FieldBaseTest):
    invalid_inputs = {1: ['Expected a list of items but got type "int".']}
    field = fields.ListField

    def test_invalid_inputs(self):
        """
        Ensure that invalid values raise the expected validation error.
        """
        field = self.get_field(lookup_expr="lookup")
        for input_value, _expected_failure in get_items(self.invalid_inputs):
            with pytest.raises(serializers.ValidationError):
                field.run_validation(input_value)


class TestListFieldString(BaseListFieldTest):
    valid_inputs = {"1,2,3,4": ["1", "2", "3", "4"]}
    field_kwargs = {"child": StringField()}


class TestListFieldInt(BaseListFieldTest):
    valid_inputs = {"1,2,3,4": [1, 2, 3, 4]}
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {"child": IntegerField()}


class TestListFieldFloat(BaseListFieldTest):
    valid_inputs = {"1.1,2.2,3.3,4.4": [1.1, 2.2, 3.3, 4.4]}
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {"child": FloatField()}


class TestListFieldDecimal(BaseListFieldTest):
    valid_inputs = {"10,20": [Decimal("10"), Decimal("20")]}
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": DecimalField(max_digits=3, decimal_places=1),
    }


class TestListFieldEmail(BaseListFieldTest):
    valid_inputs = {
        "user1@example.com,user2@example.com": [
            "user1@example.com",
            "user2@example.com",
        ]
    }
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": EmailField(),
    }


class TestListFieldDateTime(BaseListFieldTest):
    valid_inputs = {
        "2025-01-01T01:01:01+00:00,2025-01-02T01:01:01+00:00": [
            datetime.datetime(
                year=2025,
                month=1,
                day=1,
                hour=1,
                minute=1,
                second=1,
                tzinfo=pytz.UTC,
            ),
            datetime.datetime(
                year=2025,
                month=1,
                day=2,
                hour=1,
                minute=1,
                second=1,
                tzinfo=pytz.UTC,
            ),
        ]
    }
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": DateTimeField(),
    }


class TestListFieldDate(BaseListFieldTest):
    valid_inputs = {
        "2025-01-01,2025-01-02": [
            datetime.date(
                year=2025,
                month=1,
                day=1,
            ),
            datetime.date(
                year=2025,
                month=1,
                day=2,
            ),
        ]
    }
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": DateField(),
    }


class TestListFieldTime(BaseListFieldTest):
    valid_inputs = {
        "01:01:01,02:02:02": [
            datetime.time(hour=1, minute=1, second=1),
            datetime.time(hour=2, minute=2, second=2),
        ]
    }
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": TimeField(),
    }


class TestListFieldDuration(BaseListFieldTest):
    valid_inputs = {
        "15,16": [
            datetime.timedelta(seconds=15),
            datetime.timedelta(seconds=16),
        ]
    }
    invalid_inputs = {"a,b,3,4": [""]}
    field_kwargs = {
        "child": DurationField(),
    }


# Additional tests for full coverage


def test_process_lookups_with_all():
    """Test process_lookups with '__all__' special case"""
    from restflow.filters import process_lookups

    # "__all__" expands to lookups from the lookup_categories
    result = process_lookups("__all__", ["basic", "text"])
    assert isinstance(result, list)
    # It should expand to the categories provided
    assert len(result) > 0


def test_process_lookups_with_categories():
    """Test process_lookups with category expansion"""
    from restflow.filters import process_lookups

    # When no lookup_categories provided, only specific lookups are returned
    result = process_lookups(["gte", "lte", "exact"], [])
    assert isinstance(result, list)
    assert "gte" in result
    assert "lte" in result
    assert "exact" in result


def test_process_lookups_with_specific_lookups():
    """Test process_lookups with specific lookup strings"""
    from restflow.filters import process_lookups

    result = process_lookups(["gte", "lte"], [])
    assert "gte" in result
    assert "lte" in result
    assert len(result) == 2


def test_process_lookups_empty():
    """Test process_lookups with None and empty list"""
    from restflow.filters import process_lookups

    assert process_lookups(None, []) == []
    assert process_lookups([], []) == []


def test_process_lookups_invalid_type():
    """Test process_lookups with invalid lookup types"""
    from restflow.filters import process_lookups

    with pytest.raises(AssertionError) as exc:
        process_lookups([1, 2, 3], [])
    assert "`lookups` must be a list of strings" in str(exc.value)


def test_field_method_and_lookup_expr_conflict():
    """Test that method and lookup_expr cannot be used together"""
    with pytest.raises(AssertionError) as exc:
        IntegerField(method="filter_method", lookup_expr="field__gte")
    assert "`method` and `lookup_expr` cannot be used together" in str(exc.value)



def test_field_get_method_as_string():
    """Test get_method when method is a string"""
    class TestFilter(FilterSet):
        integer_field = IntegerField(method="custom_filter")

        def custom_filter(self, request, queryset, value):
            return queryset

    filterset = TestFilter({"integer_field": 10})
    assert callable(filterset.fields["integer_field"].get_method(filterset))


def test_field_get_method_as_callable():
    """Test get_method when method is a callable"""

    def custom_filter(request, queryset, value):
        return queryset

    field = IntegerField(method=custom_filter)
    method = field.get_method()
    assert method == custom_filter


@pytest.mark.django_db
def test_field_apply_filter_with_method_returning_queryset():
    """Test apply_filter when method returns a QuerySet"""
    from django.db.models import QuerySet

    from tests.models import SampleModel

    def filter_method(request, queryset, value):
        return queryset.filter(integer_field=value)

    field = IntegerField(method=filter_method)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_field_apply_filter_with_method_returning_q():
    """Test apply_filter when method returns a Q object"""
    from django.db.models import Q, QuerySet

    from tests.models import SampleModel

    def filter_method(request, queryset, value):
        return Q(integer_field=value)

    field = IntegerField(method=filter_method)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_field_apply_filter_with_string_lookup_expr():
    """Test apply_filter with string lookup_expr"""
    from django.db.models import Q, QuerySet

    from tests.models import SampleModel

    field = IntegerField(lookup_expr="integer_field__gte")
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_lookup_expr_returning_dict():
    """Test apply_filter with callable lookup_expr returning dict"""
    from django.db.models import Q

    from tests.models import SampleModel

    def lookup_func(value):
        return {"integer_field__gte": value}

    field = IntegerField(lookup_expr=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_lookup_expr_returning_q():
    """Test apply_filter with callable lookup_expr returning Q object"""
    from django.db.models import Q

    from tests.models import SampleModel

    def lookup_func(value):
        return Q(integer_field__gte=value)

    field = IntegerField(lookup_expr=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_lookup_expr_invalid_return():
    """Test apply_filter with callable lookup_expr returning invalid type"""
    from tests.models import SampleModel

    def lookup_func(value):
        return "invalid"

    field = IntegerField(lookup_expr=lookup_func)
    qs = SampleModel.objects.all()

    with pytest.raises(AssertionError) as exc:
        field.apply_filter(None, qs, 10)
    assert "Invalid lookup expression" in str(exc.value)


@pytest.mark.django_db
def test_field_apply_filter_with_exclude():
    """Test apply_filter with exclude=True"""
    from django.db.models import Q

    from tests.models import SampleModel

    field = IntegerField(lookup_expr="integer_field", negate=True)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    # Q object should be negated
    assert str(q).startswith("(NOT")


def test_field_str_and_repr():
    """Test __str__ and __repr__ methods"""
    field = IntegerField(lookup_expr="price__gte")
    field.field_name = "price"
    str_repr = str(field)
    assert "IntegerField" in str_repr
    assert "price" in str_repr
    assert repr(field) == str_repr


def test_order_field_process_fields():
    """Test OrderField.process_fields creates ascending and descending variants"""
    from restflow.filters import OrderField

    fields = [("price", "price"), ("name", "name")]
    result = OrderField.process_fields(fields)

    assert ("price", "price") in result
    assert ("-price", "-price") in result
    assert ("name", "name") in result
    assert ("-name", "-name") in result
    assert len(result) == 4


def test_order_field_process_labels():
    """Test OrderField.process_labels creates labels for variants"""
    from restflow.filters import OrderField

    labels = [("price", "Price"), ("name", "Name")]
    result = OrderField.process_labels(labels)

    assert ("price", "Price") in result
    assert ("-price", "Price") in result
    assert ("name", "Name") in result
    assert ("-name", "Name") in result


def test_order_field_process_labels_empty():
    """Test OrderField.process_labels with empty labels"""
    from restflow.filters import OrderField

    result = OrderField.process_labels(None)
    assert result == []


def test_order_field_process_choices():
    """Test OrderField.process_choices adds direction suffixes"""
    from restflow.filters import OrderField

    field = OrderField(fields=[("price", "price")])
    choices = field.process_choices([("price", "Price"), ("-price", "Price")])

    # Check that suffixes are added
    assert any("Ascending" in choice[1] for choice in choices)
    assert any("Descending" in choice[1] for choice in choices)


def test_order_field_process_choices_with_desc_override():
    """Test OrderField.process_choices with override_order_dir='desc'"""
    from restflow.filters import OrderField

    field = OrderField(fields=[("price", "price")], override_order_dir="desc")
    choices = field.process_choices([("price", "Price"), ("-price", "Price")])

    # With desc override, meanings should be reversed
    assert len(choices) == 2


@pytest.mark.django_db
def test_order_field_apply_filter():
    """Test OrderField.apply_filter orders the queryset"""
    from django.db.models import QuerySet

    from restflow.filters import OrderField
    from tests.models import SampleModel

    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_descending():
    """Test OrderField.apply_filter with descending order"""
    from django.db.models import QuerySet

    from restflow.filters import OrderField
    from tests.models import SampleModel

    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["-integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_override():
    """Test OrderField.apply_filter with override_order_dir"""
    from django.db.models import QuerySet

    from restflow.filters import OrderField
    from tests.models import SampleModel

    field = OrderField(
        fields=[("integer_field", "integer_field")], override_order_dir="desc"
    )
    qs = SampleModel.objects.all()
    result_qs, _q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_order_field_apply_filter_with_method():
    """Test OrderField.apply_filter when method is provided"""
    from django.db.models import QuerySet

    from restflow.filters import OrderField
    from tests.models import SampleModel

    def custom_order(request, queryset, value):
        return queryset.order_by(*value)

    field = OrderField(fields=[("integer_field", "integer_field")], method=custom_order)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


def test_list_field_to_internal_value_with_list():
    """Test ListField.to_internal_value with list input"""
    field = fields.ListField(child=IntegerField())
    result = field.to_internal_value([1, 2, 3])
    assert result == [1, 2, 3]


def test_list_field_to_internal_value_with_string():
    """Test ListField.to_internal_value with comma-separated string"""
    field = fields.ListField(child=IntegerField())
    result = field.to_internal_value("1,2,3")
    assert result == [1, 2, 3]


def test_list_field_to_internal_value_with_string_whitespace():
    """Test ListField.to_internal_value strips whitespace"""
    field = fields.ListField(child=IntegerField())
    result = field.to_internal_value("1, 2, 3")
    assert result == [1, 2, 3]


def test_get_field_from_type_unsupported():
    """Test get_field_from_type with unsupported type raises AssertionError"""

    class UnsupportedType:
        pass

    with pytest.raises(AssertionError) as exc:
        fields.get_field_from_type(UnsupportedType)
    assert "`annotations` must be in" in str(exc.value)


def test_get_field_from_type_with_literal():
    """Test get_field_from_type with Literal type"""
    from typing import Literal

    field = fields.get_field_from_type(Literal["a", "b", "c"])
    assert isinstance(field, fields.ChoiceField)
    assert len(field.choices) == 3


def test_get_field_from_type_with_optional():
    """Test get_field_from_type with Optional type"""
    from typing import Optional # noqa

    field = fields.get_field_from_type(Optional[int])
    assert isinstance(field, IntegerField)


@pytest.mark.parametrize("dt", [None, Optional[None], Union[None], Union[NoneType]])
@pytest.mark.django_db
def test_get_field_from_type_with_optional_invalid(dt):
    """Test get_field_from_type with Optional[None] raises exception"""
    with pytest.raises(AssertionError):
        fields.get_field_from_type(dt)


def test_get_field_from_type_with_list():
    """Test get_field_from_type with List type"""

    field = fields.get_field_from_type(list[int], field_name="ids")
    assert isinstance(field, fields.ListField)
    assert isinstance(field.child, IntegerField)
    assert field.lookup_expr == "ids__in"


def test_get_field_from_type_with_bare_list():
    """Test get_field_from_type with bare list type"""
    field = fields.get_field_from_type(list, field_name="items")
    assert isinstance(field, fields.ListField)
    assert isinstance(field.child, StringField)  # Defaults to str
    assert field.lookup_expr == "items__in"


def test_choice_field():
    """Test ChoiceField basic functionality"""
    field = fields.ChoiceField(
        choices=[("a", "Option A"), ("b", "Option B")], lookup_expr="choice_field"
    )
    assert field.run_validation("a") == "a"


@pytest.mark.django_db
def test_multiple_choice_field():
    """Test MultipleChoiceField basic functionality"""
    field = fields.MultipleChoiceField(
        choices=[("a", "Option A"), ("b", "Option B")], lookup_expr="choices"
    )
    result = field.run_validation(["a", "b"])
    assert sorted(result) == ["a", "b"]
