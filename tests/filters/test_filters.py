import datetime
import decimal
from typing import Literal, Optional

import pytest
from django.core.exceptions import FieldDoesNotExist
from rest_framework.test import APIRequestFactory

from restflow.filters.fields import (
    BooleanField,
    Email,
    Field,
    IntegerField,
    IPAddress,
    ListField,
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
    """Test FilterSet inheritance generates fields from parent classes"""

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
    """Test FilterOptions raises error for invalid operator"""
    with pytest.raises(ValueError) as exc:

        class InvalidFilterSet(FilterSet):
            field: int

            class Meta:
                operator = "INVALID"

    assert "Operator must be one of AND, OR, XOR" in str(exc.value)


def test_filterset_with_model_all_fields():
    """Test FilterSet with Meta.fields='__all__' generates fields from model"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = "__all__"

    filterset = TestFilterSet()
    assert "integer_field" in filterset.fields
    assert "string_field" in filterset.fields
    assert "boolean_field" in filterset.fields


def test_filterset_with_model_specific_fields():
    """Test FilterSet with Meta.fields list"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = ["integer_field", "string_field"]

    filterset = TestFilterSet()
    assert "integer_field" in filterset.fields
    assert "string_field" in filterset.fields
    assert "boolean_field" not in filterset.fields


def test_filterset_with_model_exclude():
    """Test FilterSet with Meta.exclude"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = "__all__"
            exclude = ["integer_field"]

    filterset = TestFilterSet()
    assert "integer_field" not in filterset.fields
    assert "string_field" in filterset.fields


def test_filterset_with_required_fields():
    """Test FilterSet with Meta.required_fields"""

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
    """Test FilterSet automatically creates OrderField"""

    class TestFilterSet(FilterSet):
        field_1: int

        class Meta:
            order_fields = [("field_1", "field_1")]

    filterset = TestFilterSet()
    assert "order_by" in filterset.fields
    assert filterset.get_options().order_param == "order_by"


def test_filterset_with_custom_order_param():
    """Test FilterSet with custom order parameter name"""

    class TestFilterSet(FilterSet):
        field_1: int

        class Meta:
            order_param = "sort_by"
            order_fields = [("field_1", "field_1")]

    filterset = TestFilterSet()
    assert "sort_by" in filterset.fields
    assert "order_by" not in filterset.fields


def test_filterset_with_explicit_order_field():
    """Test FilterSet with explicit order field"""

    class TestFilterSet(FilterSet):
        field_1: int
        order_field = OrderField(fields=[("field_1", "field_1")])

    filterset = TestFilterSet()
    assert "order_field" in filterset.fields


def test_filterset_with_explicit_order_field_inheritance():
    """Test FilterSet with explicit order field, inheritance order fields, the most recent one takes precedence"""

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
    """Test FilterOptions without a model"""
    class TestFilterSet(FilterSet):
        field_1: int
        class Meta:
            fields = fields_

    assert "field_1" in TestFilterSet().fields
    assert "field_2" not in TestFilterSet().fields


def test_filterset_with_lookups():
    """Test FilterSet generates lookup fields"""

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["gte", "lte"])

    filterset = TestFilterSet()
    assert "price" in filterset.fields
    assert "price__gte" in filterset.fields
    assert "price__lte" in filterset.fields
    assert "price!" in filterset.fields


def test_filterset_with_lookup_in():
    """Test FilterSet generates lookup `in` as ListField"""

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["in"])

    filterset = TestFilterSet()
    assert "price__in" in filterset.fields
    assert "price__in!" in filterset.fields
    assert isinstance(filterset.fields["price__in"], ListField)



def test_filterset_with_lookup_range():
    """Test FilterSet generates lookup `range` as ListField"""

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["range"])

    filterset = TestFilterSet()
    assert "price__range" in filterset.fields
    assert "price__range!" in filterset.fields
    assert isinstance(filterset.fields["price__range"], ListField)

def test_filterset_with_lookup_isnull():
    """Test FilterSet generates lookup `isnull` as BooleanField"""

    class TestFilterSet(FilterSet):
        price = IntegerField(lookups=["isnull"])

    filterset = TestFilterSet()
    assert "price__isnull" in filterset.fields
    assert "price__isnull!" in filterset.fields
    assert isinstance(filterset.fields["price__isnull"], BooleanField)



@pytest.mark.django_db
def test_filterset_filter_queryset():
    """Test FilterSet.filter_queryset applies filters"""
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
    """Test FilterSet.filter_queryset with lookup fields"""
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
    """Test FilterSet.filter_queryset with negation fields"""
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
    """Test FilterSet.filter_queryset with OR operator"""
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
    """Test FilterSet.filter_queryset with XOR operator"""
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
    """Test FilterSet with preprocessor"""
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
    """Test FilterSet with postprocessor"""
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
    """Test FilterSet.model_dump returns validated data"""

    class TestFilterSet(FilterSet):
        integer_field: int
        string_field: str

    filterset = TestFilterSet(data={"integer_field": "10", "string_field": "test"})
    data = filterset.model_dump()

    assert data == {"integer_field": 10, "string_field": "test"}


def test_filterset_model_dump_validation_error():
    """Test FilterSet.model_dump raises validation error"""
    from rest_framework.exceptions import ValidationError

    class TestFilterSet(FilterSet):
        integer_field: int

    filterset = TestFilterSet(data={"integer_field": "invalid"})

    with pytest.raises(ValidationError):
        filterset.model_dump()


@pytest.mark.django_db
def test_filterset_on_abstract_model():
    """Test FilterSet on abstract model raises ValueError"""
    with pytest.raises(ValueError) as exc:

        class TestFilterSet(FilterSet):
            class Meta:
                fields = "__all__"
                model = SampleAbstractModel

    assert "Abstract models" in str(exc.value)


@pytest.mark.django_db
def test_filterset_on_invalid_fields_structure():
    """Test FilterSet on invalid fields structure raises TypeError"""
    with pytest.raises(TypeError) :
        class TestFilterSet(FilterSet):
            field_1: int

            class Meta:
                fields = {"integer_field": "v"}
                model = SampleModel


def test_filterset_many_init_not_supported():
    """Test FilterSet.many_init raises NotImplementedError"""

    class TestFilterSet(FilterSet):
        field: int

    with pytest.raises(NotImplementedError) as exc:
        TestFilterSet().many_init()
    assert "`many=True` is not supported" in str(exc.value)


def test_inline_filterset():
    """Test InlineFilterSet creates FilterSet dynamically"""
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
    """Test InlineFilterSet with type annotations as fields"""
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
    """Test InlineFilterSet with model"""
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"integer_field": int}, model=SampleModel
    )

    filterset = TestFilterSet()
    assert filterset.get_options().model == SampleModel


def test_inline_filterset_with_operators():
    """Test InlineFilterSet with custom operator"""
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, operator="OR"
    )

    filterset = TestFilterSet()
    assert filterset.get_options().operator == "OR"


def test_inline_filterset_with_preprocessors():
    """Test InlineFilterSet with preprocessors"""

    def preprocessor(filterset, qs):
        return qs

    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, preprocessors=[preprocessor]
    )

    filterset = TestFilterSet()
    assert len(filterset.get_options().preprocessors) == 1


def test_inline_filterset_with_postprocessors():
    """Test InlineFilterSet with postprocessors"""

    def postprocessor(filterset, qs):
        return qs

    TestFilterSet = InlineFilterSet(
        name="TestFilterSet", fields={"field": int}, postprocessors=[postprocessor]
    )

    filterset = TestFilterSet()
    assert len(filterset.get_options().postprocessors) == 1


def test_inline_filterset_with_order_fields():
    """Test InlineFilterSet with order fields"""
    TestFilterSet = InlineFilterSet(
        name="TestFilterSet",
        fields={"field": int},
        order_param="sort",
        order_fields=[("field", "field")],
    )

    filterset = TestFilterSet()
    assert "sort" in filterset.fields


def test_filterset_with_django_field_choices():
    """Test FilterSet generates ChoiceField for Django model field with choices"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = ["choice_field"]

    filterset = TestFilterSet()
    assert "choice_field" in filterset.fields
    from restflow.filters import ChoiceField

    assert isinstance(filterset.fields["choice_field"], ChoiceField)


def test_filterset_with_foreign_key():
    """Test FilterSet handles ForeignKey fields"""
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
    """Test FilterSet handles ForeignKey fields"""
    from tests.models import RelatedModel

    class TestFilterSet(FilterSet):
        class Meta:
            model = RelatedModel
            fields = ["sample_model"]
            related_fields = ["sample_model"]

    filterset = TestFilterSet()
    assert "sample_model__id" in filterset.fields



def test_filterset_with_foreign_key_as_related_field_explicit():
    """Test FilterSet handles ForeignKey fields"""
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
    ("override_order_direction", "order_by", "expected_value"),
    [
        ("asc", "integer_field", [10, 20, 30]),
        ("desc", "-integer_field", [10, 20, 30]),
    ],
)
def test_filterset_order_field_with_ordering(
    override_order_direction, order_by, expected_value
):
    """Test FilterSet with OrderField performs ordering"""
    SampleModel.objects.create(integer_field=30)
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    class TestFilterSet(FilterSet):
        class Meta:
            model = SampleModel
            fields = []
            enable_ordering = True
            order_fields = [("integer_field", "integer_field")]
            override_order_dir = override_order_direction

    filterset = TestFilterSet(data={"order_by": [order_by]})
    qs = SampleModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    values = list(filtered_qs.values_list("integer_field", flat=True))
    assert values == expected_value


