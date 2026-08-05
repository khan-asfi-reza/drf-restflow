import asyncio

import pytest
from rest_framework import serializers as drf_serializers
from rest_framework.validators import UniqueValidator

from restflow.serializers import ModelSerializer
from tests.models import RelatedModel, SampleModel, Tag


class _RelatedItemSerializer(ModelSerializer):
    class Meta:
        model = RelatedModel
        fields = ["id", "sample_model", "name"]


class _UniqueTagSerializer(ModelSerializer):
    name = drf_serializers.CharField(
        validators=[UniqueValidator(queryset=Tag.objects.all())]
    )

    class Meta:
        model = Tag
        fields = ["id", "name"]


@pytest.mark.django_db(transaction=True)
def test_ais_valid_resolves_a_related_primary_key():
    parent = SampleModel.objects.create(string_field="parent")

    async def run():
        serializer = _RelatedItemSerializer(
            data={"sample_model": parent.pk, "name": "child"}
        )
        assert await serializer.ais_valid(raise_exception=True)
        assert serializer.validated_data["sample_model"] == parent
        instance = await serializer.asave()
        assert instance.sample_model_id == parent.pk

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_ais_valid_reports_a_missing_related_primary_key():
    async def run():
        serializer = _RelatedItemSerializer(
            data={"sample_model": 10**9, "name": "child"}
        )
        assert not await serializer.ais_valid()
        assert "sample_model" in serializer.errors

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_ais_valid_runs_a_unique_validator():
    Tag.objects.create(name="taken")

    async def run():
        serializer = _UniqueTagSerializer(data={"name": "taken"})
        assert not await serializer.ais_valid()
        assert "name" in serializer.errors

        serializer = _UniqueTagSerializer(data={"name": "free"})
        assert await serializer.ais_valid(raise_exception=True)

    asyncio.run(run())
