from decimal import Decimal
from typing import Literal

import pytest
from rest_framework import fields as drf_fields

from restflow.serializers import (
    Email,
    Field,
    InlineSerializer,
    ModelSerializer,
    Serializer,
)
from tests.models import Article, SampleModel, Tag


def test_serializer_with_basic_annotations():
    class UserSer(Serializer):
        name: str
        age: int
        email: Email

    s = UserSer(data={"name": "x", "age": 1, "email": "a@example.com"})
    assert s.is_valid()
    assert s.validated_data == {"name": "x", "age": 1, "email": "a@example.com"}


def test_serializer_field_classes_match_annotations():
    class S(Serializer):
        a: str
        b: int
        c: Email
        d: Literal["x", "y"]
        e: list[str]

    s = S()
    assert isinstance(s.fields["a"], drf_fields.CharField)
    assert isinstance(s.fields["b"], drf_fields.IntegerField)
    assert isinstance(s.fields["c"], drf_fields.EmailField)
    assert isinstance(s.fields["d"], drf_fields.ChoiceField)
    assert isinstance(s.fields["e"], drf_fields.ListField)


def test_optional_annotation_accepts_null():
    class S(Serializer):
        bio: str | None

    s = S(data={"bio": None})
    assert s.is_valid()
    assert s.validated_data == {"bio": None}


def test_field_sentinel_with_annotation_preserves_kwargs():
    class S(Serializer):
        secret: str = Field(write_only=True)

    s = S()
    assert isinstance(s.fields["secret"], drf_fields.CharField)
    assert s.fields["secret"].write_only is True


def test_nested_serializer_validates_recursively():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        inner: Inner

    s = Outer(data={"inner": {"name": "n"}})
    assert s.is_valid()
    assert s.validated_data == {"inner": {"name": "n"}}


def test_optional_nested_serializer_accepts_null():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        inner: Inner | None

    s = Outer(data={"inner": None})
    assert s.is_valid()
    assert s.validated_data == {"inner": None}


def test_list_of_nested_serializer():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        items: list[Inner]

    s = Outer(data={"items": [{"name": "a"}, {"name": "b"}]})
    assert s.is_valid()
    assert s.validated_data == {"items": [{"name": "a"}, {"name": "b"}]}


def test_arbitrarily_nested_lists():
    class S(Serializer):
        matrix: list[list[int]]
        cube: list[list[list[str]]]

    s = S(data={"matrix": [[1, 2], [3, 4]], "cube": [[["a"]], [["b", "c"]]]})
    assert s.is_valid()
    assert s.validated_data == {
        "matrix": [[1, 2], [3, 4]],
        "cube": [[["a"]], [["b", "c"]]],
    }


def test_decimal_annotation_uses_defaults():
    class S(Serializer):
        price: Decimal

    s = S(data={"price": "10.5"})
    assert s.is_valid()
    assert s.validated_data == {"price": Decimal("10.500000")}


def test_field_level_validate_method_runs():
    class S(Serializer):
        name: str

        def validate_name(self, value):
            return value.upper()

    s = S(data={"name": "lower"})
    assert s.is_valid()
    assert s.validated_data == {"name": "LOWER"}


def test_validate_top_level_runs():
    class S(Serializer):
        a: int
        b: int

        def validate(self, attrs):
            attrs["sum"] = attrs["a"] + attrs["b"]
            return attrs

    s = S(data={"a": 1, "b": 2})
    assert s.is_valid()
    assert s.validated_data == {"a": 1, "b": 2, "sum": 3}


def test_invalid_data_collects_errors():
    class S(Serializer):
        age: int
        email: Email

    s = S(data={"age": "not-int", "email": "not-email"})
    assert not s.is_valid()
    assert "age" in s.errors
    assert "email" in s.errors


def test_reserved_name_raises_at_class_creation():
    with pytest.raises(ValueError, match="data"):

        class S(Serializer):
            data: str


def test_explicit_drf_field_takes_precedence_over_annotation():
    class S(Serializer):
        name: int = drf_fields.CharField(default="hello")

    s = S()
    assert isinstance(s.fields["name"], drf_fields.CharField)
    assert s.fields["name"].default == "hello"


@pytest.mark.django_db
def test_serializer_save_calls_create_and_returns_instance():
    class S(Serializer):
        integer_field: int

        def create(self, validated_data):
            return SampleModel.objects.create(**validated_data)

    s = S(data={"integer_field": 42})
    assert s.is_valid()
    instance = s.save()
    assert instance.pk is not None
    assert instance.integer_field == 42


