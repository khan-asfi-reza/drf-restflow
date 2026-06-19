import datetime
import decimal
from typing import Literal, Optional

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.http import QueryDict
from rest_framework.test import APIRequestFactory

from restflow.filters.fields import (
    BooleanField,
    Email,
    Field,
    IntegerField,
    IPAddress,
    ListField,
    MultipleChoiceField,
    OrderField,
    RelatedField,
    StringField,
)
from restflow.filters.filters import (
    FilterSet,
    InlineFilterSet,
    getattr_multi_source,
)
from tests.models import SampleAbstractModel, SampleModel


def test_filterset_annotation_fields():
    class ExampleFilterSet(FilterSet):
        field_1: int
        field_2: float
        field_3: str
        field_4: bool
        field_5: datetime.datetime
        field_6: datetime.date
        field_7: datetime.time
        field_8: datetime.timedelta
        field_9: decimal.Decimal
        field_10: Email
        field_11: IPAddress
        field_12: list[int]
        field_13: list[float]
        field_14: list[str]
        field_15: list[bool]
        field_16: list[datetime.datetime]
        field_17: list[datetime.date]
        field_18: list[datetime.time]
        field_19: list[datetime.timedelta]
        field_20: list[decimal.Decimal]
        field_21: list[Email]
        field_22: list[IPAddress]
        field_23: list[int]
        field_24: list[float]
        field_25: list[str]
        field_26: list[bool]
        field_27: list[datetime.datetime]
        field_28: list[datetime.date]
        field_29: list[datetime.time]
        field_30: list[datetime.timedelta]
        field_31: list[decimal.Decimal]
        field_32: list[Email]
        field_33: list[IPAddress]
        field_34: Literal["a", "b"]
        field_35: list
        field_36: list
        field_37: Optional[int]
        field_38: Optional[float]
        field_39: Optional[str]
        field_40: Optional[bool]
        field_41: int | None
        field_42: float | None
        field_43: str | None
        field_44: bool | None
        field_45: datetime.datetime | None
        field_46: datetime.date | None
        field_47: datetime.time | None
        field_48: datetime.timedelta | None
        field_49: decimal.Decimal | None
        field_50: Email | None
        field_51: IPAddress | None
        field_52: int = Field()
        field_53: float = Field()
        field_54: str = Field()
        field_55: bool = Field()
        field_56: datetime.datetime = Field()
        field_57: datetime.date = Field()
        field_58: datetime.time = Field()
        field_59: datetime.timedelta = Field()
        field_60: decimal.Decimal = Field()
        field_61: Email = Field()
        field_62: IPAddress = Field()


        class Meta:
            operator = "OR"

    filterset = ExampleFilterSet()
    fields = filterset.fields

    assert len(fields) == 62 * 2
    for _field_name, field in fields.items():
        assert isinstance(field, Field)
        assert not field.required


def test_filterset_inheritance():

    class ParentFilterSet(FilterSet):
        field_1: int
        field_2: str

    class ChildFilterSet(ParentFilterSet):
        field_3: bool

    fields = ChildFilterSet().fields
    assert "field_1" in fields
    assert "field_2" in fields
    assert "field_3" in fields


def test_filter_options_invalid_operator():
    with pytest.raises(ValueError) as exc:

        class InvalidFilterSet(FilterSet):
            field: int

            class Meta:
                operator = "INVALID"

    assert "Operator must be one of AND, OR, XOR" in str(exc.value)


def test_filterset_with_model_all_fields():

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = "__all__"

    filterset = TestFilterSet()
    assert "integer_field" in filterset.fields
    assert "string_field" in filterset.fields
    assert "boolean_field" in filterset.fields


def test_filterset_with_model_specific_fields():

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = ["integer_field", "string_field"]

    filterset = TestFilterSet()
    assert "integer_field" in filterset.fields
    assert "string_field" in filterset.fields
    assert "boolean_field" not in filterset.fields


def test_filterset_with_model_exclude():

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = "__all__"
            exclude = ["integer_field"]

    filterset = TestFilterSet()
    assert "integer_field" not in filterset.fields
    assert "string_field" in filterset.fields


def test_filterset_with_required_fields():

    class TestFilterSet(FilterSet):
        field_1: int
        field_2: str

        class Meta:
            extra_kwargs = {
                "field_1": {"required": True},
            }

    filterset = TestFilterSet()
    assert filterset.fields["field_1"].required is True
    assert filterset.fields["field_2"].required is False


