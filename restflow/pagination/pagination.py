import math

from asgiref.sync import sync_to_async
from django.utils.translation import gettext_lazy as _
from rest_framework import pagination as drf_pagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.utils.urls import remove_query_param, replace_query_param


class BasePagination(drf_pagination.BasePagination):
    """
    All pagination classes should extend BasePagination.
    Adds an async apaginate_queryset hook that defaults to running the sync paginate_queryset in a thread.
    """

    async def apaginate_queryset(self, queryset, request, view=None):
        """Returns a list of items for a single page of the queryset, or None if pagination is disabled."""
        return await sync_to_async(
            self.paginate_queryset, thread_sensitive=True
        )(queryset, request, view)


class AsyncPage:
    def __init__(self, object_list, number, paginator):
        self.object_list = object_list
        self.number = number
        self.paginator = paginator

    def has_next(self):
        return self.number < self.paginator.num_pages

    def has_previous(self):
        return self.number > 1

    def next_page_number(self):
        return self.number + 1

    def previous_page_number(self):
        return self.number - 1

    def __iter__(self):
        return iter(self.object_list)

    def __len__(self):
        return len(self.object_list)


class AsyncPaginator:
    def __init__(self, count, per_page):
        self.count = count
        self.per_page = per_page
        self.num_pages = max(1, math.ceil(count / per_page)) if count else 1


class PageNumberPagination(BasePagination, drf_pagination.PageNumberPagination):
    """
    A simple page number based style that supports page numbers as query parameters.
    Adds an async apaginate_queryset that uses async ORM (acount, async iteration) instead of sync_to_async.
    """
    async def apaginate_queryset(self, queryset, request, view=None):
        """Returns a list of items for the requested page, or None if pagination is disabled."""
        self.request = request
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        count = await queryset.acount()
        paginator = AsyncPaginator(count=count, per_page=page_size)
        page_number = self.get_page_number(request, paginator)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError) as exc:
            msg = self.invalid_page_message.format(
                page_number=page_number, message=str(exc)
            )
            raise NotFound(msg) from exc

        if page_number < 1:
            msg = self.invalid_page_message.format(
                page_number=page_number,
                message=_("Page number must be 1 or greater."),
            )
            raise NotFound(msg)
        if count > 0 and page_number > paginator.num_pages:
            msg = self.invalid_page_message.format(
                page_number=page_number,
                message=_("That page contains no results."),
            )
            raise NotFound(msg)

        offset = (page_number - 1) * page_size
        sliced = queryset[offset : offset + page_size]
        object_list = [obj async for obj in sliced]
        self.page = AsyncPage(object_list, page_number, paginator)
        if paginator.num_pages > 1 and self.template is not None:
            self.display_page_controls = True
        return list(self.page)


class LimitOffsetPagination(BasePagination, drf_pagination.LimitOffsetPagination):
    """
    A limit/offset based style.
    Adds an async apaginate_queryset that uses async ORM (acount, async iteration) instead of sync_to_async.
    """
    async def apaginate_queryset(self, queryset, request, view=None):
        """Returns a list of items for the current limit/offset window, or None if pagination is disabled."""
        self.request = request
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.count = await queryset.acount()
        self.offset = self.get_offset(request)
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True
        if self.count == 0 or self.offset > self.count:
            return []

        sliced = queryset[self.offset : self.offset + self.limit]
        return [obj async for obj in sliced]


class CursorPagination(BasePagination, drf_pagination.CursorPagination):
    """
    The cursor pagination implementation is necessarily complex.
    Inherits DRF's sync paginate_queryset; the async surface defaults to sync_to_async.
    """


class FastPageNumberPagination(BasePagination):
    """
    Page number pagination that skips the COUNT(*) query.
    Determines whether a next page exists by checking if the current page is full, and omits the count field from the response.
    """

    page_size = api_settings.PAGE_SIZE
    page_query_param = "page"
    page_size_query_param = None
    max_page_size = None
    invalid_page_message = _("Invalid page.")

    def get_page_size(self, request):
        """Returns the page size for the current request."""
        if self.page_size_query_param:
            try:
                size = int(request.query_params[self.page_size_query_param])
            except (KeyError, TypeError, ValueError):
                size = None
            if size is not None and size > 0:
                if self.max_page_size:
                    return min(size, self.max_page_size)
                return size
        return self.page_size

    def get_page_number(self, request):
        """Returns the requested page number from the query string."""
        raw = request.query_params.get(self.page_query_param, 1)
        try:
            page = int(raw)
        except (TypeError, ValueError) as exc:
            raise NotFound(self.invalid_page_message) from exc
        if page < 1:
            raise NotFound(self.invalid_page_message)
        return page

    def paginate_queryset(self, queryset, request, view=None):
        """Returns a list of items for the requested page without issuing a COUNT(*)."""
        self.request = request
        page_size = self.get_page_size(request)
        if not page_size:
            return None
        self._page_size = page_size
        self.page_number = self.get_page_number(request)
        offset = (self.page_number - 1) * page_size
        items = list(queryset[offset : offset + page_size + 1])
        self.has_next = len(items) > page_size
        items = items[:page_size]
        if not items and self.page_number > 1:
            raise NotFound(self.invalid_page_message)
        return items

    async def apaginate_queryset(self, queryset, request, view=None):
        """Async variant of paginate_queryset using async ORM iteration."""
        self.request = request
        page_size = self.get_page_size(request)
        if not page_size:
            return None
        self._page_size = page_size
        self.page_number = self.get_page_number(request)
        offset = (self.page_number - 1) * page_size
        sliced = queryset[offset : offset + page_size + 1]
        items = [obj async for obj in sliced]
        self.has_next = len(items) > page_size
        items = items[:page_size]
        if not items and self.page_number > 1:
            raise NotFound(self.invalid_page_message)
        return items

    def get_paginated_response(self, data):
        """Returns the paginated response with results, next, and previous links."""
        return Response(
            {
                "results": data,
                "next": self._build_link(self.page_number + 1)
                if self.has_next
                else None,
                "previous": self._build_link(self.page_number - 1)
                if self.page_number > 1
                else None,
            }
        )

    def _build_link(self, page_number):
        url = self.request.build_absolute_uri()
        if page_number == 1:
            return remove_query_param(url, self.page_query_param)
        return replace_query_param(url, self.page_query_param, page_number)
