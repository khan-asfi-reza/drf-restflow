from asgiref.sync import sync_to_async
from rest_framework import status
from rest_framework.response import Response
from rest_framework.settings import api_settings


async def avalidate_or_is_valid_serializer(serializer, raise_exception=False):
    ais_valid = getattr(serializer, "ais_valid", None)
    if ais_valid is not None:
        return await ais_valid(raise_exception=raise_exception)
    return await sync_to_async(serializer.is_valid, thread_sensitive=True)(
        raise_exception=raise_exception
    )


async def asave_serializer(serializer):
    asave = getattr(serializer, "asave", None)
    if asave is not None:
        return await asave()
    return await sync_to_async(serializer.save, thread_sensitive=True)()


class AsyncCreateModelMixin:
    """
    Create a model instance, served via the async pipeline.
    """

    async def create(self, request, *args, **kwargs):
        """
        Validates the request body, persists the instance, and returns 201.
        """
        serializer = self.get_serializer(data=request.data)
        await avalidate_or_is_valid_serializer(serializer, raise_exception=True)
        await self.aperform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    async def aperform_create(self, serializer):
        """
        Saves the new instance, awaiting serializer.asave when available.
        """
        await asave_serializer(serializer)

    def get_success_headers(self, data):
        """
        Returns the headers that should be set on the 201 response.
        """
        try:
            return {"Location": str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}


class AsyncListModelMixin:
    """
    List a queryset, served via the async pipeline.
    """

    async def list(self, request, *args, **kwargs):
        """
        Returns a serialized, optionally paginated list of objects.
        """
        afilter = getattr(self, "afilter_queryset", None)
        if afilter is not None:
            queryset = await afilter(self.get_queryset())
        else:
            queryset = await sync_to_async(
                self.filter_queryset, thread_sensitive=True
            )(self.get_queryset())
        page = await self.apaginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AsyncRetrieveModelMixin:
    """
    Retrieve a model instance, served via the async pipeline.
    """

    async def retrieve(self, request, *args, **kwargs):
        """
        Returns the serialized representation of a single object.
        """
        instance = await self.aget_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class AsyncUpdateModelMixin:
    """
    Update a model instance, served via the async pipeline.
    """

    async def update(self, request, *args, **kwargs):
        """
        Validates the request body, persists the changes, and returns the
        updated representation.
        """
        partial = kwargs.pop("partial", False)
        instance = await self.aget_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial
        )
        await avalidate_or_is_valid_serializer(serializer, raise_exception=True)
        await self.aperform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    async def aperform_update(self, serializer):
        """
        Saves the updated instance, awaiting serializer.asave when available.
        """
        await asave_serializer(serializer)

    async def partial_update(self, request, *args, **kwargs):
        """
        Runs update() with partial=True so PATCH semantics apply.
        """
        kwargs["partial"] = True
        return await self.update(request, *args, **kwargs)


class AsyncDestroyModelMixin:
    """
    Destroy a model instance, served via the async pipeline.
    """

    async def destroy(self, request, *args, **kwargs):
        """
        Deletes the resolved instance and returns 204.
        """
        instance = await self.aget_object()
        await self.aperform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    async def aperform_destroy(self, instance):
        """
        Deletes the instance, preferring instance.adelete when available.
        """
        adelete = getattr(instance, "adelete", None)
        if adelete is not None:
            await adelete()
        else:
            await sync_to_async(instance.delete, thread_sensitive=True)()

