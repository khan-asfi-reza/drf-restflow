import asyncio

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from restflow.pagination import (
    BasePagination,
    FastPageNumberPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)


def _run(coro):
    return asyncio.run(coro)


def _request(query=""):
    factory = RequestFactory()
    return Request(factory.get(f"/?{query}"))


class _StubAsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


class _StubQuerySet:
    def __init__(self, items):
        self._items = list(items)
        self._sliced = self._items

    async def acount(self):
        return len(self._items)

    def __getitem__(self, key):
        sliced = _StubQuerySet(self._items)
        sliced._sliced = self._items[key]
        sliced._items = sliced._sliced
        return sliced

    def __iter__(self):
        return iter(self._items)

    def __aiter__(self):
        return _StubAsyncIter(self._items).__aiter__()


def test_page_number_pagination_apaginate_returns_first_page():
    qs = _StubQuerySet(list(range(7)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = _request("page=1")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [0, 1, 2]
    assert paginator.page.paginator.count == 7
    assert paginator.page.number == 1


def test_page_number_pagination_apaginate_second_page():
    qs = _StubQuerySet(list(range(7)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = _request("page=2")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [3, 4, 5]
    assert paginator.page.number == 2


def test_page_number_pagination_apaginate_invalid_page_raises():
    qs = _StubQuerySet(list(range(3)))
    paginator = PageNumberPagination()
    paginator.page_size = 5
    request = _request("page=99")

    with pytest.raises(NotFound):
        _run(paginator.apaginate_queryset(qs, request))


def test_page_number_pagination_paginated_response_has_count():
    qs = _StubQuerySet(list(range(2)))
    paginator = PageNumberPagination()
    paginator.page_size = 5
    request = _request("page=1")

    _run(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response(["a", "b"])

    assert response.data["count"] == 2
    assert response.data["results"] == ["a", "b"]


def test_page_number_pagination_returns_none_when_page_size_zero():
    paginator = PageNumberPagination()
    paginator.page_size = None
    request = _request()
    assert _run(paginator.apaginate_queryset(_StubQuerySet([]), request)) is None


def test_limit_offset_pagination_apaginate():
    qs = _StubQuerySet(list(range(5)))
    paginator = LimitOffsetPagination()
    paginator.default_limit = 2
    request = _request("limit=2&offset=2")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [2, 3]
    assert paginator.count == 5


def test_limit_offset_pagination_returns_empty_when_offset_past_end():
    qs = _StubQuerySet([1, 2])
    paginator = LimitOffsetPagination()
    paginator.default_limit = 5
    request = _request("limit=5&offset=99")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == []


def test_fast_page_number_apaginate_returns_first_page_with_next():
    qs = _StubQuerySet(list(range(10)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=1")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [0, 1, 2]
    assert paginator.has_next is True


def test_fast_page_number_apaginate_partial_last_page_has_no_next():
    qs = _StubQuerySet(list(range(7)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=3")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [6]
    assert paginator.has_next is False


def test_fast_page_number_apaginate_full_last_page_no_false_next():
    qs = _StubQuerySet(list(range(6)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=2")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [3, 4, 5]
    assert paginator.has_next is False


def test_fast_page_number_apaginate_full_page_with_more_reports_next():
    qs = _StubQuerySet(list(range(7)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=2")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert page == [3, 4, 5]
    assert paginator.has_next is True


def test_fast_page_number_apaginate_skips_count_call():
    class _NoCountQuerySet(_StubQuerySet):
        async def acount(self):
            msg = "acount should not be called"
            raise AssertionError(msg)

    qs = _NoCountQuerySet(list(range(10)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=1")

    page = _run(paginator.apaginate_queryset(qs, request))
    assert page == [0, 1, 2]


def test_fast_page_number_paginated_response_omits_count():
    qs = _StubQuerySet(list(range(10)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=2")

    _run(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response(["a", "b", "c"])

    assert "count" not in response.data
    assert response.data["results"] == ["a", "b", "c"]
    assert "page=3" in response.data["next"]
    assert response.data["previous"] is not None


def test_fast_page_number_paginated_response_first_page_no_previous():
    qs = _StubQuerySet(list(range(10)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=1")

    _run(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([0, 1, 2])

    assert response.data["previous"] is None
    assert "page=2" in response.data["next"]


def test_fast_page_number_paginated_response_last_page_no_next():
    qs = _StubQuerySet(list(range(7)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=3")

    _run(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([6])

    assert response.data["next"] is None
    assert "page=2" in response.data["previous"]


def test_fast_page_number_invalid_page_number_raises():
    qs = _StubQuerySet([])
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=0")

    with pytest.raises(NotFound):
        _run(paginator.apaginate_queryset(qs, request))


def test_fast_page_number_overshooting_page_raises_when_empty():
    qs = _StubQuerySet([1, 2])
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=99")

    with pytest.raises(NotFound):
        _run(paginator.apaginate_queryset(qs, request))


def test_fast_page_number_sync_paginate_queryset():
    items = list(range(10))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=1")

    page = paginator.paginate_queryset(items, request)

    assert page == [0, 1, 2]
    assert paginator.has_next is True


def test_fast_page_number_sync_partial_last_page():
    items = list(range(5))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=2")

    page = paginator.paginate_queryset(items, request)

    assert page == [3, 4]
    assert paginator.has_next is False


def test_fast_page_number_size_query_param_when_enabled():
    qs = _StubQuerySet(list(range(20)))

    class _Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = 10

    paginator = _Sized()
    paginator.page_size = 3
    request = _request("page=1&size=5")

    page = _run(paginator.apaginate_queryset(qs, request))

    assert len(page) == 5
    assert paginator.has_next is True


def test_fast_page_number_size_query_param_capped_at_max():
    qs = _StubQuerySet(list(range(20)))

    class _Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = 4

    paginator = _Sized()
    paginator.page_size = 3
    request = _request("page=1&size=999")

    page = _run(paginator.apaginate_queryset(qs, request))
    assert len(page) == 4


def test_base_pagination_apaginate_falls_back_to_sync():
    class CustomSync(BasePagination):
        def paginate_queryset(self, queryset, request, view=None):
            return list(queryset)[:1]

        def get_paginated_response(self, data):
            from rest_framework.response import Response

            return Response({"results": data})

    paginator = CustomSync()
    result = _run(paginator.apaginate_queryset([1, 2, 3], _request(), None))
    assert result == [1]


def test_async_page_previous_page_number():
    from restflow.pagination.pagination import AsyncPage, AsyncPaginator

    page = AsyncPage([1, 2, 3], 4, AsyncPaginator(count=20, per_page=3))
    assert page.previous_page_number() == 3


def test_async_page_next_page_number():
    from restflow.pagination.pagination import AsyncPage, AsyncPaginator

    page = AsyncPage([1, 2, 3], 1, AsyncPaginator(count=20, per_page=3))
    assert page.next_page_number() == 2


def test_page_number_pagination_apaginate_non_integer_page_raises():
    qs = _StubQuerySet(list(range(5)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = _request("page=abc")
    with pytest.raises(NotFound):
        _run(paginator.apaginate_queryset(qs, request))


def test_page_number_pagination_apaginate_zero_page_raises():
    qs = _StubQuerySet(list(range(5)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = _request("page=0")
    with pytest.raises(NotFound):
        _run(paginator.apaginate_queryset(qs, request))


def test_limit_offset_pagination_returns_none_when_limit_none():
    paginator = LimitOffsetPagination()
    paginator.default_limit = None
    request = _request()
    assert _run(paginator.apaginate_queryset(_StubQuerySet([]), request)) is None


def test_fast_page_number_size_query_param_invalid_value_falls_back():
    qs = _StubQuerySet(list(range(20)))

    class _Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = 10

    paginator = _Sized()
    paginator.page_size = 3
    request = _request("page=1&size=notanint")

    page = _run(paginator.apaginate_queryset(qs, request))
    assert len(page) == 3


def test_fast_page_number_size_query_param_without_max_returns_size():
    qs = _StubQuerySet(list(range(20)))

    class _Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = None

    paginator = _Sized()
    paginator.page_size = 3
    request = _request("page=1&size=7")

    page = _run(paginator.apaginate_queryset(qs, request))
    assert len(page) == 7


def test_fast_page_number_get_page_number_raises_on_non_integer():
    paginator = FastPageNumberPagination()
    request = _request("page=notanint")
    with pytest.raises(NotFound):
        paginator.get_page_number(request)


def test_fast_page_number_sync_returns_none_when_page_size_zero():
    paginator = FastPageNumberPagination()
    paginator.page_size = None
    request = _request()
    assert paginator.paginate_queryset([], request) is None


def test_fast_page_number_sync_overshooting_page_raises_when_empty():
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = _request("page=99")
    with pytest.raises(NotFound):
        paginator.paginate_queryset([1, 2], request)


def test_fast_page_number_async_returns_none_when_page_size_zero():
    paginator = FastPageNumberPagination()
    paginator.page_size = None
    request = _request()
    assert _run(paginator.apaginate_queryset(_StubQuerySet([]), request)) is None
