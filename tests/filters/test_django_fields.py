import datetime
from decimal import Decimal

import pytest
from django.db import models
from django.utils import timezone

from restflow.filters import FilterSet
from restflow.filters.fields import (
    BooleanField,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    EmailField,
    FloatField,
    IntegerField,
    IPAddressField,
    StringField,
    TimeField,
)


# Test model with all Django field types
class AllFieldsModel(models.Model):
    char_field = models.CharField(max_length=100)
    text_field = models.TextField()
    email_field = models.EmailField()
    url_field = models.URLField()
    slug_field = models.SlugField()

    integer_field = models.IntegerField()
    big_integer_field = models.BigIntegerField()
    small_integer_field = models.SmallIntegerField()
    positive_integer_field = models.PositiveIntegerField()
    positive_small_integer_field = models.PositiveSmallIntegerField()
    float_field = models.FloatField()
    decimal_field = models.DecimalField(max_digits=10, decimal_places=2)

    date_field = models.DateField()
    datetime_field = models.DateTimeField()
    time_field = models.TimeField()
    duration_field = models.DurationField()

    boolean_field = models.BooleanField()
    ip_address_field = models.GenericIPAddressField()
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]
    choice_field = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        app_label = "tests"


class RelatedFieldModel(models.Model):
    """Model for testing relationship fields"""

    name = models.CharField(max_length=100)
    related_to = models.ForeignKey(
        AllFieldsModel, on_delete=models.CASCADE, related_name="related_items"
    )
    one_to_one = models.OneToOneField(
        AllFieldsModel, on_delete=models.CASCADE, related_name="one_to_one_item"
    )

    class Meta:
        app_label = "tests"


