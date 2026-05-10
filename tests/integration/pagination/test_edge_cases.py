import asyncio

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from restflow.pagination import (
    BasePagination,
    CursorPagination,
    FastPageNumberPagination,
    LimitOffsetPagination,
    PageNumberPagination,
)


def run_coro(coro):
    return asyncio.run(coro)


def make_request(query=""):
    factory = RequestFactory()
    return Request(factory.get(f"/?{query}"))


class StubAsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


class StubQuerySet:
    def __init__(self, items):
        self._items = list(items)

    async def acount(self):
        return len(self._items)

    def __getitem__(self, key):
        sliced = StubQuerySet(self._items)
        sliced._items = self._items[key]
        return sliced

    def __iter__(self):
        return iter(self._items)

    def __aiter__(self):
        return StubAsyncIter(self._items).__aiter__()


def test_page_number_with_zero_count_returns_empty_page():
    qs = StubQuerySet([])
    paginator = PageNumberPagination()
    paginator.page_size = 5
    request = make_request("page=1")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert page == []


def test_page_number_negative_page_raises():
    qs = StubQuerySet([1, 2])
    paginator = PageNumberPagination()
    paginator.page_size = 1
    request = make_request("page=-1")
    with pytest.raises(NotFound):
        run_coro(paginator.apaginate_queryset(qs, request))


def test_limit_offset_with_zero_limit_uses_default_limit():
    qs = StubQuerySet([1, 2, 3])
    paginator = LimitOffsetPagination()
    paginator.default_limit = 2
    request = make_request("limit=0&offset=0")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert page == [1, 2]


def test_limit_offset_with_negative_offset_treated_as_zero():
    qs = StubQuerySet([1, 2, 3])
    paginator = LimitOffsetPagination()
    paginator.default_limit = 2
    request = make_request("limit=2&offset=-3")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert page == [1, 2]


def test_limit_offset_when_count_zero_returns_empty():
    qs = StubQuerySet([])
    paginator = LimitOffsetPagination()
    paginator.default_limit = 5
    request = make_request("limit=5&offset=0")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert page == []


def test_fast_page_invalid_negative_page_raises():
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = make_request("page=-5")
    with pytest.raises(NotFound):
        paginator.get_page_number(request)


def test_fast_page_first_page_no_previous_link():
    qs = StubQuerySet(list(range(3)))
    paginator = FastPageNumberPagination()
    paginator.page_size = 3
    request = make_request("page=1")
    run_coro(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([0, 1, 2])
    assert response.data["previous"] is None


def test_base_pagination_can_subclass_only_async_path():
    class AsyncBase(BasePagination):
        async def apaginate_queryset(self, queryset, request, view=None):
            return list(queryset)[:1]

        def get_paginated_response(self, data):
            from rest_framework.response import Response

            return Response(data)

    paginator = AsyncBase()
    page = run_coro(paginator.apaginate_queryset([1, 2, 3], make_request()))
    assert page == [1]


def test_page_number_pagination_skips_count_when_page_size_none():
    paginator = PageNumberPagination()
    paginator.page_size = None
    page = run_coro(paginator.apaginate_queryset(StubQuerySet([1, 2]), make_request()))
    assert page is None


def test_fast_page_size_query_param_with_negative_value_uses_default():
    qs = StubQuerySet(list(range(10)))

    class Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = 10

    paginator = Sized()
    paginator.page_size = 3
    request = make_request("page=1&size=-1")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert len(page) == 3


def test_fast_page_size_query_param_when_zero_uses_default():
    qs = StubQuerySet(list(range(10)))

    class Sized(FastPageNumberPagination):
        page_size_query_param = "size"
        max_page_size = 10

    paginator = Sized()
    paginator.page_size = 3
    request = make_request("page=1&size=0")
    page = run_coro(paginator.apaginate_queryset(qs, request))
    assert len(page) == 3


def test_limit_offset_returns_none_when_default_limit_is_none():
    paginator = LimitOffsetPagination()
    paginator.default_limit = None
    request = make_request()
    assert run_coro(paginator.apaginate_queryset(StubQuerySet([]), request)) is None


def test_page_number_paginated_response_has_next_and_previous_url():
    qs = StubQuerySet(list(range(10)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = make_request("page=2")
    run_coro(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([3, 4, 5])
    assert "next" in response.data
    assert "previous" in response.data


def test_page_number_paginated_response_first_page_previous_none():
    qs = StubQuerySet(list(range(10)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = make_request("page=1")
    run_coro(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([0, 1, 2])
    assert response.data["previous"] is None


def test_page_number_paginated_response_last_page_next_none():
    qs = StubQuerySet(list(range(7)))
    paginator = PageNumberPagination()
    paginator.page_size = 3
    request = make_request("page=3")
    run_coro(paginator.apaginate_queryset(qs, request))
    response = paginator.get_paginated_response([6])
    assert response.data["next"] is None


def test_async_page_iter_yields_items():
    from restflow.pagination.pagination import AsyncPage, AsyncPaginator

    page = AsyncPage([1, 2, 3], 1, AsyncPaginator(count=3, per_page=3))
    assert list(page) == [1, 2, 3]
    assert len(page) == 3


def test_async_page_has_next_false_on_last_page():
    from restflow.pagination.pagination import AsyncPage, AsyncPaginator

    page = AsyncPage([1], 2, AsyncPaginator(count=2, per_page=1))
    assert page.has_next() is False
    assert page.has_previous() is True


def test_async_paginator_zero_count_yields_one_page():
    from restflow.pagination.pagination import AsyncPaginator

    paginator = AsyncPaginator(count=0, per_page=10)
    assert paginator.num_pages == 1


def test_cursor_pagination_falls_back_to_sync_via_async_hook():
    paginator = CursorPagination()
    qs = []
    request = make_request()
    result = run_coro(paginator.apaginate_queryset(qs, request))
    assert result is None or result == []
