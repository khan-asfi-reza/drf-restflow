import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

import pytest
from rest_framework import fields as drf_fields
from rest_framework.exceptions import ValidationError

from restflow.helpers import IPAddress
from restflow.serializers import Email, Field, NotRequired, Serializer


class TestIntegerFieldKwargs:
    def test_int_with_min_value(self):
        class S(Serializer):
            n: int = Field(min_value=10)

        assert not S(data={"n": 5}).is_valid()
        assert S(data={"n": 10}).is_valid()
        assert S(data={"n": 100}).is_valid()

    def test_int_with_max_value(self):
        class S(Serializer):
            n: int = Field(max_value=10)

        assert S(data={"n": 5}).is_valid()
        assert S(data={"n": 10}).is_valid()
        assert not S(data={"n": 11}).is_valid()

    def test_int_with_min_and_max(self):
        class S(Serializer):
            n: int = Field(min_value=1, max_value=100)

        assert not S(data={"n": 0}).is_valid()
        assert S(data={"n": 50}).is_valid()
        assert not S(data={"n": 101}).is_valid()

    def test_int_with_required_false_and_default(self):
        class S(Serializer):
            n: int = Field(required=False, default=42)

        s = S(data={})
        assert s.is_valid()
        assert s.validated_data == {"n": 42}

    def test_int_with_write_only_excludes_from_output(self):
        class S(Serializer):
            n: int = Field(write_only=True)

        instance = type("I", (), {"n": 5})()
        assert "n" not in S(instance).data

    def test_int_with_read_only_skips_input(self):
        class S(Serializer):
            n: int = Field(read_only=True)

        s = S(data={"n": 5})
        assert s.is_valid()
        assert "n" not in s.validated_data

    def test_int_with_help_text_and_label(self):
        class S(Serializer):
            n: int = Field(help_text="hint", label="N")

        f = S().fields["n"]
        assert f.help_text == "hint"
        assert f.label == "N"

    def test_int_with_source_attribute(self):
        class S(Serializer):
            count: int = Field(source="total")

        instance = type("I", (), {"total": 99})()
        assert S(instance).data == {"count": 99}

    def test_int_with_validators_runs_them(self):
        def must_be_even(v):
            if v % 2:
                raise ValidationError("must be even")

        class S(Serializer):
            n: int = Field(validators=[must_be_even])

        assert not S(data={"n": 3}).is_valid()
        assert S(data={"n": 4}).is_valid()


class TestFloatFieldKwargs:
    def test_float_with_min_value(self):
        class S(Serializer):
            n: float = Field(min_value=0.5)

        assert not S(data={"n": 0.4}).is_valid()
        assert S(data={"n": 0.5}).is_valid()

    def test_float_with_max_value(self):
        class S(Serializer):
            n: float = Field(max_value=1.0)

        assert not S(data={"n": 1.1}).is_valid()
        assert S(data={"n": 0.9}).is_valid()

    def test_float_default_when_missing(self):
        class S(Serializer):
            n: float = Field(default=1.5)

        s = S(data={})
        assert s.is_valid()
        assert s.validated_data == {"n": 1.5}


class TestCharFieldKwargs:
    def test_str_with_max_length(self):
        class S(Serializer):
            name: str = Field(max_length=5)

        assert S(data={"name": "abcde"}).is_valid()
        assert not S(data={"name": "abcdef"}).is_valid()

    def test_str_with_min_length(self):
        class S(Serializer):
            name: str = Field(min_length=3)

        assert not S(data={"name": "ab"}).is_valid()
        assert S(data={"name": "abc"}).is_valid()

    def test_str_with_min_and_max_length(self):
        class S(Serializer):
            name: str = Field(min_length=2, max_length=4)

        assert not S(data={"name": "a"}).is_valid()
        assert S(data={"name": "abc"}).is_valid()
        assert not S(data={"name": "abcde"}).is_valid()

    def test_str_with_allow_blank_true(self):
        class S(Serializer):
            name: str = Field(allow_blank=True)

        assert S(data={"name": ""}).is_valid()

    def test_str_with_allow_blank_false_rejects_empty(self):
        class S(Serializer):
            name: str = Field(allow_blank=False)

        assert not S(data={"name": ""}).is_valid()

    def test_str_with_trim_whitespace_strips_input(self):
        class S(Serializer):
            name: str = Field(trim_whitespace=True)

        s = S(data={"name": "  hi  "})
        assert s.is_valid()
        assert s.validated_data == {"name": "hi"}

    def test_str_with_trim_whitespace_false_keeps_padding(self):
        class S(Serializer):
            name: str = Field(trim_whitespace=False)

        s = S(data={"name": "  hi  "})
        assert s.is_valid()
        assert s.validated_data == {"name": "  hi  "}

    def test_str_write_only_password(self):
        class S(Serializer):
            password: str = Field(write_only=True, min_length=8)

        instance = type("I", (), {"password": "secret"})()
        assert "password" not in S(instance).data
        assert not S(data={"password": "tiny"}).is_valid()
        assert S(data={"password": "longenough"}).is_valid()

    def test_str_read_only_with_default(self):
        class S(Serializer):
            tag: str = Field(read_only=True, default="x")

        f = S().fields["tag"]
        assert f.read_only is True