def test_filterset_with_order_field():

    class TestFilterSet(FilterSet):
        field_1: int

        class Meta:
            order_fields = [("field_1", "field_1")]

    filterset = TestFilterSet()
    assert "order_by" in filterset.fields
    assert filterset.get_options().order_param == "order_by"


def test_filterset_with_custom_order_param():

    class TestFilterSet(FilterSet):
        field_1: int

        class Meta:
            order_param = "sort_by"
            order_fields = [("field_1", "field_1")]

    filterset = TestFilterSet()
    assert "sort_by" in filterset.fields
    assert "order_by" not in filterset.fields


def test_filterset_with_explicit_order_field():

    class TestFilterSet(FilterSet):
        field_1: int
        order_field = OrderField(fields=[("field_1", "field_1")])

    filterset = TestFilterSet()
    assert "order_field" in filterset.fields


def test_filterset_with_explicit_order_field_inheritance():

    class BaseFilterSet(FilterSet):
        sort_by = OrderField(fields=[("field_1", "field_1")])

    class TestFilterSet(BaseFilterSet):
        field_1: int
        order_field = OrderField(fields=[("field_1", "field_1")])

    filterset = TestFilterSet()
    assert "order_field" in filterset.fields
    assert "sort_by" not in filterset.fields


@pytest.mark.parametrize(
    "fields_", [["field_1"], "__all__"]
)
def test_filterset_options_without_model(fields_):
    class TestFilterSet(FilterSet):
        field_1: int
        class Meta:
            fields = fields_

    assert "field_1" in TestFilterSet().fields
    assert "field_2" not in TestFilterSet().fields


def test_filterset_with_lookups():

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["gte", "lte"])

    filterset = TestFilterSet()
    assert "price" in filterset.fields
    assert "price__gte" in filterset.fields
    assert "price__lte" in filterset.fields
    assert "price!" in filterset.fields


def test_filterset_with_lookup_in():

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["in"])

    filterset = TestFilterSet()
    assert "price__in" in filterset.fields
    assert "price__in!" in filterset.fields
    assert isinstance(filterset.fields["price__in"], ListField)



def test_filterset_with_lookup_range():

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["range"])

    filterset = TestFilterSet()
    assert "price__range" in filterset.fields
    assert "price__range!" in filterset.fields
    assert isinstance(filterset.fields["price__range"], ListField)

def test_filterset_with_lookup_isnull():

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["isnull"])

    filterset = TestFilterSet()
    assert "price__isnull" in filterset.fields
    assert "price__isnull!" in filterset.fields
    assert isinstance(filterset.fields["price__isnull"], BooleanField)



@pytest.mark.django_db
def test_filterset_filter_queryset():
    # Create test data
    SampleModel.objects.create(integer_field=10, string_field="test1")
    SampleModel.objects.create(integer_field=20, string_field="test2")
    SampleModel.objects.create(integer_field=30, string_field="test3")

    class TestFilterSet(FilterSet):
        integer_field: int

    filterset = TestFilterSet(data={"integer_field": "20"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


@pytest.mark.django_db
@pytest.mark.parametrize("lookup_list", [
    ["gte", "lte"],
    ["comparison"],
    {"gte": {"allow_negate": False}, "lte": {"allow_negate": False}}
])
def test_filterset_filter_queryset_with_lookups(lookup_list):
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)
    SampleModel.objects.create(integer_field=30)

    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups=lookup_list)

    filterset = TestFilterSet(
        data={"integer_field__gte": "15", "integer_field__lte": "25"}
    )
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