@pytest.mark.django_db
def test_serializer_save_calls_update():
    instance = SampleModel.objects.create(integer_field=1)

    class S(Serializer):
        integer_field: int

        def update(self, instance, validated_data):
            for k, v in validated_data.items():
                setattr(instance, k, v)
            instance.save()
            return instance

    s = S(instance=instance, data={"integer_field": 99})
    assert s.is_valid()
    s.save()
    instance.refresh_from_db()
    assert instance.integer_field == 99


def test_inheritance_combines_annotated_and_inherited_fields():
    class Base(Serializer):
        a: int

    class Child(Base):
        b: str

    s = Child(data={"a": 1, "b": "x"})
    assert s.is_valid()
    assert set(s.fields.keys()) == {"a", "b"}


@pytest.mark.django_db
class TestModelSerializer:
    def test_model_serializer_with_meta_only(self):
        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["id", "integer_field", "string_field"]

        instance = SampleModel.objects.create(
            integer_field=5, string_field="hello"
        )
        rep = S(instance).data
        assert rep["integer_field"] == 5
        assert rep["string_field"] == "hello"

    def test_model_serializer_with_annotation_auto_includes_in_meta_fields(self):
        class S(ModelSerializer):
            extra: str = Field(write_only=True)

            class Meta:
                model = SampleModel
                fields = ["id", "integer_field"]

        # extra was auto-appended to Meta.fields by the metaclass
        assert "extra" in S.Meta.fields
        s = S(data={"integer_field": 3, "extra": "secret"})
        assert s.is_valid()
        assert s.validated_data["extra"] == "secret"

    def test_model_serializer_with_annotation_only(self):
        class S(ModelSerializer):
            integer_field: int

            class Meta:
                model = SampleModel
                fields = ["integer_field"]

        s = S(data={"integer_field": 7})
        assert s.is_valid()
        # Annotation builds an IntegerField; assertion that it is _declared
        assert "integer_field" in S._declared_fields

    def test_model_serializer_save_creates_row(self):
        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["integer_field", "string_field"]

        s = S(data={"integer_field": 11, "string_field": "saved"})
        assert s.is_valid()
        instance = s.save()
        assert instance.pk is not None
        assert instance.integer_field == 11
        assert instance.string_field == "saved"


@pytest.mark.django_db(transaction=True)
class TestModelSerializerAsync:
    def test_default_acreate_persists_via_async_orm(self):
        import asyncio

        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["integer_field", "string_field"]

        async def run():
            s = S(data={"integer_field": 42, "string_field": "async"})
            assert await s.ais_valid()
            instance = await s.asave()
            assert instance.pk is not None
            assert instance.integer_field == 42
            assert instance.string_field == "async"
            assert await SampleModel.objects.filter(pk=instance.pk).aexists()

        asyncio.run(run())

    def test_default_aupdate_writes_through_async_orm(self):
        import asyncio

        class S(ModelSerializer):
            class Meta:
                model = SampleModel
                fields = ["integer_field", "string_field"]

        async def run():
            instance = await SampleModel.objects.acreate(
                integer_field=1, string_field="before"
            )
            s = S(instance, data={"integer_field": 9, "string_field": "after"})
            assert await s.ais_valid()
            updated = await s.asave()
            assert updated.pk == instance.pk
            await updated.arefresh_from_db()
            assert updated.integer_field == 9
            assert updated.string_field == "after"

        asyncio.run(run())

    def test_default_acreate_handles_many_to_many(self):
        import asyncio

        class S(ModelSerializer):
            class Meta:
                model = Article
                fields = ["title", "body", "tags"]

        async def run():
            red = await Tag.objects.acreate(name="red")
            blue = await Tag.objects.acreate(name="blue")
            instance = await S().acreate(
                {"title": "t", "body": "b", "tags": [red, blue]}
            )
            names = sorted(
                [t async for t in instance.tags.values_list("name", flat=True)]
            )
            assert names == ["blue", "red"]

        asyncio.run(run())

    def test_default_aupdate_replaces_many_to_many(self):
        import asyncio

        class S(ModelSerializer):
            class Meta:
                model = Article
                fields = ["title", "tags"]

        async def run():
            red = await Tag.objects.acreate(name="red")
            blue = await Tag.objects.acreate(name="blue")
            green = await Tag.objects.acreate(name="green")
            article = await Article.objects.acreate(title="t")
            await article.tags.aset([red, blue])

            await S().aupdate(article, {"title": "t2", "tags": [green]})
            await article.arefresh_from_db()
            assert article.title == "t2"
            names = [
                t async for t in article.tags.values_list("name", flat=True)
            ]
            assert names == ["green"]

        asyncio.run(run())