class TestBooleanFieldKwargs:
    def test_bool_required_false_with_default(self):
        class S(Serializer):
            flag: bool = Field(required=False, default=False)

        s = S(data={})
        assert s.is_valid()
        assert s.validated_data == {"flag": False}

    def test_bool_write_only(self):
        class S(Serializer):
            consent: bool = Field(write_only=True)

        instance = type("I", (), {"consent": True})()
        assert "consent" not in S(instance).data

    def test_bool_optional_accepts_null(self):
        class S(Serializer):
            flag: bool | None = Field()

        s = S(data={"flag": None})
        assert s.is_valid()


class TestBytesFieldKwargs:
    def test_bytes_with_max_length(self):
        class S(Serializer):
            payload: bytes = Field(max_length=4)

        assert not S(data={"payload": "abcde"}).is_valid()
        assert S(data={"payload": "abc"}).is_valid()


class TestDateTimeFieldKwargs:
    def test_datetime_with_format_and_input_formats(self):
        class S(Serializer):
            at: datetime = Field(input_formats=["%Y/%m/%d %H:%M"])

        s = S(data={"at": "2024/01/02 10:30"})
        assert s.is_valid()
        assert s.validated_data["at"].year == 2024

    def test_datetime_invalid_format_rejected(self):
        class S(Serializer):
            at: datetime = Field(input_formats=["%Y-%m-%d"])

        assert not S(data={"at": "not-a-date"}).is_valid()

    def test_datetime_default_timezone(self):
        class S(Serializer):
            at: datetime = Field(default_timezone=timezone.utc)

        s = S(data={"at": "2024-01-01T12:00:00"})
        assert s.is_valid()


class TestDateFieldKwargs:
    def test_date_with_input_formats(self):
        class S(Serializer):
            d: date = Field(input_formats=["%d/%m/%Y"])

        s = S(data={"d": "31/12/2024"})
        assert s.is_valid()
        assert s.validated_data["d"] == date(2024, 12, 31)


class TestTimeFieldKwargs:
    def test_time_with_input_formats(self):
        class S(Serializer):
            t: time = Field(input_formats=["%H:%M"])

        s = S(data={"t": "10:30"})
        assert s.is_valid()
        assert s.validated_data["t"] == time(10, 30)


class TestDurationFieldKwargs:
    def test_duration_with_min_value(self):
        class S(Serializer):
            d: timedelta = Field(min_value=timedelta(seconds=10))

        assert not S(data={"d": "00:00:05"}).is_valid()
        assert S(data={"d": "00:00:30"}).is_valid()

    def test_duration_with_max_value(self):
        class S(Serializer):
            d: timedelta = Field(max_value=timedelta(hours=1))

        assert not S(data={"d": "02:00:00"}).is_valid()
        assert S(data={"d": "00:30:00"}).is_valid()