@pytest.mark.django_db
def test_filterset_filter_queryset_with_negation():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    class TestFilterSet(FilterSet):
        integer_field: int

    filterset = TestFilterSet(data={"integer_field!": "10"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


@pytest.mark.django_db
def test_filterset_filter_queryset_or_operator():
    SampleModel.objects.create(integer_field=10, string_field="test1")
    SampleModel.objects.create(integer_field=20, string_field="test2")

    class TestFilterSet(FilterSet):
        integer_field: int
        string_field: str

        class Meta:
            operator = "OR"

    filterset = TestFilterSet(data={"integer_field": "10", "string_field": "test2"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)
    assert filtered_qs.count() == 2


@pytest.mark.django_db
def test_filterset_filter_queryset_xor_operator():
    SampleModel.objects.create(integer_field=10, string_field="test1")
    SampleModel.objects.create(integer_field=10, string_field="test2")
    SampleModel.objects.create(integer_field=20, string_field="test1")

    class TestFilterSet(FilterSet):
        integer_field: int
        string_field: str

        class Meta:
            operator = "XOR"

    filterset = TestFilterSet(data={"integer_field": "10", "string_field": "test1"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    # XOR should match records that match exactly one condition
    assert filtered_qs.count() == 2


@pytest.mark.django_db
def test_filterset_with_preprocessor():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    def my_preprocessor(_, queryset):
        return queryset.filter(integer_field__gte=15)

    class TestFilterSet(FilterSet):
        integer_field: int

        class Meta:
            preprocessors = [my_preprocessor]

    filterset = TestFilterSet(data={"integer_field": "20"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    # Preprocessor filters first, then field filter
    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


@pytest.mark.django_db
def test_filterset_with_postprocessor():
    SampleModel.objects.create(integer_field=10, string_field="keep")
    SampleModel.objects.create(integer_field=20, string_field="keep")
    SampleModel.objects.create(integer_field=30, string_field="remove")

    def my_postprocessor(_, queryset):
        return queryset.filter(string_field="keep")

    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups=["gte"])

        class Meta:
            postprocessors = [my_postprocessor]

    filterset = TestFilterSet(data={"integer_field__gte": "10"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 2


def test_filterset_model_dump():

    class TestFilterSet(FilterSet):
        integer_field: int
        string_field: str

    filterset = TestFilterSet(data={"integer_field": "10", "string_field": "test"})
    data = filterset.model_dump()

    assert data == {"integer_field": 10, "string_field": "test"}


def test_filterset_model_dump_validation_error():
    from rest_framework.exceptions import ValidationError

    class TestFilterSet(FilterSet):
        integer_field: int

    filterset = TestFilterSet(data={"integer_field": "invalid"})

    with pytest.raises(ValidationError):
        filterset.model_dump()


@pytest.mark.django_db
def test_filterset_on_abstract_model():
    with pytest.raises(ValueError) as exc:

        class TestFilterSet(FilterSet):
            class Meta:
                fields = "__all__"
                model = SampleAbstractModel

    assert "Abstract models" in str(exc.value)


@pytest.mark.django_db
def test_filterset_on_invalid_fields_structure():
    with pytest.raises(TypeError) :
        class TestFilterSet(FilterSet):
            field_1: int

            class Meta:
                fields = {"integer_field": "v"}
                model = SampleModel


def test_filterset_many_init_not_supported():

    class TestFilterSet(FilterSet):
        field: int

    with pytest.raises(NotImplementedError) as exc:
        TestFilterSet().many_init()
    assert "is not supported" in str(exc.value)


def test_inline_filterset():
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet",
        fields={
            "integer_field": IntegerField(lookups=["gte", "lte"]),
            "string_field": StringField(),
        },
    )

    filterset = TestFilterSet()
    assert "integer_field" in filterset.fields
    assert "string_field" in filterset.fields
    assert "integer_field__gte" in filterset.fields


def test_inline_filterset_with_type_annotations():
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet",
        fields={
            "field_1": int,
            "field_2": str,
        },
    )

    filterset = TestFilterSet()
    assert "field_1" in filterset.fields
    assert "field_2" in filterset.fields


def test_inline_filterset_with_model():
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"integer_field": int}, model=SampleModel
    )

    filterset = TestFilterSet()
    assert filterset.get_options().model == SampleModel


def test_inline_filterset_with_operators():
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, operator="OR"
    )

    filterset = TestFilterSet()
    assert filterset.get_options().operator == "OR"


def test_inline_filterset_with_preprocessors():

    def preprocessor(filterset, qs):
        return qs

    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, preprocessors=[preprocessor]
    )

    filterset = TestFilterSet()
    assert len(filterset.get_options().preprocessors) == 1


def test_inline_filterset_with_postprocessors():

    def postprocessor(filterset, qs):
        return qs

    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, postprocessors=[postprocessor]
    )

    filterset = TestFilterSet()
    assert len(filterset.get_options().postprocessors) == 1


def test_inline_filterset_with_order_fields():
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet",
        fields={"field": int},
        order_param="sort",
        order_fields=[("field", "field")],
    )

    filterset = TestFilterSet()
    assert "sort" in filterset.fields


def test_filterset_with_django_field_choices():

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = ["choice_field"]

    filterset = TestFilterSet()
    assert "choice_field" in filterset.fields
    from restflow.filters import ChoiceField

    assert isinstance(filterset.fields["choice_field"], ChoiceField)