class TestInlineSerializer:
    def test_inline_with_field_dict(self):
        S = InlineSerializer(
            name="MyS", fields={"name": str, "age": int, "email": Email}
        )
        s = S(data={"name": "x", "age": 1, "email": "a@example.com"})
        assert s.is_valid()
        assert s.validated_data == {
            "name": "x",
            "age": 1,
            "email": "a@example.com",
        }
        assert S.__name__ == "MyS"

    def test_inline_with_explicit_drf_field(self):
        S = InlineSerializer(
            fields={"secret": drf_fields.CharField(write_only=True)}
        )
        s = S()
        assert s.fields["secret"].write_only is True

    @pytest.mark.django_db
    def test_inline_with_model(self):
        S = InlineSerializer(
            model=SampleModel,
            model_fields=["integer_field", "string_field"],
        )
        s = S(data={"integer_field": 1, "string_field": "y"})
        assert s.is_valid()
        instance = s.save()
        assert instance.integer_field == 1

    def test_inline_requires_model_or_fields(self):
        with pytest.raises(ValueError, match="model"):
            InlineSerializer()

    def test_inline_with_write_only_via_extra_kwargs(self):
        S = InlineSerializer(
            model=SampleModel,
            model_fields=["integer_field", "string_field"],
            write_only_fields=["string_field"],
        )
        s = S()
        assert s.fields["string_field"].write_only is True


def test_to_internal_value_raises_when_data_is_not_mapping():
    from rest_framework.exceptions import ValidationError

    class S(Serializer):
        name: str

    s = S(data="not a dict")
    with pytest.raises(ValidationError):
        s.is_valid(raise_exception=True)


def test_run_validation_wraps_django_validation_error():
    from django.core.exceptions import (
        ValidationError as DjangoValidationError,
    )
    from rest_framework.exceptions import ValidationError

    msg = "bad"

    class S(Serializer):
        name: str

        def validate(self, attrs):
            raise DjangoValidationError(msg)

    s = S(data={"name": "x"})
    with pytest.raises(ValidationError):
        s.is_valid(raise_exception=True)


def test_to_internal_value_field_django_validation_error_collected():
    from django.core.exceptions import (
        ValidationError as DjangoValidationError,
    )

    msg = "bad name"

    class S(Serializer):
        name: str

        def validate_name(self, value):
            raise DjangoValidationError(msg)

    s = S(data={"name": "x"})
    assert not s.is_valid()
    assert "name" in s.errors


def test_to_internal_value_field_skipfield_is_swallowed():
    from rest_framework.fields import SkipField

    class S(Serializer):
        name: str

        def validate_name(self, value):
            raise SkipField()

    s = S(data={"name": "x"})
    assert s.is_valid()
    assert "name" not in s.validated_data


def test_inheritance_dedup_does_not_duplicate_redeclared_field():
    class Base(Serializer):
        a: int
        b: int

    class Child(Base):
        a: str

    s = Child()
    assert isinstance(s.fields["a"], drf_fields.CharField)
    assert set(s.fields.keys()) == {"a", "b"}


def test_model_serializer_meta_with_no_fields_attr_is_left_alone():
    class S(ModelSerializer):
        extra: str = Field()

        class Meta:
            model = SampleModel

    assert not hasattr(S.Meta, "fields") or getattr(
        S.Meta, "fields", None
    ) is None


def test_model_serializer_subclass_without_own_meta_is_skipped():
    class Parent(ModelSerializer):
        class Meta:
            model = SampleModel
            fields = ["integer_field"]

    class Child(Parent):
        another: str = Field()

    assert "another" not in Child.Meta.fields


def test_model_serializer_meta_with_all_fields_is_left_alone():
    from rest_framework import serializers as drf_serializers

    class S(ModelSerializer):
        extra: str = Field()

        class Meta:
            model = SampleModel
            fields = drf_serializers.ALL_FIELDS

    assert S.Meta.fields == drf_serializers.ALL_FIELDS


def test_model_serializer_meta_with_set_fields_is_left_alone():
    class S(ModelSerializer):
        extra: str = Field()

        class Meta:
            model = SampleModel
            fields = {"integer_field"}

    assert S.Meta.fields == {"integer_field"}


def test_inline_with_read_only_fields_combined():
    S = InlineSerializer(
        model=SampleModel,
        model_fields=["integer_field", "string_field"],
        read_only_fields=["integer_field"],
    )
    s = S()
    assert s.fields["integer_field"].read_only is True
