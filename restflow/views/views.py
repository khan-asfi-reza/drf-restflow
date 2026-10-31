from typing import TYPE_CHECKING, Any, Protocol, cast

from asgiref.sync import sync_to_async
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.utils.functional import classproperty
from rest_framework import exceptions, status
from rest_framework.pagination import BasePagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView as DRFAPIView

from restflow.helpers import maybe_await
from restflow.permissions import has_object_permission, has_permission
from restflow.throttling import throttler_allow_request

if TYPE_CHECKING:
    from rest_framework.authentication import BaseAuthentication
    from rest_framework.metadata import BaseMetadata
    from rest_framework.request import ForcedAuthentication

    _HelpersBase = DRFAPIView

    class _AuthenticatableRequest(Protocol):
        _authenticator: "BaseAuthentication | ForcedAuthentication | None"

        def _not_authenticated(self) -> None: ...
else:
    _HelpersBase = object


def perform_post_fetches(
    items: Any, post_fetches: Any, *, many: bool
) -> Any:
    if not post_fetches:
        return items
    target = items if many else [items]
    for fetcher in post_fetches:
        fetcher.fetch(target)
    return target if many else target[0]


async def aperform_post_fetches(
    items: Any, post_fetches: Any, *, many: bool
) -> Any:
    if not post_fetches:
        return items
    target = items if many else [items]
    for fetcher in post_fetches:
        afetch = getattr(fetcher, "afetch", None)
        if afetch is not None:
            await afetch(target)
        else:
            await sync_to_async(fetcher.fetch, thread_sensitive=True)(target)
    return target if many else target[0]


async def aserializer_data(serializer: BaseSerializer[Any]) -> Any:
    """Resolve serializer.data in a thread so it can reach the database.

    Building a representation walks lazy querysets and follows relations,
    both of which open a cursor. Async handlers cannot do that on the event
    loop, so the whole render step runs through sync_to_async.
    """
    return await sync_to_async(_read_serializer_data, thread_sensitive=True)(
        serializer
    )


def _read_serializer_data(serializer: BaseSerializer[Any]) -> Any:
    return serializer.data


def _no_actions(_request: Any, _view: Any) -> dict[str, Any]:
    return {}


class APIViewHelpersMixin(_HelpersBase):

    serializer_class: type[BaseSerializer[Any]] | None = None
    request_serializer_class: type[BaseSerializer[Any]] | None = None
    response_serializer_class: type[BaseSerializer[Any]] | None = None
    pagination_class: type[BasePagination] | None = None

    def get_context(self) -> dict[str, Any]:
        """
        Returns the context that should be used by the serializer.
        """
        return {"request": self.request, "view": self}

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        """
        Returns the class used to serialize the response payload.
        """
        return cast("type[BaseSerializer[Any]]", self.serializer_class)

    def get_request_serializer_class(self) -> type[BaseSerializer[Any]]:
        """
        Returns the class used to validate the request body.
        """
        return self.request_serializer_class or self.get_serializer_class()

    def get_response_serializer_class(self) -> type[BaseSerializer[Any]]:
        """
        Returns the class used to serialize the response payload.
        """
        return self.response_serializer_class or self.get_serializer_class()

    def get_pagination_class(self) -> type[BasePagination] | None:
        """
        Returns the pagination class that should be used for list responses.
        """
        return self.pagination_class

    def get_serializer(
        self,
        *args: Any,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        direction: str | None = None,
        **kwargs: Any,
    ) -> BaseSerializer[Any]:
        """
        Returns the serializer instance that should be used for the action.
        """
        if serializer_class is None:
            if direction == "request":
                serializer_class = self.get_request_serializer_class()
            elif direction == "response":
                serializer_class = self.get_response_serializer_class()
            else:
                serializer_class = self.get_serializer_class()
        if serializer_class is None:
            msg = (
                f"{self.__class__.__name__} requires `serializer_class` "
                "or a `serializer_class=` keyword argument."
            )
            raise ImproperlyConfigured(msg)
        kwargs.setdefault("context", self.get_context())
        return serializer_class(*args, **kwargs)

    def validated_serializer(
        self,
        *,
        data: Any = None,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        **kwargs: Any,
    ) -> BaseSerializer[Any]:
        """
        Returns a serializer with the request data validated.
        """
        if data is None:
            data = self.request.data
        ser = self.get_serializer(
            data=data,
            serializer_class=serializer_class,
            direction="request",
            **kwargs,
        )
        ser.is_valid(raise_exception=True)
        return ser

    def build_options_metadata(self, request: Request) -> Any:
        """
        Returns the OPTIONS metadata for the view.

        Every restflow view exposes get_serializer, so DRF's metadata class
        reaches it even on views that never declare a serializer_class. Those
        views still have to answer OPTIONS, so the serializer-derived actions
        are dropped instead of failing the request.
        """
        metadata_class = cast("type[BaseMetadata]", self.metadata_class)
        metadata = metadata_class()
        try:
            return metadata.determine_metadata(request, self)
        except ImproperlyConfigured:
            metadata.determine_actions = _no_actions  # pyright: ignore[reportAttributeAccessIssue]
            return metadata.determine_metadata(request, self)

    def serialized_response(
        self,
        instance: Any,
        *,
        many: bool = False,
        status: int = status.HTTP_200_OK,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        post_fetches: Any = None,
        headers: Any = None,
    ) -> Response:
        """
        Returns a Response containing the serialized instance.
        """
        instance = perform_post_fetches(instance, post_fetches, many=many)
        ser = self.get_serializer(
            instance,
            many=many,
            serializer_class=serializer_class,
            direction="response",
        )
        return Response(ser.data, status=status, headers=headers)

    def paginated_response(
        self,
        queryset: Any,
        *,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        pagination_class: type[BasePagination] | None = None,
        post_fetches: Any = None,
        headers: Any = None,
    ) -> Response:
        """
        Returns a paginated Response for the given queryset.
        """
        paginator_cls = pagination_class or self.get_pagination_class()
        if paginator_cls is None:
            ser = self.get_serializer(
                queryset,
                many=True,
                serializer_class=serializer_class,
                direction="response",
            )
            return Response(ser.data, headers=headers)
        paginator = paginator_cls()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        if page is None:
            ser = self.get_serializer(
                queryset,
                many=True,
                serializer_class=serializer_class,
                direction="response",
            )
            return Response(ser.data, headers=headers)
        page = perform_post_fetches(page, post_fetches, many=True)
        ser = self.get_serializer(
            page,
            many=True,
            serializer_class=serializer_class,
            direction="response",
        )
        response = paginator.get_paginated_response(ser.data)
        if headers:
            for key, value in headers.items():
                response[key] = value
        return response



