import datetime

import pytest

from restflow.filters import (
    DateTimeField,
    EmailField,
    FilterSet,
    IntegerField,
    StringField,
)
from tests.models import SampleModel


class _SampleFilterSet(FilterSet):
    datetime_field = DateTimeField(
        lookups=["comparison", "year", "month", "day", "hour", "date", "time"]
    )
    email_field = EmailField(lookups=["exact", "icontains", "startswith"])

    class Meta:
        model = SampleModel


@pytest.mark.parametrize(
    "variant",
    ["year", "month", "day", "hour"],
)
def test_component_lookups_take_integers(variant):
    field = _SampleFilterSet().fields[f"datetime_field__{variant}"]
    assert isinstance(field, IntegerField)


def test_date_and_time_components_keep_their_own_types():
    fields = _SampleFilterSet().fields
    assert fields["datetime_field__date"].__class__.__name__ == "DateField"
    assert fields["datetime_field__time"].__class__.__name__ == "TimeField"


def test_comparison_lookups_keep_the_parent_type():
    field = _SampleFilterSet().fields["datetime_field__gte"]
    assert isinstance(field, DateTimeField)


def test_text_lookups_drop_the_parent_format_validator():
    fields = _SampleFilterSet().fields
    assert isinstance(fields["email_field__icontains"], StringField)
    assert isinstance(fields["email_field__startswith"], StringField)
    assert isinstance(fields["email_field"], EmailField)
    assert isinstance(fields["email_field__exact"], EmailField)


def test_email_substring_validates():
    filterset = _SampleFilterSet(data={"email_field__icontains": "organizer3"})
    assert filterset.is_valid(), filterset.errors


def test_email_exact_still_requires_an_address():
    filterset = _SampleFilterSet(data={"email_field__exact": "not-an-email"})
    assert not filterset.is_valid()
    assert "email_field__exact" in filterset.errors


@pytest.mark.django_db
def test_text_lookup_filters_by_fragment():
    expected = SampleModel.objects.create(email_field="organizer3@example.com")
    SampleModel.objects.create(email_field="someone@example.com")

    filterset = _SampleFilterSet(data={"email_field__icontains": "organizer3"})
    assert filterset.is_valid(), filterset.errors
    assert list(filterset.filter_queryset(SampleModel.objects.all())) == [
        expected
    ]


@pytest.mark.django_db
def test_year_lookup_filters_with_a_plain_year():
    SampleModel.objects.create(
        datetime_field=datetime.datetime(2024, 5, 1, 12, tzinfo=datetime.UTC)
    )
    expected = SampleModel.objects.create(
        datetime_field=datetime.datetime(2026, 5, 1, 12, tzinfo=datetime.UTC)
    )

    filterset = _SampleFilterSet(data={"datetime_field__year": 2026})
    assert filterset.is_valid(), filterset.errors
    assert list(filterset.filter_queryset(SampleModel.objects.all())) == [
        expected
    ]