def test_char_field_mapping():
    """Test CharField maps to StringField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["char_field"]

    filterset = TestFilterSet()
    assert "char_field" in filterset.fields
    assert isinstance(filterset.fields["char_field"], StringField)
    assert filterset.fields["char_field"].filter_by == "char_field"


def test_text_field_mapping():
    """Test TextField maps to StringField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["text_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["text_field"], StringField)


def test_email_field_mapping():
    """Test EmailField maps to EmailField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["email_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["email_field"], EmailField)


def test_url_field_mapping():
    """Test URLField maps to StringField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["url_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["url_field"], StringField)


def test_slug_field_mapping():
    """Test SlugField maps to StringField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["slug_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["slug_field"], StringField)


def test_integer_field_mapping():
    """Test IntegerField maps to IntegerField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["integer_field"], IntegerField)


def test_big_integer_field_mapping():
    """Test BigIntegerField maps to IntegerField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["big_integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["big_integer_field"], IntegerField)


def test_small_integer_field_mapping():
    """Test SmallIntegerField maps to IntegerField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["small_integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["small_integer_field"], IntegerField)


def test_positive_integer_field_mapping():
    """Test PositiveIntegerField maps to IntegerField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["positive_integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["positive_integer_field"], IntegerField)


def test_positive_small_integer_field_mapping():
    """Test PositiveSmallIntegerField maps to IntegerField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["positive_small_integer_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["positive_small_integer_field"], IntegerField)


def test_float_field_mapping():
    """Test FloatField maps to FloatField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["float_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["float_field"], FloatField)


def test_decimal_field_mapping():
    """Test DecimalField maps to DecimalField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["decimal_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["decimal_field"], DecimalField)


def test_date_field_mapping():
    """Test DateField maps to DateField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["date_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["date_field"], DateField)


def test_datetime_field_mapping():
    """Test DateTimeField maps to DateTimeField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["datetime_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["datetime_field"], DateTimeField)


def test_time_field_mapping():
    """Test TimeField maps to TimeField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["time_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["time_field"], TimeField)


def test_duration_field_mapping():
    """Test DurationField maps to DurationField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["duration_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["duration_field"], DurationField)


def test_boolean_field_mapping():
    """Test BooleanField maps to BooleanField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["boolean_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["boolean_field"], BooleanField)


def test_ip_address_field_mapping():
    """Test GenericIPAddressField maps to IPAddressField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["ip_address_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["ip_address_field"], IPAddressField)


def test_choice_field_mapping():
    """Test CharField with choices maps to ChoiceField"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["choice_field"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["choice_field"], ChoiceField)
    # Verify choices are preserved
    field = filterset.fields["choice_field"]
    assert len(field.choices) == 3


def test_foreign_key_field_mapping():
    """Test ForeignKey maps to IntegerField with __pk lookup"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = RelatedFieldModel
            fields = ["related_to"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["related_to"], IntegerField)
    assert filterset.fields["related_to"].filter_by == "related_to__pk"


def test_one_to_one_field_mapping():
    """Test OneToOneField maps to IntegerField with __pk lookup"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = RelatedFieldModel
            fields = ["one_to_one"]

    filterset = TestFilterSet()
    assert isinstance(filterset.fields["one_to_one"], IntegerField)
    assert filterset.fields["one_to_one"].filter_by == "one_to_one__pk"


def test_all_fields_together():
    """Test FilterSet with all Django field types together"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = "__all__"

    filterset = TestFilterSet()
    fields = filterset.fields

    assert "char_field" in fields
    assert "text_field" in fields
    assert "email_field" in fields
    assert "url_field" in fields
    assert "slug_field" in fields
    assert "integer_field" in fields
    assert "big_integer_field" in fields
    assert "small_integer_field" in fields
    assert "positive_integer_field" in fields
    assert "positive_small_integer_field" in fields
    assert "float_field" in fields
    assert "decimal_field" in fields
    assert "date_field" in fields
    assert "datetime_field" in fields
    assert "time_field" in fields
    assert "duration_field" in fields
    assert "boolean_field" in fields
    assert "ip_address_field" in fields
    assert "choice_field" in fields

    assert isinstance(fields["char_field"], StringField)
    assert isinstance(fields["integer_field"], IntegerField)
    assert isinstance(fields["float_field"], FloatField)
    assert isinstance(fields["decimal_field"], DecimalField)
    assert isinstance(fields["date_field"], DateField)
    assert isinstance(fields["datetime_field"], DateTimeField)
    assert isinstance(fields["time_field"], TimeField)
    assert isinstance(fields["duration_field"], DurationField)
    assert isinstance(fields["boolean_field"], BooleanField)
    assert isinstance(fields["email_field"], EmailField)
    assert isinstance(fields["ip_address_field"], IPAddressField)
    assert isinstance(fields["choice_field"], ChoiceField)


def test_mixed_character_fields():
    """Test multiple character-based fields together"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = [
                "char_field",
                "text_field",
                "email_field",
                "url_field",
                "slug_field",
            ]

    filterset = TestFilterSet()

    assert isinstance(filterset.fields["char_field"], StringField)
    assert isinstance(filterset.fields["text_field"], StringField)
    assert isinstance(filterset.fields["email_field"], EmailField)
    assert isinstance(filterset.fields["url_field"], StringField)
    assert isinstance(filterset.fields["slug_field"], StringField)


def test_mixed_numeric_fields():
    """Test multiple numeric fields together"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = [
                "integer_field",
                "big_integer_field",
                "small_integer_field",
                "float_field",
                "decimal_field",
            ]

    filterset = TestFilterSet()

    # Integer variants should all be IntegerField
    assert isinstance(filterset.fields["integer_field"], IntegerField)
    assert isinstance(filterset.fields["big_integer_field"], IntegerField)
    assert isinstance(filterset.fields["small_integer_field"], IntegerField)

    # Float and Decimal should be their own types
    assert isinstance(filterset.fields["float_field"], FloatField)
    assert isinstance(filterset.fields["decimal_field"], DecimalField)


def test_mixed_datetime_fields():
    """Test multiple date/time fields together"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["date_field", "datetime_field", "time_field", "duration_field"]

    filterset = TestFilterSet()

    assert isinstance(filterset.fields["date_field"], DateField)
    assert isinstance(filterset.fields["datetime_field"], DateTimeField)
    assert isinstance(filterset.fields["time_field"], TimeField)
    assert isinstance(filterset.fields["duration_field"], DurationField)


def test_all_fields_generate_negation_variants():
    """Test that all non-list fields generate negation (!) variants"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["char_field", "integer_field", "boolean_field", "date_field"]

    filterset = TestFilterSet()

    # All should have negation variants
    assert "char_field!" in filterset.fields
    assert "integer_field!" in filterset.fields
    assert "boolean_field!" in filterset.fields
    assert "date_field!" in filterset.fields


def test_field_with_extra_kwargs_lookups():
    """Test extra_kwargs can specify lookups for Django model fields"""

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["integer_field", "char_field"]
            extra_kwargs = {
                "integer_field": {"lookups": ["gte", "lte"]},
                "char_field": {"lookups": ["icontains", "startswith"]},
            }

    filterset = TestFilterSet()

    assert "integer_field__gte" in filterset.fields
    assert "integer_field__lte" in filterset.fields

    assert "char_field__icontains" in filterset.fields
    assert "char_field__startswith" in filterset.fields



@pytest.mark.django_db
def test_filter_char_field():
    """Test filtering with CharField"""
    AllFieldsModel.objects.create(
        char_field="test1",
        text_field="text",
        email_field="test@example.com",
        url_field="http://example.com",
        slug_field="test-slug",
        integer_field=1,
        big_integer_field=1,
        small_integer_field=1,
        positive_integer_field=1,
        positive_small_integer_field=1,
        float_field=1.0,
        decimal_field=Decimal("1.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=1),
        boolean_field=True,
        ip_address_field="127.0.0.1",
        choice_field="draft",
    )
    AllFieldsModel.objects.create(
        char_field="test2",
        text_field="text",
        email_field="test2@example.com",
        url_field="http://example.com",
        slug_field="test-slug-2",
        integer_field=2,
        big_integer_field=2,
        small_integer_field=2,
        positive_integer_field=2,
        positive_small_integer_field=2,
        float_field=2.0,
        decimal_field=Decimal("2.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=2),
        boolean_field=False,
        ip_address_field="192.168.1.1",
        choice_field="published",
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["char_field"]

    filterset = TestFilterSet(data={"char_field": "test1"})
    qs = AllFieldsModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().char_field == "test1"


@pytest.mark.django_db
def test_filter_integer_field():
    """Test filtering with IntegerField"""
    AllFieldsModel.objects.all().delete()
    AllFieldsModel.objects.create(
        char_field="test1",
        text_field="text",
        email_field="test@example.com",
        url_field="http://example.com",
        slug_field="test-slug",
        integer_field=10,
        big_integer_field=1,
        small_integer_field=1,
        positive_integer_field=1,
        positive_small_integer_field=1,
        float_field=1.0,
        decimal_field=Decimal("1.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=1),
        boolean_field=True,
        ip_address_field="127.0.0.1",
        choice_field="draft",
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["integer_field"]

    filterset = TestFilterSet(data={"integer_field": "10"})
    qs = AllFieldsModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().integer_field == 10


@pytest.mark.django_db
def test_filter_boolean_field():
    """Test filtering with BooleanField"""
    AllFieldsModel.objects.all().delete()
    AllFieldsModel.objects.create(
        char_field="test1",
        text_field="text",
        email_field="test@example.com",
        url_field="http://example.com",
        slug_field="test-slug",
        integer_field=1,
        big_integer_field=1,
        small_integer_field=1,
        positive_integer_field=1,
        positive_small_integer_field=1,
        float_field=1.0,
        decimal_field=Decimal("1.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=1),
        boolean_field=True,
        ip_address_field="127.0.0.1",
        choice_field="draft",
    )
    AllFieldsModel.objects.create(
        char_field="test2",
        text_field="text",
        email_field="test2@example.com",
        url_field="http://example.com",
        slug_field="test-slug-2",
        integer_field=2,
        big_integer_field=2,
        small_integer_field=2,
        positive_integer_field=2,
        positive_small_integer_field=2,
        float_field=2.0,
        decimal_field=Decimal("2.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=2),
        boolean_field=False,
        ip_address_field="192.168.1.1",
        choice_field="published",
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["boolean_field"]

    filterset = TestFilterSet(data={"boolean_field": "true"})
    qs = AllFieldsModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().boolean_field is True


@pytest.mark.django_db
def test_filter_choice_field():
    """Test filtering with ChoiceField"""
    AllFieldsModel.objects.all().delete()
    AllFieldsModel.objects.create(
        char_field="test1",
        text_field="text",
        email_field="test@example.com",
        url_field="http://example.com",
        slug_field="test-slug",
        integer_field=1,
        big_integer_field=1,
        small_integer_field=1,
        positive_integer_field=1,
        positive_small_integer_field=1,
        float_field=1.0,
        decimal_field=Decimal("1.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=1),
        boolean_field=True,
        ip_address_field="127.0.0.1",
        choice_field="draft",
    )
    AllFieldsModel.objects.create(
        char_field="test2",
        text_field="text",
        email_field="test2@example.com",
        url_field="http://example.com",
        slug_field="test-slug-2",
        integer_field=2,
        big_integer_field=2,
        small_integer_field=2,
        positive_integer_field=2,
        positive_small_integer_field=2,
        float_field=2.0,
        decimal_field=Decimal("2.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=2),
        boolean_field=False,
        ip_address_field="192.168.1.1",
        choice_field="published",
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["choice_field"]

    filterset = TestFilterSet(data={"choice_field": "published"})
    qs = AllFieldsModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    assert filtered_qs.first().choice_field == "published"


@pytest.mark.django_db
def test_filter_multiple_fields_together():
    """Test filtering with multiple fields of different types"""
    AllFieldsModel.objects.all().delete()
    AllFieldsModel.objects.create(
        char_field="test1",
        text_field="text",
        email_field="test@example.com",
        url_field="http://example.com",
        slug_field="test-slug",
        integer_field=10,
        big_integer_field=1,
        small_integer_field=1,
        positive_integer_field=1,
        positive_small_integer_field=1,
        float_field=1.0,
        decimal_field=Decimal("1.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=1),
        boolean_field=True,
        ip_address_field="127.0.0.1",
        choice_field="draft",
    )
    AllFieldsModel.objects.create(
        char_field="test2",
        text_field="text",
        email_field="test2@example.com",
        url_field="http://example.com",
        slug_field="test-slug-2",
        integer_field=20,
        big_integer_field=2,
        small_integer_field=2,
        positive_integer_field=2,
        positive_small_integer_field=2,
        float_field=2.0,
        decimal_field=Decimal("2.0"),
        date_field=timezone.now().date(),
        datetime_field=timezone.now(),
        time_field=datetime.time(12, 0),
        duration_field=datetime.timedelta(days=2),
        boolean_field=False,
        ip_address_field="192.168.1.1",
        choice_field="published",
    )

    class TestFilterSet(FilterSet):
        class Meta:
            model = AllFieldsModel
            fields = ["char_field", "integer_field", "boolean_field"]

    filterset = TestFilterSet(
        data={"char_field": "test1", "integer_field": "10", "boolean_field": "true"}
    )
    qs = AllFieldsModel.objects.all()
    filtered_qs = filterset.filter_queryset(qs)

    assert filtered_qs.count() == 1
    result = filtered_qs.first()
    assert result.char_field == "test1"
    assert result.integer_field == 10
    assert result.boolean_field is True