def test_filterset_with_foreign_key():
    from tests.models import RelatedModel

    class TestFilterSet(FilterSet):
        class Meta:
            model = RelatedModel
            fields = ["sample_model"]

    filterset = TestFilterSet()
    assert "sample_model" in filterset.fields
    # ForeignKey should map to IntegerField with __pk lookup
    assert filterset.fields["sample_model"].filter_by == "sample_model__pk"



def test_filterset_with_foreign_key_as_related_field():
    from tests.models import RelatedModel

    class TestFilterSet(FilterSet):
        class Meta:
            model = RelatedModel
            fields = ["sample_model"]
            related_fields = ["sample_model"]

    filterset = TestFilterSet()
    assert "sample_model__id" in filterset.fields



def test_filterset_with_foreign_key_as_related_field_explicit():
    from tests.models import RelatedModel

    class TestFilterSet(FilterSet):
        sample_model = RelatedField(model=RelatedModel, fields="__all__", exclude=[])
        class Meta:
            model = RelatedModel

    filterset = TestFilterSet()
    assert "sample_model__id" in filterset.fields
    # ForeignKey should map to IntegerField with __pk lookup




@pytest.mark.django_db
@pytest.mark.parametrize(
    ("override_order_directionection", "order_by", "expected_value"),
    [
        ("asc", "integer_field", [10, 20, 30]),
        ("desc", "-integer_field", [10, 20, 30]),
    ],
)
def test_filterset_order_field_with_ordering(
    override_order_directionection, order_by, expected_value
):
    SampleModel.objects.create(integer_field=30)
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = []
            enable_ordering = True
            order_fields = [("integer_field", "integer_field")]
            override_order_direction = override_order_directionection

    filterset = TestFilterSet(data={"order_by": [order_by]})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    values = list(filtered_qs.values_list("integer_field", flat=True))
    assert values == expected_value


def test_filterset_multiple_order_fields():
    from restflow.filters import OrderField

    with pytest.raises(ValueError) as exc:

        class TestFilterSet(FilterSet):
            order1 = OrderField(fields=[("field", "field")])
            order2 = OrderField(fields=[("field", "field")])

    assert "Only one order field is allowed" in str(exc.value)


def test_filterset_explicit_field_priority():

    class TestFilterSet(FilterSet):
        field_1 = StringField()  # Explicit
        field_1: int  # Annotation

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["field_1"], StringField)


def test_filterset_annotation_priority_over_meta():

    class TestFilterSet(FilterSet):
        integer_field: str

        class Meta:
            model = SampleModel
            fields = ["integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["integer_field"], StringField)


def test_filterset_skip_not_equal():

    class TestFilterSet(FilterSet):
        field = IntegerField(allow_negate=False)

    filterset = TestFilterSet()
    assert "field" in filterset.fields
    assert "field!" not in filterset.fields


@pytest.mark.django_db
def test_filterset_with_method_field():

    def filter_method(request, queryset, value):
        return queryset.filter(integer_field__gte=value)

    class TestFilterSet(FilterSet):
        custom_filter = IntegerField(method=filter_method)

    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    filterset = TestFilterSet(data={"custom_filter": "15"})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20




@pytest.mark.django_db
def test_filterset_with_method_field_return_queryset():

    class CustomIntField(IntegerField):
        def apply_filter(self, filterset, queryset, value):
            return queryset.filter(integer_field__gte=value)

    class TestFilterSet(FilterSet):
        integer_field = CustomIntField()


    api_request = APIRequestFactory()
    request = api_request.get(path="/", data={"integer_field": "15"})

    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)


    _filterset = TestFilterSet(request=request)
    qs = SampleModel.objects.all()
    filtered_qs = _filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20



@pytest.mark.django_db
def test_filterset_with_undefined_field_in_model():
    with pytest.raises(FieldDoesNotExist):
        class TestFilterSet(FilterSet):
            field_1: int
            class Meta:
                model = SampleModel
                fields = ["undefined_field"]


def test_inline_filterset_with_no_model():
    with pytest.raises(ValueError):
        InlineFilterSet(name="TestFilterSet",)


@pytest.mark.parametrize(
    "obj_list", [[], int]
)
def test_getattr_multi_source(obj_list):
    assert getattr_multi_source(obj_list, "abcd", 1) == 1