class TestDecimalFieldKwargs:
    def test_decimal_with_max_digits_and_places(self):
        class S(Serializer):
            price: Decimal = Field(max_digits=4, decimal_places=2)

        assert not S(data={"price": "100.00"}).is_valid()
        assert S(data={"price": "99.99"}).is_valid()

    def test_decimal_with_min_value(self):
        class S(Serializer):
            price: Decimal = Field(
                max_digits=10, decimal_places=2, min_value=Decimal("0")
            )

        assert not S(data={"price": "-1.00"}).is_valid()
        assert S(data={"price": "0.01"}).is_valid()

    def test_decimal_with_max_value(self):
        class S(Serializer):
            price: Decimal = Field(
                max_digits=10, decimal_places=2, max_value=Decimal("100")
            )

        assert not S(data={"price": "100.01"}).is_valid()
        assert S(data={"price": "99.99"}).is_valid()

    def test_decimal_coerce_to_string_false_returns_decimal(self):
        class S(Serializer):
            price: Decimal = Field(
                max_digits=10, decimal_places=2, coerce_to_string=False
            )

        instance = type("I", (), {"price": Decimal("1.5")})()
        assert isinstance(S(instance).data["price"], Decimal)

    def test_decimal_default_with_field_overrides(self):
        class S(Serializer):
            price: Decimal = Field(max_digits=3, decimal_places=1)

        f = S().fields["price"]
        assert f.max_digits == 3
        assert f.decimal_places == 1


class TestUUIDFieldKwargs:
    def test_uuid_with_format_hex(self):
        u = uuid.UUID("12345678-1234-5678-1234-567812345678")

        class S(Serializer):
            id: uuid.UUID = Field(format="hex")

        instance = type("I", (), {"id": u})()
        rep = S(instance).data
        assert "-" not in rep["id"]

    def test_uuid_input_accepts_dashed(self):
        class S(Serializer):
            id: uuid.UUID = Field()

        s = S(data={"id": "12345678-1234-5678-1234-567812345678"})
        assert s.is_valid()


class TestEmailFieldKwargs:
    def test_email_with_max_length(self):
        class S(Serializer):
            addr: Email = Field(max_length=20)

        assert not S(data={"addr": "verylongemail@example.com"}).is_valid()
        assert S(data={"addr": "a@b.com"}).is_valid()

    def test_email_with_allow_blank(self):
        class S(Serializer):
            addr: Email = Field(allow_blank=True)

        assert S(data={"addr": ""}).is_valid()

    def test_email_invalid_format_rejected(self):
        class S(Serializer):
            addr: Email = Field()

        assert not S(data={"addr": "not-an-email"}).is_valid()


class TestIPAddressFieldKwargs:
    def test_ipaddress_protocol_ipv4(self):
        class S(Serializer):
            ip: IPAddress = Field(protocol="ipv4")

        assert S(data={"ip": "127.0.0.1"}).is_valid()
        assert not S(data={"ip": "::1"}).is_valid()

    def test_ipaddress_protocol_ipv6(self):
        class S(Serializer):
            ip: IPAddress = Field(protocol="ipv6")

        assert S(data={"ip": "::1"}).is_valid()
        assert not S(data={"ip": "127.0.0.1"}).is_valid()

    def test_ipaddress_protocol_both(self):
        class S(Serializer):
            ip: IPAddress = Field(protocol="both")

        assert S(data={"ip": "127.0.0.1"}).is_valid()
        assert S(data={"ip": "::1"}).is_valid()


class TestDictFieldKwargs:
    def test_dict_field_with_typed_child(self):
        class S(Serializer):
            counts: dict = Field(child=drf_fields.IntegerField())

        assert S(data={"counts": {"a": 1, "b": 2}}).is_valid()
        assert not S(data={"counts": {"a": "x"}}).is_valid()


class TestJSONFieldKwargs:
    def test_any_field_accepts_arbitrary_payload(self):
        class S(Serializer):
            payload: Any = Field()

        assert S(data={"payload": {"k": [1, 2, {"x": True}]}}).is_valid()
        assert S(data={"payload": [1, 2, 3]}).is_valid()

    def test_any_field_with_binary(self):
        class S(Serializer):
            payload: Any = Field(binary=True)

        f = S().fields["payload"]
        assert f.binary is True


