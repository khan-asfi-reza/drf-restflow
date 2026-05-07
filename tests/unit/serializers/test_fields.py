import datetime
import decimal
import uuid
from typing import Any, Literal

import pytest
from rest_framework import fields as drf_fields

from restflow.serializers import (
    DecimalField,
    Email,
    Field,
    IPAddress,
    Serializer,
    SerializerFieldMap,
    get_field_from_type,
)


class TestSerializerFieldMap:
    @pytest.mark.parametrize(
        "data_type,expected_class",
        [
            (int, drf_fields.IntegerField),
            (float, drf_fields.FloatField),
            (str, drf_fields.CharField),
            (bool, drf_fields.BooleanField),
            (bytes, drf_fields.CharField),
            (datetime.datetime, drf_fields.DateTimeField),
            (datetime.date, drf_fields.DateField),
            (datetime.time, drf_fields.TimeField),
            (datetime.timedelta, drf_fields.DurationField),
            (decimal.Decimal, DecimalField),
            (uuid.UUID, drf_fields.UUIDField),
            (Email, drf_fields.EmailField),
            (IPAddress, drf_fields.IPAddressField),
            (dict, drf_fields.DictField),
            (Any, drf_fields.JSONField),
        ],
    )
    def test_map_resolves_to_expected_class(self, data_type, expected_class):
        field = get_field_from_type(data_type)
        assert isinstance(field, expected_class)

    def test_map_is_complete(self):
        for t, cls in SerializerFieldMap.items():
            field = get_field_from_type(t)
            assert isinstance(field, cls)


class TestLiteral:
    def test_literal_resolves_to_choice_field(self):
        field = get_field_from_type(Literal["a", "b", "c"])
        assert isinstance(field, drf_fields.ChoiceField)
        assert "a" in field.choices
        assert "b" in field.choices
        assert "c" in field.choices

    def test_literal_validates_choices(self):
        field = get_field_from_type(Literal["a", "b"])
        assert field.run_validation("a") == "a"
        with pytest.raises(Exception):
            field.run_validation("z")


class TestOptional:
    @pytest.mark.parametrize(
        "annotation",
        [str | None, int | None],
    )
    def test_t_or_none_unwraps_and_sets_allow_null(self, annotation):
        field = get_field_from_type(annotation)
        assert field.allow_null is True

    def test_optional_unwraps_and_sets_allow_null(self):
        from typing import Optional

        field = get_field_from_type(Optional[int])
        assert isinstance(field, drf_fields.IntegerField)
        assert field.allow_null is True

    def test_optional_literal(self):
        field = get_field_from_type(Literal["a", "b"] | None)
        assert isinstance(field, drf_fields.ChoiceField)
        assert field.allow_null is True

    def test_optional_list(self):
        field = get_field_from_type(list[str] | None)
        assert isinstance(field, drf_fields.ListField)
        assert field.allow_null is True

    def test_optional_nested_serializer(self):
        class Inner(Serializer):
            name: str

        field = get_field_from_type(Inner | None)
        assert isinstance(field, Inner)
        assert field.allow_null is True


class TestList:
    def test_bare_list(self):
        field = get_field_from_type(list)
        assert isinstance(field, drf_fields.ListField)

    def test_list_of_int(self):
        field = get_field_from_type(list[int])
        assert isinstance(field, drf_fields.ListField)
        assert isinstance(field.child, drf_fields.IntegerField)

    def test_nested_list_of_int(self):
        field = get_field_from_type(list[list[int]])
        assert isinstance(field, drf_fields.ListField)
        assert isinstance(field.child, drf_fields.ListField)
        assert isinstance(field.child.child, drf_fields.IntegerField)

    def test_three_deep_list(self):
        field = get_field_from_type(list[list[list[str]]])
        assert isinstance(field, drf_fields.ListField)
        assert isinstance(field.child, drf_fields.ListField)
        assert isinstance(field.child.child, drf_fields.ListField)
        assert isinstance(field.child.child.child, drf_fields.CharField)

    def test_list_of_serializer_uses_many(self):
        class Inner(Serializer):
            name: str

        field = get_field_from_type(list[Inner])
        # Inner(many=True) returns a ListSerializer
        from rest_framework.serializers import ListSerializer

        assert isinstance(field, ListSerializer)
        assert isinstance(field.child, Inner)


class TestNestedSerializer:
    def test_nested_serializer_instance(self):
        class Inner(Serializer):
            name: str

        field = get_field_from_type(Inner)
        assert isinstance(field, Inner)


class TestDecimalDefault:
    def test_decimal_default_max_digits_and_places(self):
        field = get_field_from_type(decimal.Decimal)
        assert isinstance(field, DecimalField)
        assert field.max_digits == 20
        assert field.decimal_places == 6

    def test_decimal_user_kwargs_override_defaults(self):
        field = get_field_from_type(
            decimal.Decimal, max_digits=5, decimal_places=2
        )
        assert field.max_digits == 5
        assert field.decimal_places == 2


class TestUnsupported:
    def test_unsupported_type_raises(self):
        class Custom:
            pass

        with pytest.raises(AssertionError, match="annotation"):
            get_field_from_type(Custom)


class TestFieldShim:
    def test_clone_with_type_routes_through_resolver(self):
        f = Field(write_only=True)
        cloned = f.clone(_type=int)
        assert isinstance(cloned, drf_fields.IntegerField)
        assert cloned.write_only is True

    def test_clone_without_type_preserves_class_and_kwargs(self):
        f = Field(write_only=True, required=False)
        cloned = f.clone()
        assert isinstance(cloned, Field)
        assert cloned.field_kwargs == {"write_only": True, "required": False}
