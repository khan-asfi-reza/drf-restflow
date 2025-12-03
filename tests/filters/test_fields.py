"""
Some pieces of code taken from:
  - Project Name: django-rest-framework
  - Source URL: https://github.com/encode/django-rest-framework
  - File: tests/test_py

Testing the essential things, as the fields are inherited from `djangorestframework`
"""

import datetime
import decimal
from decimal import Decimal
from types import NoneType
from typing import Optional, Union
from unittest.mock import MagicMock

import pytest
import pytz
from django.db.models import Q, QuerySet
from rest_framework import serializers

from restflow.filters import FilterSet
from restflow.filters.fields import (
    LOOKUP_CATEGORIES,
    BooleanField,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    Email,
    EmailField,
    Field,
    FloatField,
    IntegerField,
    IPAddress,
    IPAddressField,
    ListField,
    MultipleChoiceField,
    OrderField,
    RelatedField,
    StringField,
    TimeField,
    extract_model_fields,
    get_field_from_type,
    process_lookups,
)
from tests.models import SampleModel

TEST_DATE_TIME = datetime.datetime(
    year=2025, month=1, day=1, hour=1, minute=1, second=1, tzinfo=pytz.UTC
)

TEST_DATE_TIME_2 = datetime.datetime(
    year=2025, month=1, day=2, hour=1, minute=1, second=1, tzinfo=pytz.UTC
)


def get_items(item):
    if isinstance(item, dict):
        return item.items()
    return item


@pytest.mark.parametrize(
    "data_type",
    [
        int,
        float,
        str,
        bool,
        datetime.datetime,
        datetime.date,
        datetime.time,
        datetime.timedelta,
        decimal.Decimal,
        Email,
        IPAddress,
    ]
)
def test_get_child_drf_field_from_data_type(data_type):
    # Valid data types should pass
    child = get_field_from_type(data_type)
    assert isinstance(child, serializers.Field)


def test_get_child_drf_field_from_custom_type():
    with pytest.raises(AssertionError):
        class CustomField:
            pass
        get_field_from_type(CustomField)