class TestListFieldKwargs:
    def test_list_with_min_length(self):
        class S(Serializer):
            tags: list[str] = Field(min_length=2)

        assert not S(data={"tags": ["a"]}).is_valid()
        assert S(data={"tags": ["a", "b"]}).is_valid()

    def test_list_with_max_length(self):
        class S(Serializer):
            tags: list[str] = Field(max_length=2)

        assert S(data={"tags": ["a", "b"]}).is_valid()
        assert not S(data={"tags": ["a", "b", "c"]}).is_valid()

    def test_list_with_allow_empty_false(self):
        class S(Serializer):
            tags: list[str] = Field(allow_empty=False)

        assert not S(data={"tags": []}).is_valid()
        assert S(data={"tags": ["a"]}).is_valid()

    def test_list_with_allow_empty_true_default(self):
        class S(Serializer):
            tags: list[str] = Field()

        assert S(data={"tags": []}).is_valid()


class TestLiteralFieldKwargs:
    def test_literal_with_field_kwargs_required_false(self):
        class S(Serializer):
            role: Literal["admin", "user"] = Field(
                required=False, default="user"
            )

        s = S(data={})
        assert s.is_valid()
        assert s.validated_data == {"role": "user"}

    def test_literal_with_field_invalid_choice(self):
        class S(Serializer):
            role: Literal["admin", "user"] = Field()

        assert not S(data={"role": "ghost"}).is_valid()

    def test_literal_write_only(self):
        class S(Serializer):
            role: Literal["a", "b"] = Field(write_only=True)

        instance = type("I", (), {"role": "a"})()
        assert "role" not in S(instance).data


class TestOptionalKwargs:
    def test_optional_int_with_default_none(self):
        class S(Serializer):
            n: int | None = Field(required=False, default=None)

        s = S(data={})
        assert s.is_valid()
        assert s.validated_data == {"n": None}

    def test_optional_str_with_max_length(self):
        class S(Serializer):
            note: str | None = Field(max_length=5)

        assert S(data={"note": None}).is_valid()
        assert S(data={"note": "abc"}).is_valid()
        assert not S(data={"note": "abcdef"}).is_valid()

    def test_optional_decimal_with_constraints(self):
        class S(Serializer):
            price: Decimal | None = Field(
                max_digits=5, decimal_places=2, min_value=Decimal("0")
            )

        assert S(data={"price": None}).is_valid()
        assert S(data={"price": "1.23"}).is_valid()
        assert not S(data={"price": "-1.00"}).is_valid()

    def test_optional_list_with_constraints(self):
        class S(Serializer):
            tags: list[str] | None = Field(min_length=1, max_length=3)

        assert S(data={"tags": None}).is_valid()
        assert not S(data={"tags": []}).is_valid()
        assert S(data={"tags": ["a", "b"]}).is_valid()


class TestNotRequiredKwargs:
    def test_not_required_str_is_optional_but_not_nullable(self):
        class S(Serializer):
            nick: NotRequired[str]

        f = S().fields["nick"]
        assert f.required is False
        assert f.allow_null is False

    def test_not_required_omitting_key_validates(self):
        class S(Serializer):
            nick: NotRequired[str]

        assert S(data={}).is_valid()

    def test_not_required_rejects_null_when_not_optional(self):
        class S(Serializer):
            nick: NotRequired[str]

        assert not S(data={"nick": None}).is_valid()

    def test_not_required_optional_allows_null(self):
        class S(Serializer):
            bio: NotRequired[str | None]

        f = S().fields["bio"]
        assert f.required is False
        assert f.allow_null is True
        assert S(data={"bio": None}).is_valid()

    def test_not_required_list(self):
        class S(Serializer):
            tags: NotRequired[list[str]]

        f = S().fields["tags"]
        assert isinstance(f, drf_fields.ListField)
        assert f.required is False
        assert S(data={}).is_valid()

    def test_not_required_with_field_kwargs(self):
        class S(Serializer):
            secret: NotRequired[str] = Field(write_only=True, min_length=4)

        f = S().fields["secret"]
        assert f.required is False
        assert f.write_only is True
        assert not S(data={"secret": "ab"}).is_valid()
        assert S(data={"secret": "abcd"}).is_valid()

    def test_explicit_required_true_overrides_not_required(self):
        class S(Serializer):
            x: NotRequired[str] = Field(required=True)

        f = S().fields["x"]
        assert f.required is True
        assert not S(data={}).is_valid()


