import asyncio
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Optional, Union

import pytest
from rest_framework import fields as drf_fields
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError

from restflow.helpers import IPAddress
from restflow.serializers import (
    Email,
    Field,
    HyperlinkedModelSerializer,
    InlineSerializer,
    ModelSerializer,
    Serializer,
)
from restflow.serializers.fields import DecimalField as RFDecimal
from tests.models import Article, SampleModel, Tag


def _run(coro):
    return asyncio.run(coro)


def test_field_with_default_when_missing():
    class S(Serializer):
        name: str = Field(default="anon")

    s = S(data={})
    assert s.is_valid()
    assert s.validated_data == {"name": "anon"}


def test_field_with_required_false_skips_when_missing():
    class S(Serializer):
        name: str = Field(required=False)
        age: int

    s = S(data={"age": 1})
    assert s.is_valid()
    assert s.validated_data == {"age": 1}


def test_field_with_allow_null_alongside_optional_annotation():
    class S(Serializer):
        bio: str | None = Field()

    s = S(data={"bio": None})
    assert s.is_valid()
    assert s.validated_data == {"bio": None}


def test_field_overrides_max_length_for_charfield():
    class S(Serializer):
        name: str = Field(max_length=3)

    s = S(data={"name": "abcd"})
    assert not s.is_valid()
    assert "name" in s.errors


def test_field_min_value_for_int():
    class S(Serializer):
        age: int = Field(min_value=18)

    s = S(data={"age": 17})
    assert not s.is_valid()


def test_field_with_help_text_and_label_metadata():
    class S(Serializer):
        x: int = Field(help_text="hint", label="X")

    f = S().fields["x"]
    assert f.help_text == "hint"
    assert f.label == "X"


def test_field_with_initial_used_for_unbound_serializer():
    class S(Serializer):
        x: int = Field(initial=42)

    assert S().fields["x"].initial == 42


def test_field_with_validators_runs_them():
    def must_be_even(v):
        if v % 2:
            from rest_framework.exceptions import (
                ValidationError as DRFValidationError,
            )
            raise DRFValidationError("must be even")

    class S(Serializer):
        n: int = Field(validators=[must_be_even])

    assert not S(data={"n": 3}).is_valid()
    assert S(data={"n": 4}).is_valid()


def test_field_decimal_overrides_max_digits():
    class S(Serializer):
        price: Decimal = Field(max_digits=4, decimal_places=2)

    s = S(data={"price": "12.34"})
    assert s.is_valid()
    assert s.validated_data == {"price": Decimal("12.34")}
    assert not S(data={"price": "999.34"}).is_valid()


def test_field_decimal_default_via_field_sentinel_overrides_kwargs():
    class S(Serializer):
        price: Decimal = Field()

    f = S().fields["price"]
    assert isinstance(f, RFDecimal)
    assert f.max_digits == 20
    assert f.decimal_places == 6


def test_optional_decimal_with_field():
    class S(Serializer):
        price: Decimal | None = Field()

    s = S(data={"price": None})
    assert s.is_valid()
    assert s.validated_data == {"price": None}


def test_optional_literal_with_field():
    class S(Serializer):
        role: Optional[Literal["admin", "user"]] = Field()

    s = S(data={"role": None})
    assert s.is_valid()
    s2 = S(data={"role": "admin"})
    assert s2.is_valid()
    bad = S(data={"role": "foo"})
    assert not bad.is_valid()


def test_list_with_field_passes_kwargs_through():
    class S(Serializer):
        tags: list[str] = Field(allow_empty=False)

    s = S(data={"tags": []})
    assert not s.is_valid()


def test_list_of_optional_int():
    class S(Serializer):
        nums: list[int | None]

    s = S(data={"nums": [1, None, 3]})
    assert s.is_valid()
    assert s.validated_data == {"nums": [1, None, 3]}


def test_union_t_or_none_via_typing_union():
    class S(Serializer):
        x: Union[int, None]

    assert S(data={"x": None}).is_valid()
    assert S(data={"x": 5}).is_valid()