class FieldBaseTest:
    field: type[Field]

    field_kwargs = {}
    valid_inputs = {}
    invalid_inputs = {}
    outputs = {}
    filter_lookup_suffix = ""

    def get_field(self, **kwargs):
        return self.field(**self.field_kwargs, **kwargs)

    @staticmethod
    def make_qs(values):
        values = values if isinstance(values, (list, tuple)) else [values]
        qs = QuerySet(model=None)
        qs._result_cache = values
        return qs


    def _assert_filter_by_apply_filter(self, field, negate=False):
        # This makes sure the apply_filter logic is properly handled for variants for filter_by
        # For string, callable and dict filter_by
        for input_value in self.valid_inputs.values():
            qs = self.make_qs(input_value)
            _actual_qs, actual_q = field.apply_filter(None, qs, input_value)
            expected_q = Q(**{f"field{self.filter_lookup_suffix}": input_value})
            if negate:
                expected_q = ~expected_q
            assert actual_q == expected_q, f"input value: {input_value!r}"


    def _assert_method_apply_filter(self, field, filterset=None):
        # This makes sure the apply_filter logic is properly handled for variants for method
        # For both string and callable methods
        for input_value in self.valid_inputs.values():
            qs = self.make_qs(input_value)
            _actual_qs, _ = field.apply_filter(filterset, qs, input_value)
            assert qs == _actual_qs, f"input value: {input_value!r}"

    def test_field_apply_filter_string_filter_by(self):
        # Tests if `filter_by` as a string is returning the valid Q object
        field = self.get_field(filter_by=f"field{self.filter_lookup_suffix}",)
        self._assert_filter_by_apply_filter(field)
        field_negated = self.get_field(filter_by=f"field{self.filter_lookup_suffix}", negate=True)
        self._assert_filter_by_apply_filter(field_negated, negate=True)

    def test_field_apply_filter_func_filter_by(self):
        # Tests if `filter_by` as a function is returning the valid Q object
        # It should return a Q object with Q(field=x)
        field = self.get_field(filter_by=lambda x: Q(**{
            f"field{self.filter_lookup_suffix}": x
        }))
        self._assert_filter_by_apply_filter(field)

    def test_field_apply_filter_dict_filter_by(self):
        # Tests if `filter_by` as a function is returning the valid Q object
        # It should return a Q object with Q(field=x)
        field = self.get_field(filter_by=lambda x: {f"field{self.filter_lookup_suffix}": x})
        self._assert_filter_by_apply_filter(field)

    def test_field_apply_filter_method_as_callable(self):
        # Tests if the filter method is being called with the correct parameters
        # Tests if the callable function is executed
        def filter_method(filterset, queryset, _):
            assert filterset is not None
            return queryset

        field = self.get_field(method=filter_method)
        self._assert_method_apply_filter(field, MagicMock())

    def test_field_apply_filter_method_as_string(self):
        # Tests if the string method is executed
        class DummyFilterSet:
            @staticmethod
            def filter_method(filterset, queryset, _):
                assert filterset is not None
                return queryset

        field = self.get_field(method="filter_method")
        self._assert_method_apply_filter(field, DummyFilterSet())

    def test_valid_inputs(self):
        """
        Ensure that valid values return the expected validated data.
        """
        field = self.get_field(filter_by="lookup")
        for input_value, expected_output in get_items(self.valid_inputs):
            assert (
                field.run_validation(input_value) == expected_output
            ), f"input value: {input_value!r}"

    def test_invalid_inputs(self):
        """
        Ensure that invalid values raise the expected validation error.
        """
        field = self.get_field(filter_by="lookup")
        for input_value, expected_failure in get_items(self.invalid_inputs):
            with pytest.raises(serializers.ValidationError) as exc_info:
                field.run_validation(input_value)
            assert exc_info.value.detail == expected_failure, f"input value: {input_value!r}"

    def test_method_should_be_string_or_callable(self):
        """Test that the method should be string or callable"""
        with pytest.raises(TypeError):
            self.get_field(method=1)


    def test_validate_lookups(self):
        # `db_field` is not specified then setting lookups will raise error.
        with pytest.raises(AssertionError):
            self.get_field(filter_by="field__gte", lookups=["lt"])

    @pytest.mark.parametrize(
        ("lookup_param", "val"),
        [
            ("filter_by", "val"),
            ("filter_by", lambda v: Q(a=v)),
        ],
    )
    def test_field_filter_by_param(self, lookup_param, val):
        """
        Ensure that the lookup field is correct.
        """
        field = self.get_field(**{lookup_param: val})
        assert field.filter_by == val


    def test_field_method_and_filter_by_conflict(self):
        """Test that method and filter_by cannot be used together"""
        with pytest.raises(AssertionError) as exc:
            self.get_field(method="filter_method", filter_by="field__gte")
        assert "`method` and `filter_by` cannot be used together" in str(exc.value)

    def test_field_get_method_as_string(self):
        """Test get_method when `method` is a string"""
        class TestFilter(FilterSet):
            field_1 = self.get_field(method="custom_filter")

            @staticmethod
            def custom_filter(_filterset, queryset, value):
                nonlocal self
                assert _filterset.__class__ == self.__class__
                assert value == next(iter(self.valid_inputs.values()))
                return queryset

        filterset = TestFilter({"field_1": next(iter(self.valid_inputs.keys()))})
        assert callable(filterset.fields["field_1"].get_method(filterset))

    def test_field_get_method_as_callable(self):
        """Test get_method when `method` is a callable function"""

        def custom_filter(_filterset, queryset, value):
            nonlocal self
            assert _filterset.__class__ == self.__class__
            assert value == next(iter(self.valid_inputs.values()))
            return queryset

        class TestFilter(FilterSet):
            field_1 = self.get_field(method=custom_filter)

        filterset = TestFilter({"field_1": next(iter(self.valid_inputs.keys()))})
        assert callable(filterset.fields["field_1"].get_method(filterset))


    @pytest.mark.parametrize(
        ("param", "expected"), [
            (["gte", "lte"], ["gte", "lte"]),
            (("gte", "lte"), ["gte", "lte"]),
            (["comparison", "gte", "lte", "lt"], LOOKUP_CATEGORIES.get("comparison")),
            (["comparison", ], LOOKUP_CATEGORIES.get("comparison")),
            (
                    {"comparison": {"allow_negate": False}},
                    {k: {"allow_negate": True} for k in LOOKUP_CATEGORIES.get("comparison")},
            ),
        ]
    )
    def test_lookups_with_iterable(self, param, expected):
        # Tests dict, list, tuple variations of process lookups with categories.
        field = self.get_field(db_field="db_field", lookups=param)
        assert sorted(field.lookups) == sorted(expected)

    def test_lookups_with_string_all(self, ):
        """Test process_lookups with '__all__', it should return field default lookups"""
        field = self.get_field(db_field="db_field", lookups="__all__")
        assert sorted(field.lookups) == sorted(process_lookups(
            field.lookup_categories, []
        ))

    def test_empty_process_lookups(self, ):
        """Test process_lookups with an empty list, it should return an empty list"""
        field = self.get_field(lookups=[])
        assert field.lookups == []

    def test_invalid_lookups(self, ):
        """Test process_lookups with an invalid list (list of int), it should raise an error"""
        with pytest.raises(AssertionError):
            self.get_field(lookups=[1, 2, 3])



