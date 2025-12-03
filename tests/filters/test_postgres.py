import pytest
from django.conf import settings

pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(
    "postgresql" not in settings.DATABASES["default"]["ENGINE"],
    reason="Default database is not PostgreSQL",
)
from django.contrib.postgres.fields import ArrayField
from django.db import models

from restflow.filters import FilterSet
from restflow.filters.fields import (
    LOOKUP_CATEGORIES,
    IntegerField,
    ListField,
    StringField,
)


class PostgresModel(models.Model):
    """Model with PostgreSQL-specific fields"""

    integer_array = ArrayField(models.IntegerField(), blank=True, null=True)
    string_array = ArrayField(models.CharField(max_length=100), blank=True, null=True)
    float_array = ArrayField(models.FloatField(), blank=True, null=True)
    name = models.CharField(max_length=100)
    tags = ArrayField(models.CharField(max_length=50), blank=True, default=list)

    class Meta:
        app_label = "tests"


@pytest.mark.postgres
def test_array_field_maps_to_list_field():
    """Test ArrayField maps to ListField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["integer_array"]

    filterset = TestFilterSet()
    assert "integer_array" in filterset.fields
    assert isinstance(filterset.fields["integer_array"], ListField)


@pytest.mark.postgres
def test_array_field_integer_array():
    """Test integer ArrayField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["integer_array"]

    filterset = TestFilterSet()
    field = filterset.fields["integer_array"]
    assert isinstance(field, ListField)
    assert isinstance(field.child, IntegerField)


@pytest.mark.postgres
def test_array_field_string_array():
    """Test string ArrayField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["string_array"]

    filterset = TestFilterSet()
    field = filterset.fields["string_array"]
    assert isinstance(field, ListField)
    assert isinstance(field.child, StringField)


@pytest.mark.postgres
def test_array_field_has_pg_array_lookups():
    """Test ArrayField gets PostgreSQL-specific lookups"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["tags"]

    filterset = TestFilterSet()
    field = filterset.fields["tags"]
    # ArrayFields should get pg_array lookups
    assert sorted(LOOKUP_CATEGORIES["pg_array"]) == sorted(field.lookups)