def test_all_primitive_annotations_at_once():
    class S(Serializer):
        i: int
        f: float
        s: str
        b: bool
        by: bytes
        dt: datetime
        d: date
        t: time
        td: timedelta
        dec: Decimal
        u: uuid.UUID
        em: Email
        ip: IPAddress
        m: dict
        a: Any

    payload = {
        "i": 1,
        "f": 1.5,
        "s": "hi",
        "b": True,
        "by": "x",
        "dt": "2024-01-01T00:00:00Z",
        "d": "2024-01-01",
        "t": "10:00:00",
        "td": "1 00:00:00",
        "dec": "1.0",
        "u": "00000000-0000-0000-0000-000000000000",
        "em": "a@b.com",
        "ip": "127.0.0.1",
        "m": {"k": 1},
        "a": [1, 2],
    }
    s = S(data=payload)
    assert s.is_valid(), s.errors


def test_explicit_drf_field_alongside_annotation_explicit_wins():
    class S(Serializer):
        a: int
        b: str = drf_fields.IntegerField(default=7)

    fields = S().fields
    assert isinstance(fields["a"], drf_fields.IntegerField)
    assert isinstance(fields["b"], drf_fields.IntegerField)


def test_explicit_drf_field_ordering_preserved_by_creation_counter():
    class S(Serializer):
        z = drf_fields.CharField(default="z")
        a = drf_fields.CharField(default="a")
        m = drf_fields.CharField(default="m")

    keys = list(S().fields.keys())
    assert keys == ["z", "a", "m"]


def test_field_sentinel_clone_method_returns_concrete_field():
    sentinel = Field(default=5)
    cloned = sentinel.clone(_type=int, field_name="x")
    assert isinstance(cloned, drf_fields.IntegerField)
    assert cloned.default == 5


def test_inheritance_chain_three_levels():
    class A(Serializer):
        a: int

    class B(A):
        b: str

    class C(B):
        c: bool

    s = C(data={"a": 1, "b": "x", "c": True})
    assert s.is_valid()
    assert set(s.fields) == {"a", "b", "c"}


def test_diamond_inheritance():
    class L(Serializer):
        x: int

    class M1(L):
        m1: str

    class M2(L):
        m2: str

    class D(M1, M2):
        d: bool

    s = D(data={"x": 1, "m1": "a", "m2": "b", "d": True})
    assert s.is_valid()
    assert set(s.fields) == {"x", "m1", "m2", "d"}


def test_field_redefined_in_subclass_via_field_sentinel_takes_over():
    class A(Serializer):
        x: int

    class B(A):
        x: int = Field(min_value=10)

    assert not B(data={"x": 1}).is_valid()
    assert B(data={"x": 100}).is_valid()


def test_async_validate_field_changes_value_then_top_validate_uses_new_value():
    seen = {}

    class S(Serializer):
        a: int

        async def validate_a(self, value):
            return value + 1

        async def validate(self, attrs):
            seen["a"] = attrs["a"]
            return attrs

    _run(S(data={"a": 5}).ais_valid())
    assert seen["a"] == 6


def test_validate_method_can_remove_field_via_skipfield():
    from rest_framework.fields import SkipField

    class S(Serializer):
        keep: str
        drop: str

        def validate_drop(self, value):
            raise SkipField()

    s = S(data={"keep": "k", "drop": "d"})
    assert s.is_valid()
    assert "drop" not in s.validated_data
    assert s.validated_data == {"keep": "k"}


def test_async_validate_method_can_skip_field():
    from rest_framework.fields import SkipField

    class S(Serializer):
        keep: str
        drop: str

        async def validate_drop(self, value):
            raise SkipField()

    s = S(data={"keep": "k", "drop": "d"})
    assert _run(s.ais_valid())
    assert "drop" not in s.validated_data


def test_validation_collects_multi_field_errors_at_once():
    class S(Serializer):
        a: int
        b: int
        c: Email

    s = S(data={"a": "x", "b": "y", "c": "no"})
    assert not s.is_valid()
    assert {"a", "b", "c"} <= set(s.errors.keys())


def test_async_validation_collects_multi_field_errors():
    class S(Serializer):
        a: int

        async def validate_a(self, value):
            raise ValidationError("fail-a")

    s = S(data={"a": 1})
    assert not _run(s.ais_valid())
    assert "a" in s.errors


def test_nested_partial_update_only_validates_provided():
    class Inner(Serializer):
        x: int
        y: int

    class Outer(Serializer):
        inner: Inner

    s = Outer(data={"inner": {"x": 1}}, partial=True)
    assert s.is_valid()


def test_list_field_default_min_max_length():
    class S(Serializer):
        tags: list[str] = Field(min_length=1, max_length=2)

    assert not S(data={"tags": []}).is_valid()
    assert not S(data={"tags": ["a", "b", "c"]}).is_valid()
    assert S(data={"tags": ["a"]}).is_valid()


