from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework import generics as drf_generics

from restflow.views.mixins import (
    AsyncCreateModelMixin,
    AsyncDestroyModelMixin,
    AsyncListModelMixin,
    AsyncRetrieveModelMixin,
    AsyncUpdateModelMixin,
)
from restflow.views.views import AsyncAPIView


class AsyncGenericAPIView(AsyncAPIView, drf_generics.GenericAPIView):
    """
    Base class for all other generic views, with an async dispatch loop.

    Adds aget_object, afilter_queryset, and apaginate_queryset, falling back
    to sync_to_async for sync filter backends and paginators that do not expose
    async hooks.
    """

    async def afilter_queryset(self, queryset):
        """
        Returns a filtered queryset, awaiting any async-aware filter backends.
        """
        for backend_class in list(self.filter_backends):
            backend = backend_class()
            afilter = getattr(backend, "afilter_queryset", None)
            if afilter is not None:
                queryset = await afilter(self.request, queryset, self)
            else:
                queryset = await sync_to_async(
                    backend.filter_queryset, thread_sensitive=True
                )(self.request, queryset, self)
        return queryset

    async def apaginate_queryset(self, queryset):
        """
        Returns a single page of results, or None if pagination is disabled.
        """
        if self.paginator is None:
            return None
        apag = getattr(self.paginator, "apaginate_queryset", None)
        if apag is not None:
            return await apag(queryset, self.request, view=self)
        return await sync_to_async(
            self.paginator.paginate_queryset, thread_sensitive=True
        )(queryset, self.request, view=self)

    async def aget_object(self):
        """
        Returns the object the view is displaying, looked up via queryset.aget.
        """
        queryset = await self.afilter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.kwargs, (
            f"Expected view {self.__class__.__name__} to be called with "
            f'a URL keyword argument named "{lookup_url_kwarg}". '
            "Fix your URL conf, or set the `.lookup_field` attribute "
            "on the view correctly."
        )
        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        try:
            obj = await queryset.aget(**filter_kwargs)
        except (TypeError, ValueError, ValidationError) as exc:
            raise Http404 from exc
        except queryset.model.DoesNotExist as exc:
            raise Http404 from exc
        await self.acheck_object_permissions(self.request, obj)
        return obj


class AsyncCreateAPIView(AsyncCreateModelMixin, AsyncGenericAPIView):
    """
    Concrete view for creating a model instance, served via the async pipeline.
    """

    async def post(self, request, *args, **kwargs):
        return await self.create(request, *args, **kwargs)


class AsyncListAPIView(AsyncListModelMixin, AsyncGenericAPIView):
    """
    Concrete view for listing a queryset, served via the async pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.list(request, *args, **kwargs)


class AsyncRetrieveAPIView(AsyncRetrieveModelMixin, AsyncGenericAPIView):
    """
    Concrete view for retrieving a model instance, served via the async
    pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.retrieve(request, *args, **kwargs)


class AsyncDestroyAPIView(AsyncDestroyModelMixin, AsyncGenericAPIView):
    """
    Concrete view for deleting a model instance, served via the async pipeline.
    """

    async def delete(self, request, *args, **kwargs):
        return await self.destroy(request, *args, **kwargs)


class AsyncUpdateAPIView(AsyncUpdateModelMixin, AsyncGenericAPIView):
    """
    Concrete view for updating a model instance, served via the async pipeline.
    """

    async def put(self, request, *args, **kwargs):
        return await self.update(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_update(request, *args, **kwargs)


class AsyncListCreateAPIView(
    AsyncListModelMixin, AsyncCreateModelMixin, AsyncGenericAPIView
):
    """
    Concrete view for listing a queryset or creating a model instance, served
    via the async pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.list(request, *args, **kwargs)

    async def post(self, request, *args, **kwargs):
        return await self.create(request, *args, **kwargs)


class AsyncRetrieveUpdateAPIView(
    AsyncRetrieveModelMixin, AsyncUpdateModelMixin, AsyncGenericAPIView
):
    """
    Concrete view for retrieving or updating a model instance, served via the
    async pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.retrieve(request, *args, **kwargs)

    async def put(self, request, *args, **kwargs):
        return await self.update(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_update(request, *args, **kwargs)


class AsyncRetrieveDestroyAPIView(
    AsyncRetrieveModelMixin, AsyncDestroyModelMixin, AsyncGenericAPIView
):
    """
    Concrete view for retrieving or deleting a model instance, served via the
    async pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.retrieve(request, *args, **kwargs)

    async def delete(self, request, *args, **kwargs):
        return await self.destroy(request, *args, **kwargs)


class AsyncRetrieveUpdateDestroyAPIView(
    AsyncRetrieveModelMixin,
    AsyncUpdateModelMixin,
    AsyncDestroyModelMixin,
    AsyncGenericAPIView,
):
    """
    Concrete view for retrieving, updating, or deleting a model instance,
    served via the async pipeline.
    """

    async def get(self, request, *args, **kwargs):
        return await self.retrieve(request, *args, **kwargs)

    async def put(self, request, *args, **kwargs):
        return await self.update(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_update(request, *args, **kwargs)

    async def delete(self, request, *args, **kwargs):
        return await self.destroy(request, *args, **kwargs)
