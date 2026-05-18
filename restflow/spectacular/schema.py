import logging

from django.core.exceptions import ImproperlyConfigured
from drf_spectacular.openapi import AutoSchema

from restflow.spectacular.parameters import (
    build_filterset_parameters,
    resolve_filterset_class,
)

logger = logging.getLogger(__name__)
_SCHEMA_FAILURE_TYPES = (AttributeError, ImproperlyConfigured, TypeError)


class RestflowAutoSchema(AutoSchema):
    """AutoSchema that understands restflow's view conventions.

    Resolves serializers from action_configs, non-generic APIView
    `serializer_class`, `filterset_class`, and `pagination_class`.
    Filter parameters are computed directly from `filterset_class`
    without depending on `filter_backends`, so any view that declares
    a FilterSet gets its query parameters in the schema.
    """

    def _get_filter_parameters(self):
        parameters = list(super()._get_filter_parameters())
        filterset_class = resolve_filterset_class(self.view)
        if filterset_class is None:
            return parameters

        existing_keys = {
            (p.get("name"), p.get("in"))
            for p in parameters
            if isinstance(p, dict)
        }
        try:
            extra = build_filterset_parameters(filterset_class)
        except Exception as exc:
            logger.warning(
                "RestflowAutoSchema: failed to build filterset params for %r: %s",
                self.view,
                exc,
            )
            return parameters

        for parameter in extra:
            key = (parameter.get("name"), parameter.get("in"))
            if key in existing_keys:
                continue
            parameters.append(parameter)
            existing_keys.add(key)
        return parameters

    def get_request_serializer(self):
        """Returns the serializer instance used to describe the operation's request body."""
        cfg = self.restflow_action_config()
        if cfg is not None and cfg.request_serializer_class is not None:
            return cfg.request_serializer_class()
        if cfg is not None and cfg.serializer_class is not None:
            return cfg.serializer_class()
        view = self.view
        get_request = getattr(view, "get_request_serializer_class", None)
        if callable(get_request):
            try:
                cls = get_request()
            except _SCHEMA_FAILURE_TYPES as exc:
                logger.warning(
                    "RestflowAutoSchema: get_request_serializer_class on %r failed: %s",
                    self.view,
                    exc,
                )
                cls = None
            if cls is not None:
                return cls()
        return super().get_request_serializer()

    def get_response_serializers(self):
        """Returns the serializer instance used to describe the operation's response body."""
        cfg = self.restflow_action_config()
        many = self.should_paginate()

        if cfg is not None and cfg.response_serializer_class is not None:
            return cfg.response_serializer_class(many=many) if many else cfg.response_serializer_class()
        if cfg is not None and cfg.serializer_class is not None:
            return cfg.serializer_class(many=many) if many else cfg.serializer_class()

        view = self.view
        get_response = getattr(view, "get_response_serializer_class", None)
        if callable(get_response):
            try:
                cls = get_response()
            except _SCHEMA_FAILURE_TYPES as exc:
                logger.warning(
                    "RestflowAutoSchema: get_response_serializer_class on %r failed: %s",
                    self.view,
                    exc,
                )
                cls = None
            if cls is not None:
                return cls(many=many) if many else cls()

        if many:
            ser_cls = self.restflow_serializer_class()
            if ser_cls is not None:
                return ser_cls(many=True)
        return super().get_response_serializers()

    def restflow_action_config(self):
        view = self.view
        action = getattr(view, "action", None)
        if action is None:
            return None
        configs = getattr(view, "action_configs", None)
        if not configs:
            return None
        return configs.get(action)

    def restflow_serializer_class(self):
        view = self.view
        get_serializer_class = getattr(view, "get_serializer_class", None)
        if callable(get_serializer_class):
            try:
                return get_serializer_class()
            except _SCHEMA_FAILURE_TYPES as exc:
                logger.warning(
                    "RestflowAutoSchema: get_serializer_class on %r failed: %s",
                    view,
                    exc,
                )
                return None
        return getattr(view, "serializer_class", None)

    def should_paginate(self):
        if (self.method or "").upper() != "GET":
            return False
        view = self.view
        if hasattr(view, "lookup_url_kwarg") or hasattr(view, "lookup_field"):
            url_kwarg = getattr(view, "lookup_url_kwarg", None) or getattr(
                view, "lookup_field", None
            )
            if url_kwarg and url_kwarg in (self.path_regex or ""):
                return False
            if url_kwarg and ("{" + str(url_kwarg) + "}") in (self.path or ""):
                return False
        return self.resolved_pagination_class() is not None

    def resolved_pagination_class(self):
        cfg = self.restflow_action_config()
        if cfg is not None and cfg.pagination_class is not None:
            return cfg.pagination_class
        get_pagination_class = getattr(self.view, "get_pagination_class", None)
        if callable(get_pagination_class):
            try:
                return get_pagination_class()
            except _SCHEMA_FAILURE_TYPES as exc:
                logger.warning(
                    "RestflowAutoSchema: get_pagination_class on %r failed: %s",
                    self.view,
                    exc,
                )
                return None
        return getattr(self.view, "pagination_class", None)