class TestBooleanField(FieldBaseTest):
    field = BooleanField
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
    field = IntegerField
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
    field = FloatField
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
    field = StringField
    invalid_inputs = {}
    valid_inputs = {
        "foo": "foo",
        "1.1": "1.1",
    }


class TestDateTimeField(FieldBaseTest):
    field = DateTimeField
    invalid_inputs = {
        "foo": [
            "Datetime has wrong format. Use one of these formats instead: YYYY-MM-DDThh:mm[:ss[.uuuuuu]]["
            "+HH:MM|-HH:MM|Z]."
        ]
    }
    valid_inputs = {
        "2025-01-01T01:01:01+00:00": TEST_DATE_TIME,
    }



class TestTimeField(FieldBaseTest):
    field = TimeField
    invalid_inputs = {
        "foo": [
            "Time has wrong format. Use one of these formats instead: hh:mm[:ss[.uuuuuu]]."
        ]
    }
    valid_inputs = {
        "01:01:01": datetime.time(hour=1, minute=1, second=1),
    }


class TestDateField(FieldBaseTest):
    field = DateField
    invalid_inputs = {
        "foo": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]
    }
    valid_inputs = {
        "2025-01-01": datetime.date(year=2025, month=1, day=1),
    }



class TestDurationField(FieldBaseTest):
    field = DurationField
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
    field = EmailField
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
    field = DecimalField
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
    field = IPAddressField


class TestChoiceField(FieldBaseTest):
    valid_inputs = {"1": "1", "2": "2"}
    invalid_inputs = {"a": ['"a" is not a valid choice.']}
    field = ChoiceField
    field_kwargs = {"choices": [("1", "One"), ("2", "Two")]}


class TestMultipleChoiceField(FieldBaseTest):
    valid_inputs = {"1,2": {"1", "2"}}
    invalid_inputs = {"a": ['"a" is not a valid choice.']}
    field = MultipleChoiceField
    field_kwargs = {"choices": [("1", "One"), ("2", "Two")]}
    filter_lookup_suffix = "__in"


