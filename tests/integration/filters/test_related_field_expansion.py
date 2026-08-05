import pytest

from restflow.filters import FilterSet, RelatedField
from tests.models import RelatedModel, SampleModel


class _RelatedItemFilterSet(FilterSet):
    sample_model = RelatedField(
        model=SampleModel, fields=["string_field", "integer_field"]
    )

    class Meta:
        model = RelatedModel


def test_expanded_fields_are_exposed_under_the_relation_path():
    filterset = _RelatedItemFilterSet(data={})
    assert "sample_model__string_field" in filterset.fields
    assert "sample_model__integer_field" in filterset.fields


@pytest.mark.django_db
def test_expanded_field_filters_through_the_relation_not_the_base_model():
    alpha = SampleModel.objects.create(string_field="alpha", integer_field=1)
    beta = SampleModel.objects.create(string_field="beta", integer_field=2)
    RelatedModel.objects.create(sample_model=alpha, name="beta")
    expected = RelatedModel.objects.create(sample_model=beta, name="alpha")

    filterset = _RelatedItemFilterSet(
        data={"sample_model__string_field": "beta"}
    )
    assert filterset.is_valid(), filterset.errors
    result = filterset.filter_queryset(RelatedModel.objects.all())
    assert list(result) == [expected]


@pytest.mark.django_db
def test_expanded_numeric_field_filters_through_the_relation():
    parent = SampleModel.objects.create(string_field="alpha", integer_field=7)
    SampleModel.objects.create(string_field="beta", integer_field=8)
    expected = RelatedModel.objects.create(sample_model=parent, name="row")

    filterset = _RelatedItemFilterSet(data={"sample_model__integer_field": 7})
    assert filterset.is_valid(), filterset.errors
    result = filterset.filter_queryset(RelatedModel.objects.all())
    assert list(result) == [expected]