class TestCombinedKwargs:
    def test_int_required_default_help_label_validators(self):
        def positive(v):
            if v < 0:
                raise ValidationError("negative")

        class S(Serializer):
            score: int = Field(
                required=False,
                default=0,
                help_text="Score from 0 to 100",
                label="Score",
                min_value=0,
                max_value=100,
                validators=[positive],
            )

        assert S(data={}).is_valid()
        assert not S(data={"score": -1}).is_valid()
        assert not S(data={"score": 101}).is_valid()
        assert S(data={"score": 50}).is_valid()

    def test_str_full_kwarg_combo(self):
        class S(Serializer):
            username: str = Field(
                min_length=3,
                max_length=10,
                allow_blank=False,
                trim_whitespace=True,
                help_text="username",
                label="User",
            )

        assert not S(data={"username": "ab"}).is_valid()
        assert S(data={"username": "  abc  "}).is_valid()
        assert not S(data={"username": "x" * 11}).is_valid()

    def test_decimal_full_kwarg_combo(self):
        class S(Serializer):
            price: Decimal = Field(
                max_digits=8,
                decimal_places=2,
                min_value=Decimal("0.01"),
                max_value=Decimal("9999.99"),
                coerce_to_string=False,
            )

        assert not S(data={"price": "0.00"}).is_valid()
        assert not S(data={"price": "10000.00"}).is_valid()
        assert S(data={"price": "100.50"}).is_valid()

    def test_email_full_kwarg_combo(self):
        class S(Serializer):
            addr: Email = Field(
                max_length=50,
                min_length=5,
                allow_blank=False,
                required=True,
                help_text="email",
            )

        assert not S(data={"addr": "x@y"}).is_valid()
        assert S(data={"addr": "khan@example.com"}).is_valid()

    def test_optional_email_with_kwargs(self):
        class S(Serializer):
            addr: Email | None = Field(max_length=20, required=False)

        assert S(data={}).is_valid()
        assert S(data={"addr": None}).is_valid()
        assert S(data={"addr": "a@b.com"}).is_valid()

    def test_list_of_int_with_kwargs_on_outer(self):
        class S(Serializer):
            ns: list[int] = Field(min_length=1, max_length=5)

        assert not S(data={"ns": []}).is_valid()
        assert S(data={"ns": [1, 2, 3]}).is_valid()
        assert not S(data={"ns": list(range(10))}).is_valid()

    def test_field_default_callable_resolves_per_call(self):
        counter = {"n": 0}

        def gen():
            counter["n"] += 1
            return counter["n"]

        class S(Serializer):
            seq: int = Field(default=gen)

        s1 = S(data={})
        s1.is_valid()
        assert s1.validated_data == {"seq": 1}
        s2 = S(data={})
        s2.is_valid()
        assert s2.validated_data == {"seq": 2}

    def test_field_with_initial_for_form_rendering(self):
        class S(Serializer):
            n: int = Field(initial=99)

        assert S().fields["n"].initial == 99


class TestFieldKwargsViaInheritance:
    def test_subclass_can_redefine_field_kwargs(self):
        class Base(Serializer):
            name: str = Field(max_length=10)

        class Child(Base):
            name: str = Field(max_length=3)

        assert Child(data={"name": "abcd"}).is_valid() is False
        assert Child(data={"name": "ab"}).is_valid()

    def test_inherited_field_kwargs_persist_when_not_redefined(self):
        class Base(Serializer):
            name: str = Field(max_length=3)

        class Child(Base):
            extra: int

        assert not Child(data={"name": "abcd", "extra": 1}).is_valid()
        assert Child(data={"name": "ab", "extra": 1}).is_valid()


class TestFieldExplicitDRFFieldFallback:
    def test_explicit_drf_field_overrides_annotation(self):
        class S(Serializer):
            n: int = drf_fields.CharField(max_length=4)

        assert S(data={"n": "abcd"}).is_valid()
        assert not S(data={"n": "abcde"}).is_valid()

    def test_explicit_drf_field_with_validators(self):
        class S(Serializer):
            tag = drf_fields.CharField(min_length=2, max_length=4)

        assert not S(data={"tag": "a"}).is_valid()
        assert S(data={"tag": "abc"}).is_valid()
        assert not S(data={"tag": "abcde"}).is_valid()