class BaseListFieldTest(FieldBaseTest):
    invalid_inputs = {1: ['Expected a list of items but got type "int".']}
    field = ListField
    filter_lookup_suffix = "__in"

    def test_invalid_inputs(self):
        """
        Ensure that invalid values raise the expected validation error.
        """
        field = self.get_field(filter_by="lookup")
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
            TEST_DATE_TIME,
            TEST_DATE_TIME_2,
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
def test_field_apply_filter_with_string_filter_by():
    """Test apply_filter with string filter_by"""
    from django.db.models import Q, QuerySet

    from tests.models import SampleModel

    field = IntegerField(filter_by="integer_field__gte")
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)
    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_returning_dict():
    """Test apply_filter with callable filter_by returning dict"""
    from django.db.models import Q

    from tests.models import SampleModel

    def lookup_func(value):
        return {"integer_field__gte": value}

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_returning_q():
    """Test apply_filter with callable filter_by returning Q object"""
    def lookup_func(value):
        return Q(integer_field__gte=value)

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)

    assert isinstance(q, Q)


@pytest.mark.django_db
def test_field_apply_filter_with_callable_filter_by_invalid_return():
    """Test apply_filter with callable filter_by returning invalid type"""
    def lookup_func(value):
        return "invalid"

    field = IntegerField(filter_by=lookup_func)
    qs = SampleModel.objects.all()

    with pytest.raises(AssertionError) as exc:
        field.apply_filter(None, qs, 10)
    assert "Invalid lookup expression" in str(exc.value)


@pytest.mark.django_db
def test_field_apply_filter_with_exclude():
    """Test apply_filter with negate=True"""
    field = IntegerField(filter_by="integer_field", negate=True)
    qs = SampleModel.objects.all()
    _result_qs, q = field.apply_filter(None, qs, 10)
    assert isinstance(q, Q)
    # Q object should be negated
    assert str(q).startswith("(NOT")


def test_field_str_and_repr():
    """Test __str__ and __repr__ methods"""
    field = IntegerField(filter_by="price__gte")
    field.field_name = "price"
    str_repr = str(field)
    assert "IntegerField" in str_repr
    assert "price" in str_repr
    assert repr(field) == str_repr


def test_order_field_process_fields():
    """Test OrderField.process_fields creates ascending and descending variants"""
    fields = [("price", "price"), ("name", "name")]
    result = OrderField.process_fields(fields)

    assert ("price", "price") in result
    assert ("-price", "-price") in result
    assert ("name", "name") in result
    assert ("-name", "-name") in result
    assert len(result) == 4


def test_order_field_process_labels():
    """Test OrderField.process_labels creates labels for variants"""
    labels = [("price", "Price"), ("name", "Name")]
    result = OrderField.process_labels(labels)

    assert ("price", "Price") in result
    assert ("-price", "Price") in result
    assert ("name", "Name") in result
    assert ("-name", "Name") in result


def test_order_field_process_labels_empty():
    """Test OrderField.process_labels with empty labels"""
    result = OrderField.process_labels(None)
    assert result == []


def test_order_field_process_choices():
    """Test OrderField.process_choices adds direction suffixes"""
    field = OrderField(fields=[("price", "price")])
    choices = field.process_choices([("price", "Price"), ("-price", "Price")])
    assert any("Ascending" in choice[1] for choice in choices)
    assert any("Descending" in choice[1] for choice in choices)


def test_order_field_process_choices_with_desc_override():
    """Test OrderField.process_choices with override_order_dir='desc'"""
    field = OrderField(fields=[("price", "price")], override_order_dir="desc")
    choices = field.process_choices([("price", "Price"), ("-price", "Price")])

    # With desc override, meanings should be reversed
    assert len(choices) == 2


@pytest.mark.django_db
def test_order_field_apply_filter():
    """Test OrderField.apply_filter orders the queryset"""
    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_descending():
    """Test OrderField.apply_filter with descending order"""

    field = OrderField(fields=[("integer_field", "integer_field")])
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["-integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


@pytest.mark.django_db
def test_order_field_apply_filter_with_override():
    """Test OrderField.apply_filter with override_order_dir"""
    field = OrderField(
        fields=[("integer_field", "integer_field")], override_order_dir="desc"
    )
    qs = SampleModel.objects.all()
    result_qs, _q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)