def test_alias_lookups_generate_named_variants():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(
            lookups={"max": "lte", "min": "gte"},
            lookup_separator="_",
        )

    fs_fields = TestFilterSet().fields
    assert "integer_field_max" in fs_fields
    assert "integer_field_min" in fs_fields
    # ORM expression on the variant uses the standard __ joiner with the
    # mapped ORM lookup, regardless of the user-facing separator.
    assert fs_fields["integer_field_max"].filter_by == "integer_field__lte"
    assert fs_fields["integer_field_min"].filter_by == "integer_field__gte"
    assert "integer_field_max!" in fs_fields
    assert "integer_field_min!" in fs_fields


def test_per_lookup_help_text_resolves_in_three_tiers():
    class TestFilterSet(FilterSet):
        a_val = IntegerField(
            lookups={
                "min": {"lookup": "gte", "help_text": "Minimum A value"},
                "max": {"lookup": "lte"},
            },
            lookup_separator="_",
            help_text="A value",
        )

    fs_fields = TestFilterSet().fields
    assert fs_fields["a_val_min"].help_text == "Minimum A value"
    assert fs_fields["a_val_max"].help_text == "A value (Inclusive Upper Bound)"
    assert fs_fields["a_val_min"].filter_by == "a_val__gte"
    assert fs_fields["a_val_max"].filter_by == "a_val__lte"


def test_per_lookup_help_text_falls_back_to_none_without_parent_help():
    class TestFilterSet(FilterSet):
        a_val = IntegerField(lookups={"max": "lte"}, lookup_separator="_")

    fs_fields = TestFilterSet().fields
    assert fs_fields["a_val_max"].help_text is None


def test_alias_lookups_default_separator_is_double_underscore():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups={"max": "lte"})

    fs_fields = TestFilterSet().fields
    assert "integer_field__max" in fs_fields
    assert fs_fields["integer_field__max"].filter_by == "integer_field__lte"


@pytest.mark.django_db
def test_alias_lookups_apply_filter():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)
    SampleModel.objects.create(integer_field=30)

    class TestFilterSet(FilterSet):
        integer_field = IntegerField(
            lookups={"max": "lte", "min": "gte"},
            lookup_separator="_",
        )

    filterset = TestFilterSet(
        data={"integer_field_max": "25", "integer_field_min": "15"},
    )
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())
    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


@pytest.mark.django_db
def test_alias_lookups_negation_excludes_matching():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)
    SampleModel.objects.create(integer_field=30)

    class TestFilterSet(FilterSet):
        integer_field = IntegerField(
            lookups={"max": "lte"},
            lookup_separator="_",
        )

    # NOT (integer_field <= 15) -> integer_field > 15
    filterset = TestFilterSet(data={"integer_field_max!": "15"})
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())
    assert filtered_qs.count() == 2
    assert sorted(
        filtered_qs.values_list("integer_field", flat=True)
    ) == [20, 30]


def test_alias_lookups_with_db_field_remap_public_name():
    class TestFilterSet(FilterSet):
        product_price = IntegerField(
            db_field="price",
            lookups={"max": "lte", "min": "gte"},
            lookup_separator="_",
        )

    fs_fields = TestFilterSet().fields
    assert fs_fields["product_price_max"].filter_by == "price__lte"
    assert fs_fields["product_price_min"].filter_by == "price__gte"


def test_meta_lookup_separator_applied_when_field_does_not_set_one():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups={"max": "lte", "min": "gte"})

        class Meta:
            lookup_separator = "_"

    fs_fields = TestFilterSet().fields
    assert "integer_field_max" in fs_fields
    assert "integer_field_min" in fs_fields
    assert fs_fields["integer_field_max"].filter_by == "integer_field__lte"
    assert fs_fields["integer_field_min"].filter_by == "integer_field__gte"


def test_meta_lookup_separator_applies_to_standard_form_too():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups=["gte", "lte"])

        class Meta:
            lookup_separator = "_"

    fs_fields = TestFilterSet().fields
    assert "integer_field_gte" in fs_fields
    assert "integer_field_lte" in fs_fields
    assert fs_fields["integer_field_gte"].filter_by == "integer_field__gte"


def test_field_lookup_separator_overrides_meta():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(
            lookups={"max": "lte"},
            lookup_separator="-",
        )
        string_field = StringField(lookups={"like": "icontains"})

        class Meta:
            lookup_separator = "_"

    fs_fields = TestFilterSet().fields
    # integer_field uses its own "-"
    assert "integer_field-max" in fs_fields
    # string_field falls back to Meta's "_"
    assert "string_field_like" in fs_fields


def test_lookup_separator_default_is_double_underscore_without_meta():
    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups=["gte"])

    fs_fields = TestFilterSet().fields
    assert "integer_field__gte" in fs_fields