def test_optional_list_accepts_null():
    class S(Serializer):
        tags: list[str] | None

    s = S(data={"tags": None})
    assert s.is_valid()


def test_to_representation_yields_values_for_typed_serializer():
    class S(Serializer):
        a: int
        b: str

    instance = type("I", (), {"a": 5, "b": "ok"})()
    s = S(instance)
    assert s.data == {"a": 5, "b": "ok"}


def test_async_to_representation_default_falls_back_to_sync_to_representation():
    class S(Serializer):
        a: int

    instance = type("I", (), {"a": 9})()
    rep = _run(S(instance).ato_representation(instance))
    assert rep == {"a": 9}


def test_typed_validated_data_indexable_like_dict():
    class S(Serializer):
        a: int
        b: str

    s = S(data={"a": 1, "b": "x"})
    assert s.is_valid()
    assert s.validated_data["a"] == 1
    assert s.validated_data["b"] == "x"


def test_typed_validated_data_raises_before_is_valid():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    with pytest.raises(AssertionError):
        _ = s.validated_data


@pytest.mark.django_db
class TestModelSerializerPermutations:
    def test_partial_update_skips_missing_fields(self):
        instance = SampleModel.objects.create(integer_field=1, string_field="a")

        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["integer_field", "string_field"]

        s = S(instance, data={"integer_field": 2}, partial=True)
        assert s.is_valid()
        s.save()
        instance.refresh_from_db()
        assert instance.integer_field == 2
        assert instance.string_field == "a"

    def test_extra_kwargs_via_meta_makes_field_read_only(self):
        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["integer_field", "string_field"]
                extra_kwargs = {"string_field": {"read_only": True}}

        s = S(data={"integer_field": 1, "string_field": "skip"})
        assert s.is_valid()
        assert "string_field" not in s.validated_data

    def test_annotation_overrides_model_field_in_modelserializer(self):
        class S(ModelSerializer):
            integer_field: str

            class Meta:
                model = SampleModel
                fields = ["integer_field"]

        f = S().fields["integer_field"]
        assert isinstance(f, drf_fields.CharField)

    def test_model_serializer_with_field_sentinel_kwargs(self):
        class S(ModelSerializer):
            note: str = Field(write_only=True, max_length=5)

            class Meta:
                model = SampleModel
                fields = ["integer_field"]

        f = S().fields["note"]
        assert f.write_only is True
        assert f.max_length == 5

    def test_async_create_persists_with_partial_data(self):
        async def run():
            class S(ModelSerializer):
                class Meta:
                    model = SampleModel
                    fields = ["integer_field", "string_field"]

            s = S(data={"integer_field": 11, "string_field": "p"})
            assert await s.ais_valid()
            instance = await s.asave()
            assert instance.integer_field == 11

        _run(run())

    def test_validation_error_on_invalid_choice(self):
        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["choice_field"]

        s = S(data={"choice_field": "z"})
        assert not s.is_valid()
        assert "choice_field" in s.errors


class TestInlineSerializerPermutations:
    def test_inline_with_drf_field_in_dict(self):
        S = InlineSerializer(
            fields={"x": drf_fields.IntegerField(min_value=0)}
        )
        assert not S(data={"x": -1}).is_valid()
        assert S(data={"x": 5}).is_valid()

    def test_inline_with_mixed_types_and_explicit(self):
        S = InlineSerializer(
            fields={
                "name": str,
                "explicit": drf_fields.CharField(max_length=2),
            }
        )
        assert not S(data={"name": "x", "explicit": "abc"}).is_valid()

    @pytest.mark.django_db
    def test_inline_model_with_extra_kwargs(self):
        S = InlineSerializer(
            model=SampleModel,
            model_fields=["integer_field", "string_field"],
            extra_kwargs={"integer_field": {"min_value": 0}},
        )
        assert not S(data={"integer_field": -1, "string_field": "x"}).is_valid()

    @pytest.mark.django_db
    def test_inline_model_default_fields_all(self):
        S = InlineSerializer(model=SampleModel)
        assert "integer_field" in S().fields

    def test_inline_uses_default_class_name(self):
        S = InlineSerializer(fields={"x": int})
        assert S.__name__ == "_Serializer"

    @pytest.mark.django_db
    def test_inline_model_named_class(self):
        S = InlineSerializer(name="Foo", model=SampleModel)
        assert S.__name__ == "Foo"

    @pytest.mark.django_db
    def test_inline_model_default_class_name_is_model_serializer(self):
        S = InlineSerializer(model=SampleModel)
        assert S.__name__ == f"{SampleModel.__name__}Serializer"