@pytest.mark.django_db
def test_order_field_apply_filter_with_method():
    """Test OrderField.apply_filter when method is provided"""
    def custom_order(request, queryset, value):
        return queryset.order_by(*value)

    field = OrderField(fields=[("integer_field", "integer_field")], method=custom_order)
    qs = SampleModel.objects.all()
    result_qs, q = field.apply_filter(None, qs, ["integer_field"])

    assert isinstance(result_qs, QuerySet)
    assert q is None


def test_list_field_to_internal_value_with_list():
    """Test ListField.to_internal_value with list input"""
    field = ListField(child=IntegerField())
    result = field.to_internal_value([1, 2, 3])
    assert result == [1, 2, 3]


def test_list_field_to_internal_value_with_string():
    """Test ListField.to_internal_value with comma-separated string"""
    field = ListField(child=IntegerField())
    result = field.to_internal_value("1,2,3")
    assert result == [1, 2, 3]


def test_list_field_to_internal_value_with_string_whitespace():
    """Test ListField.to_internal_value strips whitespace"""
    field = ListField(child=IntegerField())
    result = field.to_internal_value("1, 2, 3")
    assert result == [1, 2, 3]


def test_get_field_from_type_unsupported():
    """Test get_field_from_type with unsupported type raises AssertionError"""

    class UnsupportedType:
        pass

    with pytest.raises(AssertionError) as exc:
        get_field_from_type(UnsupportedType)
    assert "`annotations` must be in" in str(exc.value)


def test_get_field_from_type_with_literal():
    """Test get_field_from_type with Literal type"""
    from typing import Literal

    field = get_field_from_type(Literal["a", "b", "c"])
    assert isinstance(field, ChoiceField)
    assert len(field.choices) == 3


def test_get_field_from_type_with_optional():
    field = get_field_from_type(Optional[int])
    assert isinstance(field, IntegerField)


@pytest.mark.parametrize("dt", [None, Optional[None], Union[None], Union[NoneType]])
@pytest.mark.django_db
def test_get_field_from_type_with_optional_invalid(dt):
    """Test get_field_from_type with Optional[None] raises exception"""
    with pytest.raises(AssertionError):
        get_field_from_type(dt)


def test_get_field_from_type_with_list():
    """Test get_field_from_type with List type"""

    field = get_field_from_type(list[int], field_name="ids")
    assert isinstance(field, ListField)
    assert isinstance(field.child, IntegerField)
    assert field.filter_by == "ids__in"


def test_get_field_from_type_with_bare_list():
    """Test get_field_from_type with bare list type"""
    field = get_field_from_type(list, field_name="items")
    assert isinstance(field, ListField)
    assert isinstance(field.child, StringField)  # Defaults to str
    assert field.filter_by == "items__in"


def test_choice_field():
    """Test ChoiceField basic functionality"""
    field = ChoiceField(
        choices=[("a", "Option A"), ("b", "Option B")], filter_by="choice_field"
    )
    assert field.run_validation("a") == "a"


@pytest.mark.django_db
def test_multiple_choice_field():
    """Test MultipleChoiceField basic functionality"""
    field = MultipleChoiceField(
        choices=[("a", "Option A"), ("b", "Option B")], filter_by="choices"
    )
    result = field.run_validation(["a", "b"])
    assert sorted(result) == ["a", "b"]


def test_extract_model_fields_exclude_error_handle():
    # Exclude must be a list or tuple
    with pytest.raises(TypeError):
        extract_model_fields(model=None, fields="__all__", exclude=1)


def test_related_field():
    """Test RelatedField basic functionality"""
    field = RelatedField(model=SampleModel, fields=["name"], )
    assert "RelatedField" in str(field)
    assert field.model == SampleModel
    assert field.exclude == []