@pytest.mark.postgres
def test_all_array_fields_together():
    """Test multiple ArrayFields together"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["integer_array", "string_array", "float_array"]

    filterset = TestFilterSet()

    assert "integer_array" in filterset.fields
    assert "string_array" in filterset.fields
    assert "float_array" in filterset.fields

    assert isinstance(filterset.fields["integer_array"], ListField)
    assert isinstance(filterset.fields["string_array"], ListField)
    assert isinstance(filterset.fields["float_array"], ListField)


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_array_field_contains():
    """Test filtering ArrayField with contains lookup"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="test1",
        integer_array=[1, 2, 3],
        string_array=["a", "b"],
        tags=["python", "django"],
    )
    PostgresModel.objects.create(
        name="test2",
        integer_array=[4, 5, 6],
        string_array=["c", "d"],
        tags=["javascript", "react"],
    )

    class TestFilterSet(FilterSet):
        tags = ListField(child=StringField(), filter_by="tags__contains")

    filterset = TestFilterSet(data={"tags": ["python"]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().name == "test1"


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_array_field_overlaps():
    """Test filtering ArrayField with overlaps lookup"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="test1",
        integer_array=[1, 2, 3],
        string_array=["a", "b"],
        tags=["python", "django"],
    )
    PostgresModel.objects.create(
        name="test2",
        integer_array=[3, 4, 5],
        string_array=["c", "d"],
        tags=["python", "flask"],
    )
    PostgresModel.objects.create(
        name="test3",
        integer_array=[6, 7, 8],
        string_array=["e", "f"],
        tags=["javascript", "react"],
    )

    class TestFilterSet(FilterSet):
        tags = ListField(child=StringField(), filter_by="tags__overlap")

    filterset = TestFilterSet(data={"tags": ["python", "javascript"]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)
    assert filtered_qs.count() == 3


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_integer_array():
    """Test filtering integer ArrayField"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="test1", integer_array=[10, 20, 30], string_array=["a"], tags=["tag1"]
    )
    PostgresModel.objects.create(
        name="test2", integer_array=[40, 50, 60], string_array=["b"], tags=["tag2"]
    )

    class TestFilterSet(FilterSet):
        integer_array = ListField(
            child=IntegerField(), filter_by="integer_array__contains"
        )

    filterset = TestFilterSet(data={"integer_array": [10]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().name == "test1"


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_array_field_contained_by():
    """Test filtering ArrayField with contained_by lookup"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="subset", integer_array=[1, 2], string_array=["a"], tags=["python"]
    )
    PostgresModel.objects.create(
        name="superset",
        integer_array=[1, 2, 3, 4, 5],
        string_array=["a", "b"],
        tags=["python", "django", "flask"],
    )

    class TestFilterSet(FilterSet):
        integer_array = ListField(
            child=IntegerField(), filter_by="integer_array__contained_by"
        )

    filterset = TestFilterSet(data={"integer_array": [1, 2, 3, 4, 5]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)
    assert filtered_qs.count() == 2


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_string_array():
    """Test filtering string ArrayField"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="test1", integer_array=[1], string_array=["hello", "world"], tags=["tag1"]
    )
    PostgresModel.objects.create(
        name="test2", integer_array=[2], string_array=["foo", "bar"], tags=["tag2"]
    )

    class TestFilterSet(FilterSet):
        string_array = ListField(
            child=StringField(), filter_by="string_array__contains"
        )

    filterset = TestFilterSet(data={"string_array": ["hello"]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().name == "test1"


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_filter_multiple_array_fields():
    """Test filtering with multiple ArrayFields"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="match",
        integer_array=[1, 2, 3],
        string_array=["a", "b"],
        tags=["python", "django"],
    )
    PostgresModel.objects.create(
        name="no_match_int",
        integer_array=[4, 5, 6],
        string_array=["a", "b"],
        tags=["python"],
    )
    PostgresModel.objects.create(
        name="no_match_str",
        integer_array=[1, 2, 3],
        string_array=["c", "d"],
        tags=["django"],
    )

    class TestFilterSet(FilterSet):
        integer_array = ListField(
            child=IntegerField(), filter_by="integer_array__contains"
        )
        string_array = ListField(
            child=StringField(), filter_by="string_array__contains"
        )

    filterset = TestFilterSet(data={"integer_array": [1], "string_array": ["a"]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    # Only "match" should satisfy both conditions
    assert filtered_qs.count() == 1
    assert filtered_qs.first().name == "match"


@pytest.mark.postgres
def test_array_field_generates_variants():
    """Test ArrayField doesn't generate negation variants (it's a ListField)"""

    class TestFilterSet(FilterSet):
        tags = ArrayField(models.CharField(max_length=50))

        class Meta:
            model = PostgresModel
            fields = ["tags"]

    filterset = TestFilterSet()

    assert "tags" in filterset.fields
    assert "tags!" in filterset.fields


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_array_field_validation():
    """Test ArrayField validates input correctly"""

    class TestFilterSet(FilterSet):
        integer_array = ListField(child=IntegerField())

    filterset = TestFilterSet(data={"integer_array": "1,2,3"})
    assert filterset.is_valid()
    assert filterset.validated_data["integer_array"] == [1, 2, 3]

    filterset = TestFilterSet(data={"integer_array": "a,b,c"})
    assert not filterset.is_valid()


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_array_field_with_ordering():
    """Test combining ArrayField filters with ordering"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="alpha", integer_array=[1, 2], string_array=["a"], tags=["python"]
    )
    PostgresModel.objects.create(
        name="beta", integer_array=[1, 2], string_array=["b"], tags=["python"]
    )
    PostgresModel.objects.create(
        name="gamma", integer_array=[3, 4], string_array=["c"], tags=["javascript"]
    )

    class TestFilterSet(FilterSet):
        integer_array = ListField(
            child=IntegerField(), filter_by="integer_array__contains"
        )

        class Meta:
            model = PostgresModel
            fields = []
            order_fields = [("name", "name")]

    filterset = TestFilterSet(data={"integer_array": [1], "order_by": ["name"]})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 2
    assert list(filtered_qs.values_list("name", flat=True)) == ["alpha", "beta"]


@pytest.mark.postgres
def test_array_field_with_complex_types():
    """Test ArrayField handles complex child field types"""

    class ComplexPostgresModel(models.Model):
        date_array = ArrayField(models.DateField(), blank=True, null=True)
        decimal_array = ArrayField(
            models.DecimalField(max_digits=10, decimal_places=2), blank=True, null=True
        )

        class Meta:
            app_label = "tests"

    class TestFilterSet(FilterSet):
        class Meta:
            model = ComplexPostgresModel
            fields = ["date_array", "decimal_array"]

    filterset = TestFilterSet()

    assert "date_array" in filterset.fields
    assert "decimal_array" in filterset.fields
    assert isinstance(filterset.fields["date_array"], ListField)
    assert isinstance(filterset.fields["decimal_array"], ListField)


@pytest.mark.django_db(databases=["default"])
@pytest.mark.postgres
def test_empty_array_filtering():
    """Test filtering with empty arrays"""
    PostgresModel.objects.all().delete()
    PostgresModel.objects.create(
        name="empty", integer_array=[], string_array=[], tags=[]
    )
    PostgresModel.objects.create(
        name="not_empty", integer_array=[1], string_array=["a"], tags=["tag"]
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = PostgresModel
            fields = ["integer_array"]

    filterset = TestFilterSet(data={"integer_array": "1"})
    qs = PostgresModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)
    assert filtered_qs.count() == 1
    assert filtered_qs.first().name == "not_empty"