def test_filterset_multiple_order_fields():
    """Test FilterSet handles multiple OrderField instances error"""
    from restflow.filters import OrderField

    with pytest.raises(ValueError) as exc:

        class TestFilterSet(FilterSet):
            order1 = OrderField(fields=[("field", "field")])
            order2 = OrderField(fields=[("field", "field")])

    assert "Only one order field is allowed" in str(exc.value)


def test_filterset_explicit_field_priority():
    """Test explicit fields take priority over annotations"""

    class TestFilterSet(FilterSet):
        field_1 = StringField()  # Explicit
        field_1: int  # Annotation

    filterset = TestFilterSet()
    # Should use the explicit StringField, not IntegerField from annotation
    assert isinstance(filterset.fields["field_1"], StringField)


def test_filterset_annotation_priority_over_meta():
    """Test annotations take priority over Meta.fields"""

    class TestFilterSet(FilterSet):
        integer_field: str

        class Meta:
            model = SampleModel
            fields = ["integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["integer_field"], StringField)


def test_filterset_skip_not_equal():
    """Test field with allow_negate=True doesn't generate a negation field"""

    class TestFilterSet(FilterSet):
        field = IntegerField(allow_negate=False)

    filterset = TestFilterSet()
    assert "field" in filterset.fields
    assert "field!" not in filterset.fields


@pytest.mark.django_db
def test_filterset_with_method_field():
    """Test FilterSet with field using method parameter"""

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
    """Test FilterSet with custom-field that returns queryset"""

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
    """Test FilterSet with undefined field in model"""
    with pytest.raises(FieldDoesNotExist):
        class TestFilterSet(FilterSet):
            field_1: int
            class Meta:
                model = SampleModel
                fields = ["undefined_field"]


def test_inline_filterset_with_no_model():
    """Test InlineFilterSet with no model"""
    with pytest.raises(ValueError):
        InlineFilterSet(name="TestFilterSet",)


@pytest.mark.parametrize(
    "obj_list", [[], int]
)
def test_getattr_multi_source(obj_list):
    assert getattr_multi_source(obj_list, "abcd", 1) == 1