@pytest.mark.django_db
def test_meta_lookup_separator_end_to_end():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)
    SampleModel.objects.create(integer_field=30)

    class TestFilterSet(FilterSet):
        integer_field = IntegerField(lookups={"max": "lte", "min": "gte"})

        class Meta:
            lookup_separator = "_"

    filterset = TestFilterSet(
        data={"integer_field_max": "25", "integer_field_min": "15"},
    )
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())
    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 20


def test_alias_lookups_preserve_declaration_order_for_underscore_field_names():
    class TestFilterSet(FilterSet):
        first_field = IntegerField()
        created_at = IntegerField(
            lookups={"max": "lte"},
            lookup_separator="_",
        )

    field_names = list(TestFilterSet().fields.keys())
    assert field_names.index("first_field") < field_names.index("created_at")
    assert (
        field_names.index("created_at")
        < field_names.index("created_at_max")
        < field_names.index("created_at_max!")
    )


def test_array_field_extracts_to_list_field_with_pg_array_lookups():
    from restflow.filters.fields import ListField, StringField
    from restflow.filters.filters import FilterMetaClass, FilterOptions

    class ArrayField:
        def __init__(self, name, base_field):
            self.name = name
            self.base_field = base_field
            self.choices = None

    class _CharField:
        pass

    fake_field = ArrayField("tags", _CharField())
    fake_field.__class__.__name__ = "ArrayField"

    options = FilterOptions(options=[])
    items = FilterMetaClass._extract_django_model_fields(
        model_fields=[fake_field],
        options=options,
        extra_kwargs={},
    )

    assert len(items) == 1
    name, field = items[0]
    assert name == "tags"
    assert isinstance(field, ListField)
    assert isinstance(field.child, StringField)
    assert "contains" in field.lookups
    assert "overlaps" in field.lookups
    assert "contained_by" in field.lookups



@pytest.mark.django_db
def test_unset_boolean_filter_from_query_params_keeps_all_rows():
    SampleModel.objects.create(boolean_field=True)
    SampleModel.objects.create(boolean_field=False)

    class TestFilterSet(FilterSet):
        boolean_field = BooleanField(required=False)

    filterset = TestFilterSet(data=QueryDict(""))
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())

    assert filtered_qs.count() == 2


@pytest.mark.django_db
def test_set_boolean_filter_from_query_params_applies():
    SampleModel.objects.create(boolean_field=True)
    SampleModel.objects.create(boolean_field=False)

    class TestFilterSet(FilterSet):
        boolean_field = BooleanField(required=False)

    filterset = TestFilterSet(data=QueryDict("boolean_field=true"))
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())

    assert filtered_qs.count() == 1
    assert filtered_qs.first().boolean_field is True


@pytest.mark.django_db
def test_unset_multiple_choice_filter_from_query_params_keeps_all_rows():
    SampleModel.objects.create(choice_field="a")
    SampleModel.objects.create(choice_field="b")
    SampleModel.objects.create(choice_field="c")

    class TestFilterSet(FilterSet):
        choice_field = MultipleChoiceField(
            choices=[("a", "A"), ("b", "B"), ("c", "C")],
            filter_by="choice_field__in",
        )

    filterset = TestFilterSet(data=QueryDict(""))
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())

    assert filtered_qs.count() == 3


@pytest.mark.django_db
def test_set_multiple_choice_filter_from_query_params_applies():
    SampleModel.objects.create(choice_field="a")
    SampleModel.objects.create(choice_field="b")
    SampleModel.objects.create(choice_field="c")

    class TestFilterSet(FilterSet):
        choice_field = MultipleChoiceField(
            choices=[("a", "A"), ("b", "B"), ("c", "C")],
            filter_by="choice_field__in",
        )

    filterset = TestFilterSet(data=QueryDict("choice_field=a,b"))
    filtered_qs = filterset.filter_queryset(SampleModel.objects.all())

    assert filtered_qs.count() == 2
    assert set(filtered_qs.values_list("choice_field", flat=True)) == {"a", "b"}


def test_unset_filters_from_query_params_are_absent_from_validated_data():
    class TestFilterSet(FilterSet):
        is_active = BooleanField(required=False)
        kinds = MultipleChoiceField(
            choices=[("a", "A"), ("b", "B")],
            filter_by="kind__in",
        )
        ordering = OrderField(fields=[("created", "created_at")])

    filterset = TestFilterSet(data=QueryDict(""))

    assert filterset.is_valid()
    assert filterset.validated_data == {}
