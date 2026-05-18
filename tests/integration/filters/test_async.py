import asyncio

import pytest
from django.db.models import Q, QuerySet

from restflow.filters.fields import IntegerField, OrderField, StringField
from restflow.filters.filters import FilterSet
from tests.models import SampleModel


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.django_db
def test_afilter_queryset_all_sync_matches_filter_queryset():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)
    SampleModel.objects.create(integer_field=30)

    class FS(FilterSet):
        integer_field: int

    sync_qs = list(
        FS(data={"integer_field": "20"}).filter_queryset(SampleModel.objects.all())
    )
    async_qs = list(
        _run(FS(data={"integer_field": "20"}).afilter_queryset(SampleModel.objects.all()))
    )
    assert [obj.integer_field for obj in sync_qs] == [obj.integer_field for obj in async_qs] == [20]


@pytest.mark.django_db
def test_afilter_queryset_async_method_returns_q():
    SampleModel.objects.create(integer_field=5)
    SampleModel.objects.create(integer_field=15)

    async def filter_method(filterset, queryset, value):
        return Q(integer_field__gte=value)

    class FS(FilterSet):
        threshold = IntegerField(method=filter_method)

    qs = _run(FS(data={"threshold": "10"}).afilter_queryset(SampleModel.objects.all()))
    assert {obj.integer_field for obj in qs} == {15}


@pytest.mark.django_db
def test_afilter_queryset_async_method_returns_queryset():
    SampleModel.objects.create(integer_field=1)
    SampleModel.objects.create(integer_field=2)

    async def filter_method(filterset, queryset, value):
        return queryset.filter(integer_field=value)

    class FS(FilterSet):
        target = IntegerField(method=filter_method)

    qs = _run(FS(data={"target": "2"}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.integer_field for obj in qs] == [2]


@pytest.mark.django_db
def test_afilter_queryset_async_string_method_on_filterset():
    SampleModel.objects.create(integer_field=100)
    SampleModel.objects.create(integer_field=200)

    class FS(FilterSet):
        custom = IntegerField(method="filter_custom")

        async def filter_custom(self, queryset, value):
            return Q(integer_field=value)

    qs = _run(FS(data={"custom": "200"}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.integer_field for obj in qs] == [200]


@pytest.mark.django_db
def test_afilter_queryset_async_preprocessor():
    SampleModel.objects.create(integer_field=1, string_field="active")
    SampleModel.objects.create(integer_field=2, string_field="inactive")

    async def only_active(filterset, queryset):
        return queryset.filter(string_field="active")

    class FS(FilterSet):
        class Meta:
            preprocessors = [only_active]

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.string_field for obj in qs] == ["active"]


@pytest.mark.django_db
def test_afilter_queryset_async_postprocessor():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=20)

    async def order_desc(filterset, queryset):
        return queryset.order_by("-integer_field")

    class FS(FilterSet):
        class Meta:
            postprocessors = [order_desc]

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.integer_field for obj in qs] == [20, 10]


@pytest.mark.django_db
def test_afilter_queryset_chain_with_two_async_processors_awaits_both():
    SampleModel.objects.create(integer_field=1, string_field="a")
    SampleModel.objects.create(integer_field=2, string_field="b")
    SampleModel.objects.create(integer_field=3, string_field="c")

    calls = []

    async def async_first(filterset, queryset):
        calls.append("first")
        return queryset.exclude(string_field="a")

    async def async_second(filterset, queryset):
        calls.append("second")
        return queryset.exclude(string_field="b")

    class FS(FilterSet):
        class Meta:
            preprocessors = [async_first, async_second]

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.string_field for obj in qs] == ["c"]
    assert calls == ["first", "second"]


@pytest.mark.django_db
def test_afilter_queryset_mixed_sync_and_async_processors_chain_in_order():
    SampleModel.objects.create(integer_field=1, string_field="a")
    SampleModel.objects.create(integer_field=2, string_field="b")
    SampleModel.objects.create(integer_field=3, string_field="c")

    calls = []

    def sync_first(filterset, queryset):
        calls.append("sync_first")
        return queryset.exclude(string_field="a")

    async def async_second(filterset, queryset):
        calls.append("async_second")
        return queryset.exclude(string_field="b")

    def sync_third(filterset, queryset):
        calls.append("sync_third")
        return queryset.order_by("integer_field")

    class FS(FilterSet):
        class Meta:
            preprocessors = [sync_first, async_second, sync_third]

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert [obj.string_field for obj in qs] == ["c"]
    assert calls == ["sync_first", "async_second", "sync_third"]


