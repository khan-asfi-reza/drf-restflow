import pytest


@pytest.fixture(autouse=True)
def clean_models(db):
    from tests.models import Article, RelatedModel, SampleModel, Tag

    RelatedModel.objects.all().delete()
    Article.objects.all().delete()
    Tag.objects.all().delete()
    SampleModel.objects.all().delete()
    yield
    RelatedModel.objects.all().delete()
    Article.objects.all().delete()
    Tag.objects.all().delete()
    SampleModel.objects.all().delete()
