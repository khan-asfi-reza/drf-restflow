from typing import Literal

import pytest

from restflow.filters.fields import (
    IntegerField,
    OrderField,
    StringField,
)
from restflow.filters.filters import FilterSet, InlineFilterSet
from tests.models import SampleModel


@pytest.mark.django_db
class TestFilterSetPermutations:
    def test_filterset_with_only_annotation(self):
        class FS(FilterSet):
            integer_field: int

        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)

        fs = FS(data={"integer_field": "1"})
        result = fs.filter_queryset(SampleModel.objects.all())
        assert result.count() == 1

    def test_filterset_with_explicit_field(self):
        class FS(FilterSet):
            integer_field = IntegerField(db_field="integer_field")

        SampleModel.objects.create(integer_field=5)
        SampleModel.objects.create(integer_field=10)

        fs = FS(data={"integer_field": "5"})
        result = fs.filter_queryset(SampleModel.objects.all())
        assert result.count() == 1

    def test_filterset_with_meta_fields_only(self):
        class FS(FilterSet):
            class Meta:
                model = SampleModel
                fields = ["integer_field"]

        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)

        fs = FS(data={"integer_field": "1"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_combined_annotation_and_meta(self):
        class FS(FilterSet):
            integer_field: int

            class Meta:
                model = SampleModel
                fields = ["string_field"]

        SampleModel.objects.create(integer_field=1, string_field="a")
        SampleModel.objects.create(integer_field=2, string_field="a")

        fs = FS(data={"integer_field": "1", "string_field": "a"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_negation_via_exclamation(self):
        class FS(FilterSet):
            integer_field: int

        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=2)

        fs = FS(data={"integer_field!": "1"})
        result = fs.filter_queryset(SampleModel.objects.all())
        assert result.count() == 1
        assert result.first().integer_field == 2

    def test_filterset_lookup_variant_gte(self):
        class FS(FilterSet):
            integer_field = IntegerField(
                db_field="integer_field", lookups=["gte"]
            )

        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=5)
        SampleModel.objects.create(integer_field=10)

        fs = FS(data={"integer_field__gte": "5"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 2

    def test_filterset_or_operator(self):
        class FS(FilterSet):
            integer_field: int
            string_field: str

            class Meta:
                operator = "OR"

        SampleModel.objects.create(integer_field=1, string_field="a")
        SampleModel.objects.create(integer_field=2, string_field="b")
        SampleModel.objects.create(integer_field=3, string_field="c")

        fs = FS(data={"integer_field": "1", "string_field": "b"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 2

    def test_filterset_xor_operator(self):
        class FS(FilterSet):
            integer_field: int
            string_field: str

            class Meta:
                operator = "XOR"

        SampleModel.objects.create(integer_field=1, string_field="x")
        SampleModel.objects.create(integer_field=1, string_field="y")
        SampleModel.objects.create(integer_field=2, string_field="x")

        fs = FS(data={"integer_field": "1", "string_field": "x"})
        result = fs.filter_queryset(SampleModel.objects.all())
        assert result.count() == 2

    def test_filterset_order_field_orders_results(self):
        class FS(FilterSet):
            integer_field: int
            order = OrderField(fields=[("integer_field", "integer_field")])

        SampleModel.objects.create(integer_field=2)
        SampleModel.objects.create(integer_field=1)
        SampleModel.objects.create(integer_field=3)

        fs = FS(data={"order": "integer_field"})
        result = fs.filter_queryset(SampleModel.objects.all())
        ints = list(result.values_list("integer_field", flat=True))
        assert ints == [1, 2, 3]

    def test_filterset_order_field_descending(self):
        class FS(FilterSet):
            integer_field: int
            order = OrderField(fields=[("integer_field", "integer_field")])

        SampleModel.objects.create(integer_field=2)
        SampleModel.objects.create(integer_field=1)

        fs = FS(data={"order": "-integer_field"})
        result = fs.filter_queryset(SampleModel.objects.all())
        ints = list(result.values_list("integer_field", flat=True))
        assert ints == [2, 1]

    def test_filterset_invalid_value_handled(self):
        class FS(FilterSet):
            integer_field: int

        SampleModel.objects.create(integer_field=1)
        fs = FS(data={"integer_field": "notanint"})
        try:
            fs.filter_queryset(SampleModel.objects.all())
        except Exception:
            pass

    def test_filterset_multiple_fields_combined_with_and(self):
        class FS(FilterSet):
            integer_field: int
            string_field: str

        SampleModel.objects.create(integer_field=1, string_field="a")
        SampleModel.objects.create(integer_field=1, string_field="b")
        SampleModel.objects.create(integer_field=2, string_field="a")

        fs = FS(data={"integer_field": "1", "string_field": "a"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_no_query_params_returns_full_queryset(self):
        class FS(FilterSet):
            integer_field: int

        for i in range(3):
            SampleModel.objects.create(integer_field=i)

        fs = FS(data={})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 3

    def test_filterset_string_lookup_icontains(self):
        class FS(FilterSet):
            string_field: str = StringField(lookups=["icontains"])

        SampleModel.objects.create(string_field="foobar")
        SampleModel.objects.create(string_field="bazqux")

        fs = FS(data={"string_field__icontains": "foo"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_inheritance_combines_fields(self):
        class Base(FilterSet):
            integer_field: int

        class Child(Base):
            string_field: str

        SampleModel.objects.create(integer_field=1, string_field="x")
        SampleModel.objects.create(integer_field=2, string_field="y")

        fs = Child(data={"integer_field": "1", "string_field": "x"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_choice_field_via_literal(self):
        class FS(FilterSet):
            string_field: Literal["a", "b", "c"]

        SampleModel.objects.create(string_field="a")
        SampleModel.objects.create(string_field="b")

        fs = FS(data={"string_field": "a"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1

    def test_filterset_choice_field_invalid_value_raises(self):
        class FS(FilterSet):
            string_field: Literal["a", "b"]

        SampleModel.objects.create(string_field="a")
        fs = FS(data={"string_field": "z"})
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            fs.is_valid(raise_exception=True)


@pytest.mark.django_db
class TestInlineFilterSet:
    def test_inline_filterset_with_explicit_field_class(self):
        FS = InlineFilterSet(
            model=SampleModel,
            fields={"integer_field": IntegerField(db_field="integer_field")},
        )
        SampleModel.objects.create(integer_field=10)
        SampleModel.objects.create(integer_field=20)

        fs = FS(data={"integer_field": "10"})
        assert fs.filter_queryset(SampleModel.objects.all()).count() == 1
