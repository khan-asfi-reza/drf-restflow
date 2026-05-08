import pytest
from django.test import RequestFactory
from rest_framework.request import Request

from restflow.serializers import Field, HyperlinkedModelSerializer
from tests.models import SampleModel


@pytest.fixture
def request_with_host():
    factory = RequestFactory()
    return Request(factory.get("/"))


@pytest.fixture
def patch_reverse(monkeypatch):
    def fake_reverse(viewname, args=None, kwargs=None, request=None, format=None):
        pk = (args[0] if args else (kwargs or {}).get("pk", "?"))
        url = f"/{viewname}/{pk}/"
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    monkeypatch.setattr(
        "rest_framework.relations.reverse", fake_reverse, raising=False
    )
    monkeypatch.setattr(
        "rest_framework.serializers.reverse", fake_reverse, raising=False
    )


@pytest.mark.django_db
def test_hyperlinked_model_serializer_renders_url_for_pk(
    request_with_host, patch_reverse
):
    instance = SampleModel.objects.create(integer_field=1, string_field="a")

    class S(HyperlinkedModelSerializer):
        class Meta:
            model = SampleModel
            fields = ["url", "integer_field", "string_field"]
            extra_kwargs = {"url": {"view_name": "samplemodel-detail"}}

    rep = S(instance, context={"request": request_with_host}).data
    assert "url" in rep
    assert rep["url"].endswith(f"/samplemodel-detail/{instance.pk}/")
    assert rep["integer_field"] == 1


@pytest.mark.django_db
def test_hyperlinked_model_serializer_with_annotation_in_meta(
    request_with_host, patch_reverse
):
    instance = SampleModel.objects.create(integer_field=42)

    class S(HyperlinkedModelSerializer):
        extra: str = Field(write_only=True, default="x")

        class Meta:
            model = SampleModel
            fields = ["url", "integer_field"]
            extra_kwargs = {"url": {"view_name": "samplemodel-detail"}}

    assert "extra" in S.Meta.fields
    rep = S(instance, context={"request": request_with_host}).data
    assert rep["integer_field"] == 42
    assert "extra" not in rep


@pytest.mark.django_db
def test_hyperlinked_model_serializer_validates_input():
    class S(HyperlinkedModelSerializer):
        class Meta:
            model = SampleModel
            fields = ["url", "integer_field"]
            extra_kwargs = {"url": {"view_name": "samplemodel-detail"}}

    s = S(data={"integer_field": "not-int"})
    assert not s.is_valid()
    assert "integer_field" in s.errors


@pytest.mark.django_db
def test_hyperlinked_model_serializer_async_path():
    import asyncio

    class S(HyperlinkedModelSerializer):
        class Meta:
            model = SampleModel
            fields = ["url", "integer_field"]
            extra_kwargs = {"url": {"view_name": "samplemodel-detail"}}

    s = S(data={"integer_field": 7})
    assert asyncio.run(s.ais_valid())
    assert s.validated_data == {"integer_field": 7}