@pytest.mark.django_db
class TestHyperlinkedModelSerializer:
    def test_hyperlinked_with_meta(self):
        class S(HyperlinkedModelSerializer):
            class Meta:
                model = Tag
                fields = ["name"]

        instance = Tag.objects.create(name="x")
        rep = S(instance, context={"request": None}).data
        assert rep["name"] == "x"


def test_field_default_callable():
    class S(Serializer):
        x: int = Field(default=lambda: 99)

    s = S(data={})
    assert s.is_valid()
    assert s.validated_data == {"x": 99}


def test_field_required_true_explicitly():
    class S(Serializer):
        x: int = Field(required=True)

    s = S(data={})
    assert not s.is_valid()
    assert "x" in s.errors


def test_validate_returns_none_triggers_assertion_through_validation_error():
    class S(Serializer):
        a: int

        def validate(self, attrs):
            return None

    with pytest.raises(AssertionError):
        S(data={"a": 1}).is_valid(raise_exception=True)


def test_async_validate_returns_none_triggers_assertion():
    class S(Serializer):
        a: int

        async def validate(self, attrs):
            return None

    with pytest.raises(AssertionError):
        _run(S(data={"a": 1}).ais_valid(raise_exception=True))


def test_save_with_kwargs_merged_into_validated_data():
    class S(Serializer):
        x: int

        def create(self, validated_data):
            return type("I", (), validated_data)()

    s = S(data={"x": 1})
    assert s.is_valid()
    instance = s.save(extra="stamp")
    assert instance.extra == "stamp"
    assert instance.x == 1


def test_asave_with_kwargs_merged_into_validated_data():
    class S(Serializer):
        x: int

        async def acreate(self, validated_data):
            return type("I", (), validated_data)()

    async def run():
        s = S(data={"x": 1})
        await s.ais_valid()
        instance = await s.asave(extra="stamp")
        assert instance.extra == "stamp"

    _run(run())


def test_save_rejects_commit_kwarg():
    class S(Serializer):
        x: int

        def create(self, validated_data):
            return object()

    s = S(data={"x": 1})
    s.is_valid()
    with pytest.raises(AssertionError):
        s.save(commit=False)


def test_asave_rejects_commit_kwarg():
    class S(Serializer):
        x: int

        async def acreate(self, validated_data):
            return object()

    async def run():
        s = S(data={"x": 1})
        await s.ais_valid()
        with pytest.raises(AssertionError):
            await s.asave(commit=False)

    _run(run())


def test_save_after_data_access_raises():
    class S(Serializer):
        x: int

        def create(self, validated_data):
            return type("I", (), validated_data)()

    s = S(data={"x": 1})
    s.is_valid()
    _ = s.data
    with pytest.raises(AssertionError):
        s.save()


def test_serializer_many_true_returns_list_serializer():
    class S(Serializer):
        x: int

    instances = [type("I", (), {"x": i})() for i in range(3)]
    rep = S(instances, many=True).data
    assert rep == [{"x": 0}, {"x": 1}, {"x": 2}]


def test_field_with_source_translates_input_to_output_path():
    class S(Serializer):
        display_name: str = Field(source="name")

    instance = type("I", (), {"name": "alice"})()
    assert S(instance).data == {"display_name": "alice"}


def test_optional_nested_serializer_in_list():
    class Inner(Serializer):
        n: int

    class Outer(Serializer):
        rows: list[Inner | None]

    s = Outer(data={"rows": [{"n": 1}, None, {"n": 2}]})
    assert s.is_valid()


def test_unsupported_annotation_type_raises():
    class Custom:
        pass

    with pytest.raises(AssertionError):
        class S(Serializer):
            x: Custom


def test_drf_field_explicit_with_typed_field_sentinel_in_same_class():
    class S(Serializer):
        a = drf_fields.IntegerField(default=1)
        b: str = Field(default="x")

    assert S(data={}).is_valid()


def test_field_with_only_kwargs_then_passed_to_concrete_field():
    class S(Serializer):
        s: str = Field(allow_blank=True)

    assert S(data={"s": ""}).is_valid()


def test_invalid_inline_choice_in_literal_collects_error():
    class S(Serializer):
        role: Literal["admin", "user"]

    s = S(data={"role": "ghost"})
    assert not s.is_valid()
    assert "role" in s.errors