class APIView(APIViewHelpersMixin, DRFAPIView):

    def options(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Handles the OPTIONS request, tolerating views without a
        serializer_class.
        """
        if self.metadata_class is None:
            return self.http_method_not_allowed(request, *args, **kwargs)
        return Response(
            self.build_options_metadata(request), status=status.HTTP_200_OK
        )

class AsyncAPIView(APIViewHelpersMixin, DRFAPIView):

    @classproperty
    def view_is_async(cls):  # noqa: N805  # pyright: ignore[reportIncompatibleVariableOverride]
        return True

    async def dispatch(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Async equivalent of APIView.dispatch.
        """
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers

        try:
            await self.ainitial(request, *args, **kwargs)
            if cast(str, request.method).lower() in self.http_method_names:
                handler = getattr(
                    self,
                    cast(str, request.method).lower(),
                    self.http_method_not_allowed,
                )
            else:
                handler = self.http_method_not_allowed
            response = await maybe_await(handler(request, *args, **kwargs))
        except Exception as exc:
            response = await self.ahandle_exception(exc)

        self.response = await self.afinalize_response(
            request, response, *args, **kwargs
        )
        return self.response

    async def options(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Async equivalent of APIView.options. Metadata generation inspects the
        serializer and can reach the database, so it runs in a thread instead
        of on the event loop.
        """
        if self.metadata_class is None:
            return await maybe_await(
                self.http_method_not_allowed(request, *args, **kwargs)
            )
        data = await sync_to_async(
            self.build_options_metadata, thread_sensitive=True
        )(request)
        return Response(data, status=status.HTTP_200_OK)

    async def ainitial(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> None:
        """
        Runs anything that needs to occur prior to calling the method handler.
        """
        self.format_kwarg = self.get_format_suffix(**kwargs)

        neg = self.perform_content_negotiation(request)
        request.accepted_renderer, request.accepted_media_type = neg

        version, scheme = self.determine_version(request, *args, **kwargs)
        request.version, request.versioning_scheme = version, scheme

        await self.aperform_authentication(request)
        await self.acheck_permissions(request)
        await self.acheck_throttles(request)

    async def aperform_authentication(self, request: Request) -> None:
        """
        Performs authentication on the incoming request.
        """
        internal = cast("_AuthenticatableRequest", request)
        for authenticator in request.authenticators or ():
            aauth = getattr(authenticator, "aauthenticate", None)
            try:
                if aauth is not None:
                    user_auth_tuple = await aauth(request)
                else:
                    user_auth_tuple = await sync_to_async(
                        authenticator.authenticate, thread_sensitive=True
                    )(request)
            except exceptions.APIException:
                internal._not_authenticated()
                raise
            if user_auth_tuple is not None:
                internal._authenticator = authenticator
                request.user, request.auth = user_auth_tuple
                return
        internal._not_authenticated()

    async def acheck_permissions(self, request: Request) -> None:
        """
        Checks if the request should be permitted, raising on failure.
        """
        for permission in self.get_permissions():
            allowed = await maybe_await(
                has_permission(permission, request, self)
            )
            if not allowed:
                self.permission_denied(
                    request,
                    message=getattr(permission, "message", None),
                    code=getattr(permission, "code", None),
                )

    async def acheck_object_permissions(
        self, request: Request, obj: Any
    ) -> None:
        """
        Checks if the request should be permitted for a given object.
        """
        for permission in self.get_permissions():
            allowed = await maybe_await(
                has_object_permission(permission, request, self, obj)
            )
            if not allowed:
                self.permission_denied(
                    request,
                    message=getattr(permission, "message", None),
                    code=getattr(permission, "code", None),
                )

    async def acheck_throttles(self, request: Request) -> None:
        """
        Checks the throttles on the incoming request.
        """
        throttle_durations = []
        for throttle in self.get_throttles():
            allowed = await maybe_await(
                throttler_allow_request(throttle, request, self)
            )
            if not allowed:
                throttle_durations.append(throttle.wait())

        if throttle_durations:
            durations = [d for d in throttle_durations if d is not None]
            duration = max(durations, default=None)
            self.throttled(request, cast(float, duration))

    async def ahandle_exception(self, exc: Exception) -> Response:
        """
        Handles any exception that occurs, by returning an appropriate response,
        or re-raising the error.
        """
        if isinstance(
            exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)
        ):
            auth_header = self.get_authenticate_header(self.request)
            if auth_header:
                exc.auth_header = auth_header  # pyright: ignore[reportAttributeAccessIssue]
            else:
                exc.status_code = status.HTTP_403_FORBIDDEN

        exception_handler = self.get_exception_handler()
        context = self.get_exception_handler_context()
        response = await maybe_await(exception_handler(exc, context))
        if response is None:
            self.raise_uncaught_exception(exc)

        response.exception = True
        return response

    async def afinalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Returns the final response object after any processing.
        """
        return self.finalize_response(request, response, *args, **kwargs)

    async def avalidated_serializer(
        self,
        *,
        data: Any = None,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        **kwargs: Any,
    ) -> BaseSerializer[Any]:
        """
        Returns a serializer with the request data validated, awaiting ais_valid
        when available.
        """
        if data is None:
            data = self.request.data
        ser = self.get_serializer(
            data=data,
            serializer_class=serializer_class,
            direction="request",
            **kwargs,
        )
        ais_valid = getattr(ser, "ais_valid", None)
        if ais_valid is not None:
            await ais_valid(raise_exception=True)
        else:
            await sync_to_async(ser.is_valid, thread_sensitive=True)(
                raise_exception=True
            )
        return ser

    async def aserialized_response(
        self,
        instance: Any,
        *,
        many: bool = False,
        status: int = status.HTTP_200_OK,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        post_fetches: Any = None,
        headers: Any = None,
    ) -> Response:
        """
        Returns a Response containing the serialized instance, awaiting any
        post-fetch helpers.
        """
        instance = await aperform_post_fetches(instance, post_fetches, many=many)
        ser = self.get_serializer(
            instance,
            many=many,
            serializer_class=serializer_class,
            direction="response",
        )
        data = await aserializer_data(ser)
        return Response(data, status=status, headers=headers)

    async def apaginated_response(
        self,
        queryset: Any,
        *,
        serializer_class: type[BaseSerializer[Any]] | None = None,
        pagination_class: type[BasePagination] | None = None,
        post_fetches: Any = None,
        headers: Any = None,
    ) -> Response:
        """
        Returns a paginated Response for the given queryset, using async
        paginator hooks when available.
        """
        paginator_cls = pagination_class or self.get_pagination_class()
        if paginator_cls is None:
            ser = self.get_serializer(
                queryset,
                many=True,
                serializer_class=serializer_class,
                direction="response",
            )
            data = await aserializer_data(ser)
            return Response(data, headers=headers)
        paginator = paginator_cls()
        apaginate = getattr(paginator, "apaginate_queryset", None)
        if apaginate is not None:
            page = await apaginate(queryset, self.request, view=self)
        else:
            page = await sync_to_async(
                paginator.paginate_queryset, thread_sensitive=True
            )(queryset, self.request, view=self)
        if page is None:
            ser = self.get_serializer(
                queryset,
                many=True,
                serializer_class=serializer_class,
                direction="response",
            )
            data = await aserializer_data(ser)
            return Response(data, headers=headers)
        page = await aperform_post_fetches(page, post_fetches, many=True)
        ser = self.get_serializer(
            page,
            many=True,
            serializer_class=serializer_class,
            direction="response",
        )
        data = await aserializer_data(ser)
        response = paginator.get_paginated_response(data)
        if headers:
            for key, value in headers.items():
                response[key] = value
        return response
