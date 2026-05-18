from dataclasses import dataclass
from functools import update_wrapper
from typing import Any

import django
from django.utils.decorators import classonlymethod
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics as drf_generics
from rest_framework import viewsets as drf_viewsets

from restflow.views.generics import AsyncGenericAPIView
from restflow.views.mixins import (
    AsyncCreateModelMixin,
    AsyncDestroyModelMixin,
    AsyncListModelMixin,
    AsyncRetrieveModelMixin,
    AsyncUpdateModelMixin,
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from restflow.views.views import APIView, APIViewHelpersMixin, AsyncAPIView


@dataclass(frozen=True)
class ActionConfig:
    """
    Per-action override for a viewset. Each field is optional and falls through
    to the class-level attribute when None. Used as values in action_configs
    on AsyncViewSet and ViewSet subclasses.

        class UserViewSet(AsyncModelViewSet):
            serializer_class = UserSer
            queryset = User.objects.all()
            pagination_class = StandardPagination
            permission_classes = [IsAuthenticated]
            action_configs = {
                "list": ActionConfig(
                    serializer_class=UserListSer,
                    pagination_class=FastPageNumberPagination,
                    queryset=lambda self: User.objects.filter(
                        owner=self.request.user
                    ),
                ),
                "archive": ActionConfig(
                    queryset=User.objects.filter(is_archived=True),
                ),
                "destroy": ActionConfig(permission_classes=[IsAdminUser]),
            }

    The queryset field accepts either a static QuerySet or a callable with
    signature (self) -> QuerySet.
    """

    serializer_class: type | None = None
    request_serializer_class: type | None = None
    response_serializer_class: type | None = None
    permission_classes: list | tuple | None = None
    throttle_classes: list | tuple | None = None
    parser_classes: list | tuple | None = None
    renderer_classes: list | tuple | None = None
    pagination_class: type | None = None
    queryset: Any = None


class ActionConfigResolutionMixin:
    """
    Resolution helpers shared by sync and async viewsets.

    Reads the per-action ActionConfig from action_configs, falling back to
    the class-level attribute when the config does not override.
    """

    action_configs: dict = {}
    name = None
    description = None
    suffix = None
    detail = None
    basename = None

    def _action_config(self):
        return self.action_configs.get(getattr(self, "action", None))

    def get_serializer_class(self):
        """
        Returns the class used to serialize the response payload for the
        current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.serializer_class is not None:
            return cfg.serializer_class
        parent = getattr(super(), "get_serializer_class", None)
        if parent is not None:
            return parent()
        return self.serializer_class

    def get_request_serializer_class(self):
        """
        Returns the class used to validate the request body for the current
        action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.request_serializer_class is not None:
            return cfg.request_serializer_class
        parent = getattr(super(), "get_request_serializer_class", None)
        if parent is not None:
            return parent()
        return self.get_serializer_class()

    def get_response_serializer_class(self):
        """
        Returns the class used to serialize the response payload for the
        current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.response_serializer_class is not None:
            return cfg.response_serializer_class
        parent = getattr(super(), "get_response_serializer_class", None)
        if parent is not None:
            return parent()
        return self.get_serializer_class()

    def get_permissions(self):
        """
        Returns the list of permissions that this view requires for the current
        action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.permission_classes is not None:
            return [p() for p in cfg.permission_classes]
        return super().get_permissions()

    def get_throttles(self):
        """
        Returns the list of throttle instances for the current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.throttle_classes is not None:
            return [t() for t in cfg.throttle_classes]
        return super().get_throttles()

    def get_parsers(self):
        """
        Returns the list of parser instances for the current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.parser_classes is not None:
            return [p() for p in cfg.parser_classes]
        return super().get_parsers()

    def get_renderers(self):
        """
        Returns the list of renderer instances for the current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.renderer_classes is not None:
            return [r() for r in cfg.renderer_classes]
        return super().get_renderers()

    def get_pagination_class(self):
        """
        Returns the pagination class for the current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.pagination_class is not None:
            return cfg.pagination_class
        parent = getattr(super(), "get_pagination_class", None)
        if parent is not None:
            return parent()
        return getattr(self, "pagination_class", None)

    def get_queryset(self):
        """
        Returns the queryset that should be used for the current action.
        """
        cfg = self._action_config()
        if cfg is not None and cfg.queryset is not None:
            qs = cfg.queryset
            if callable(qs):
                return qs(self)
            if hasattr(qs, "all"):
                return qs.all()
            return qs
        parent = getattr(super(), "get_queryset", None)
        if parent is not None:
            return parent()
        msg = (
            f"{self.__class__.__name__} has no `queryset` and no "
            "`get_queryset()` method. Set `queryset` on the class, "
            "set `queryset` on an `action_configs[...]` ActionConfig, "
            "or override `get_queryset()`."
        )
        raise AssertionError(msg)

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            cls = self.get_pagination_class()
            self._paginator = cls() if cls is not None else None
        return self._paginator


class ViewSetMixin(ActionConfigResolutionMixin, drf_viewsets.ViewSetMixin):
    """
    Sync ViewSetMixin that honours an action_configs mapping.

    Mirrors AsyncViewSetMixin's resolution semantics on top of DRF's
    sync ViewSetMixin. Use ViewSet, GenericViewSet, ReadOnlyModelViewSet,
    or ModelViewSet for the concrete sync surface.
    """


class AsyncViewSetMixin(ActionConfigResolutionMixin, drf_viewsets.ViewSetMixin):
    """
    ViewSetMixin that returns an async closure from as_view().

    Honours an action_configs mapping so subclasses can override
    serializer_class, permission_classes, throttle_classes, parser_classes,
    renderer_classes, pagination_class, and queryset per action.
    """

    @classonlymethod
    def as_view(cls, actions=None, **initkwargs):  # noqa: N805
        """
        Returns an async view callable that binds the given actions map to
        HTTP method names and dispatches via the async pipeline.
        """
        if not actions:
            msg = (
                "The `actions` argument must be provided when calling "
                "`.as_view()` on a ViewSet. For example "
                "`.as_view({'get': 'list'})`"
            )
            raise TypeError(msg)
        actions = dict(actions)

        for key in initkwargs:
            if key in cls.http_method_names:
                msg = (
                    f"You tried to pass in the {key} method name as a "
                    f"keyword argument to {cls.__name__}(). Don't do that."
                )
                raise TypeError(msg)
            if not hasattr(cls, key):
                msg = f"{cls.__name__}() received an invalid keyword {key!r}"
                raise TypeError(msg)

        if "name" in initkwargs and "suffix" in initkwargs:
            msg = (
                f"{cls.__name__}() received both `name` and `suffix`, "
                "which are mutually exclusive arguments."
            )
            raise TypeError(msg)

        if "get" in actions and "head" not in actions:
            actions["head"] = actions["get"]

        async def view(request, *args, **kwargs):
            self = cls(**initkwargs)
            self.action_map = actions

            for method, action in actions.items():
                handler = getattr(self, action)
                setattr(self, method, handler)

            self.request = request
            self.args = args
            self.kwargs = kwargs

            return await self.dispatch(request, *args, **kwargs)

        update_wrapper(view, cls, updated=())
        update_wrapper(view, cls.dispatch, assigned=())

        view.cls = cls
        view.initkwargs = initkwargs
        view.actions = actions

        if django.VERSION >= (5, 1):
            view.login_required = False

        return csrf_exempt(view)


class ViewSet(ViewSetMixin, APIView):
    """
    The base sync ViewSet class. Does not provide any actions by default.

    Adds restflow's action_configs resolution and the sync APIView surface
    (serialized_response, paginated_response, validated_serializer).
    """


class GenericViewSet(
    ViewSetMixin, APIViewHelpersMixin, drf_generics.GenericAPIView
):
    """
    The sync GenericViewSet class. Does not provide any actions by default,
    but includes DRF's GenericAPIView base behaviour (get_object,
    filter_queryset, paginate_queryset) plus restflow's action_configs
    resolution and the validated_serializer / serialized_response /
    paginated_response helper surface.
    """


class ReadOnlyModelViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    """
    Sync viewset that provides default list() and retrieve() actions, served
    through restflow's serialized_response and paginated_response helpers so
    the request/response serializer split and post-fetches apply.
    """


class ModelViewSet(
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    """
    Sync viewset that provides default create(), retrieve(), update(),
    partial_update(), destroy(), and list() actions, all routed through
    restflow's helper surface (validated_serializer, serialized_response,
    paginated_response).
    """


class AsyncViewSet(AsyncViewSetMixin, AsyncAPIView):
    """
    The base ViewSet class with async dispatch. Does not provide any actions
    by default.
    """


class AsyncGenericViewSet(AsyncViewSetMixin, AsyncGenericAPIView):
    """
    The GenericViewSet class with async dispatch. Does not provide any actions
    by default, but does include the base set of generic view behavior such as
    aget_object, afilter_queryset, and apaginate_queryset.
    """


class AsyncReadOnlyModelViewSet(
    AsyncRetrieveModelMixin,
    AsyncListModelMixin,
    AsyncGenericViewSet,
):
    """
    A viewset that provides default list() and retrieve() actions, served via
    the async pipeline.
    """


class AsyncModelViewSet(
    AsyncCreateModelMixin,
    AsyncRetrieveModelMixin,
    AsyncUpdateModelMixin,
    AsyncDestroyModelMixin,
    AsyncListModelMixin,
    AsyncGenericViewSet,
):
    """
    A viewset that provides default create(), retrieve(), update(),
    partial_update(), destroy(), and list() actions, served via the async
    pipeline.
    """
