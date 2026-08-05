from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.settings import api_settings

from restflow.views.views import aserializer_data

if TYPE_CHECKING:
    from restflow.views.generics import AsyncGenericAPIView
    from restflow.views.viewsets import GenericViewSet

    _SyncCRUDMixinBase = GenericViewSet
    _AsyncCRUDMixinBase = AsyncGenericAPIView
else:
    _SyncCRUDMixinBase = object
    _AsyncCRUDMixinBase = object


async def asave_serializer(serializer: BaseSerializer[Any]) -> Any:
    asave = getattr(serializer, "asave", None)
    if asave is not None:
        return await asave()
    return await sync_to_async(serializer.save, thread_sensitive=True)()


class CreateModelMixin(_SyncCRUDMixinBase):
    def create(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Validates the request body, persists the instance, and returns 201.
        """
        serializer = self.validated_serializer()
        self.perform_create(serializer)
        return self.serialized_response(
            serializer.instance,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """
        Saves the new instance.
        """
        serializer.save()

    def get_success_headers(self, data: Any) -> dict[str, str]:
        """
        Returns the headers that should be set on the 201 response.
        """
        try:
            return {"Location": str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}


class ListModelMixin(_SyncCRUDMixinBase):

    def list(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Returns a serialized, optionally paginated list of objects.
        """
        queryset = self.filter_queryset(self.get_queryset())
        return self.paginated_response(queryset)


class RetrieveModelMixin(_SyncCRUDMixinBase):

    def retrieve(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Returns the serialized representation of a single object.
        """
        instance = self.get_object()
        return self.serialized_response(instance)


class UpdateModelMixin(_SyncCRUDMixinBase):

    def update(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Validates the request body, persists the changes, and returns the
        updated representation.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.validated_serializer(
            instance=instance, partial=partial
        )
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return self.serialized_response(serializer.instance)

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """
        Saves the updated instance.
        """
        serializer.save()

    def partial_update(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Runs update() with partial=True so PATCH semantics apply.
        """
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class DestroyModelMixin(_SyncCRUDMixinBase):

    def destroy(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Deletes the resolved instance and returns 204.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance: Any) -> None:
        """
        Deletes the instance.
        """
        instance.delete()


class AsyncCreateModelMixin(_AsyncCRUDMixinBase):

    async def create(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Validates the request body, persists the instance, and returns 201.
        """
        serializer = await self.avalidated_serializer()
        await self.aperform_create(serializer)
        data = await aserializer_data(serializer)
        return await self.aserialized_response(
            serializer.instance,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(data),
        )

    async def aperform_create(
        self, serializer: BaseSerializer[Any]
    ) -> None:
        """
        Saves the new instance, awaiting serializer.asave when available.
        """
        await asave_serializer(serializer)

    def get_success_headers(self, data: Any) -> dict[str, str]:
        """
        Returns the headers that should be set on the 201 response.
        """
        try:
            return {"Location": str(data[api_settings.URL_FIELD_NAME])}
        except (TypeError, KeyError):
            return {}


class AsyncListModelMixin(_AsyncCRUDMixinBase):

    async def list(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
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
        return await self.apaginated_response(queryset)


class AsyncRetrieveModelMixin(_AsyncCRUDMixinBase):

    async def retrieve(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Returns the serialized representation of a single object.
        """
        instance = await self.aget_object()
        return await self.aserialized_response(instance)


class AsyncUpdateModelMixin(_AsyncCRUDMixinBase):

    async def update(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Validates the request body, persists the changes, and returns the
        updated representation.
        """
        partial = kwargs.pop("partial", False)
        instance = await self.aget_object()
        serializer = await self.avalidated_serializer(
            instance=instance, partial=partial
        )
        await self.aperform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return await self.aserialized_response(serializer.instance)

    async def aperform_update(
        self, serializer: BaseSerializer[Any]
    ) -> None:
        """
        Saves the updated instance, awaiting serializer.asave when available.
        """
        await asave_serializer(serializer)

    async def partial_update(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Runs update() with partial=True so PATCH semantics apply.
        """
        kwargs["partial"] = True
        return await self.update(request, *args, **kwargs)


class AsyncDestroyModelMixin(_AsyncCRUDMixinBase):

    async def destroy(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Deletes the resolved instance and returns 204.
        """
        instance = await self.aget_object()
        await self.aperform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    async def aperform_destroy(self, instance: Any) -> None:
        """
        Deletes the instance, preferring instance.adelete when available.
        """
        adelete = getattr(instance, "adelete", None)
        if adelete is not None:
            await adelete()
        else:
            await sync_to_async(instance.delete, thread_sensitive=True)()