@pytest.mark.django_db
def test_afilter_queryset_mixed_sync_and_async_methods_in_filterset():
    SampleModel.objects.create(integer_field=10, string_field="apple")
    SampleModel.objects.create(integer_field=20, string_field="banana")
    SampleModel.objects.create(integer_field=30, string_field="apple")

    def sync_int_method(filterset, queryset, value):
        return Q(integer_field__gte=value)

    async def async_str_method(filterset, queryset, value):
        return Q(string_field=value)

    class FS(FilterSet):
        min_int = IntegerField(method=sync_int_method)
        name = StringField(method=async_str_method)

    qs = _run(
        FS(data={"min_int": "15", "name": "apple"}).afilter_queryset(
            SampleModel.objects.all()
        )
    )
    assert [obj.integer_field for obj in qs] == [30]


@pytest.mark.django_db
def test_afilter_queryset_orderfield_with_async_method():
    SampleModel.objects.create(integer_field=10)
    SampleModel.objects.create(integer_field=30)
    SampleModel.objects.create(integer_field=20)

    async def custom_order(filterset, queryset, value):
        return queryset.order_by(*value)

    class FS(FilterSet):
        sort = OrderField(
            fields=[("integer_field", "integer_field")], method=custom_order
        )

    qs = _run(
        FS(data={"sort": "integer_field"}).afilter_queryset(SampleModel.objects.all())
    )
    assert [obj.integer_field for obj in qs] == [10, 20, 30]


@pytest.mark.django_db
def test_afilter_queryset_or_operator_with_async_method():
    SampleModel.objects.create(integer_field=1, string_field="x")
    SampleModel.objects.create(integer_field=2, string_field="y")
    SampleModel.objects.create(integer_field=3, string_field="z")

    async def async_int_method(filterset, queryset, value):
        return Q(integer_field=value)

    def sync_str_method(filterset, queryset, value):
        return Q(string_field=value)

    class FS(FilterSet):
        i = IntegerField(method=async_int_method)
        s = StringField(method=sync_str_method)

        class Meta:
            operator = "OR"

    qs = _run(
        FS(data={"i": "1", "s": "z"}).afilter_queryset(SampleModel.objects.all())
    )
    assert {obj.integer_field for obj in qs} == {1, 3}


@pytest.mark.django_db
def test_afilter_queryset_empty_data_runs_async_preprocessors():
    SampleModel.objects.create(integer_field=1)
    SampleModel.objects.create(integer_field=2)

    ran = []

    async def stamp(filterset, queryset):
        ran.append("stamp")
        return queryset.filter(integer_field=2)

    class FS(FilterSet):
        class Meta:
            preprocessors = [stamp]

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert ran == ["stamp"]
    assert [obj.integer_field for obj in qs] == [2]


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.django_db
def test_filter_queryset_raises_on_async_method():
    async def filter_method(filterset, queryset, value):
        return Q(integer_field=value)

    class FS(FilterSet):
        custom = IntegerField(method=filter_method)

    with pytest.raises(TypeError, match="afilter_queryset"):
        FS(data={"custom": "1"}).filter_queryset(SampleModel.objects.all())


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.django_db
def test_filter_queryset_raises_on_async_preprocessor():
    async def proc(filterset, queryset):
        return queryset

    class FS(FilterSet):
        class Meta:
            preprocessors = [proc]

    with pytest.raises(TypeError, match="afilter_queryset"):
        FS(data={}).filter_queryset(SampleModel.objects.all())


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.django_db
def test_filter_queryset_raises_on_async_postprocessor():
    async def proc(filterset, queryset):
        return queryset

    class FS(FilterSet):
        class Meta:
            postprocessors = [proc]

    with pytest.raises(TypeError, match="afilter_queryset"):
        FS(data={}).filter_queryset(SampleModel.objects.all())


@pytest.mark.django_db
def test_afilter_queryset_returns_lazy_queryset():
    # afilter_queryset does not evaluate the queryset, consumer must.
    SampleModel.objects.create(integer_field=1)

    class FS(FilterSet):
        integer_field: int

    qs = _run(FS(data={}).afilter_queryset(SampleModel.objects.all()))
    assert isinstance(qs, QuerySet)
