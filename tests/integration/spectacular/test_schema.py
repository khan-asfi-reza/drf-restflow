from typing import Literal

import pytest
from rest_framework import serializers as drf_serializers

spectacular = pytest.importorskip("drf_spectacular")

from drf_spectacular.generators import SchemaGenerator

from restflow.serializers import Email, Serializer
from restflow.spectacular import RestflowAutoSchema
from restflow.views import (
    ActionConfig,
    AsyncListAPIView,
    AsyncModelViewSet,
)


class _ListSer(Serializer):
    pk: int
    name: str


class _DetailSer(Serializer):
    pk: int
    name: str
    email: Email
    role: Literal["admin", "user"]
    tags: list[str]


class _CreateSer(Serializer):
    name: str
    email: Email


class _DefaultSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField()
    name = drf_serializers.CharField()


def _build_schema(view_callable):
    from django.urls import path

    urlpatterns = [
        path("widgets/", view_callable, name="widgets-list"),
    ]

    generator = SchemaGenerator(patterns=urlpatterns)
    return generator.get_schema(request=None, public=True)


def test_action_config_picks_serializer_per_action_in_schema():
    class _VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        schema = RestflowAutoSchema()
        action_configs = {
            "list": ActionConfig(serializer_class=_ListSer),
            "create": ActionConfig(serializer_class=_CreateSer),
        }

        def get_queryset(self):
            return []

    list_view = _VS.as_view({"get": "list", "post": "create"})

    schema = _build_schema(list_view)
    paths = schema["paths"]
    widgets_path = paths["/widgets/"]

    get_op = widgets_path["get"]
    post_op = widgets_path["post"]

    schemas = schema.get("components", {}).get("schemas", {})
    list_ref = get_op["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    list_name = _resolve_ref(list_ref, schemas) or _ref_name(list_ref)
    assert "_ListSer" in list_name or "ListSer" in str(list_name)

    post_request_schema = post_op["requestBody"]["content"][
        "application/json"
    ]["schema"]
    post_name = _resolve_ref(post_request_schema, schemas) or _ref_name(
        post_request_schema
    )
    assert "_CreateSer" in post_name or "CreateSer" in str(post_name)


def test_email_annotation_renders_with_format_email():
    class _SerWithEmail(Serializer):
        contact: Email

    class _View(AsyncListAPIView):
        serializer_class = _SerWithEmail
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return []

    schema = _build_schema(_View.as_view())
    components = schema.get("components", {}).get("schemas", {})

    target = None
    for name, comp in components.items():
        if "_SerWithEmail" in name or "SerWithEmail" in name:
            target = comp
            break
    assert target is not None, f"serializer not found in components {list(components)}"
    assert target["properties"]["contact"]["format"] == "email"


def test_literal_annotation_renders_as_enum():
    class _SerWithLiteral(Serializer):
        role: Literal["admin", "user", "guest"]

    class _View(AsyncListAPIView):
        serializer_class = _SerWithLiteral
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return []

    schema = _build_schema(_View.as_view())
    components = schema.get("components", {}).get("schemas", {})

    target = None
    for name, comp in components.items():
        if "_SerWithLiteral" in name or "SerWithLiteral" in name:
            target = comp
            break
    assert target is not None
    role = target["properties"]["role"]
    if "enum" in role:
        assert set(role["enum"]) == {"admin", "user", "guest"}
    else:
        ref_name = role["$ref"].split("/")[-1]
        enum_comp = components[ref_name]
        assert set(enum_comp["enum"]) == {"admin", "user", "guest"}


def test_list_annotation_renders_as_array():
    class _SerWithList(Serializer):
        tags: list[str]

    class _View(AsyncListAPIView):
        serializer_class = _SerWithList
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return []

    schema = _build_schema(_View.as_view())
    components = schema.get("components", {}).get("schemas", {})

    target = None
    for name, comp in components.items():
        if "SerWithList" in name:
            target = comp
            break
    assert target is not None
    tags = target["properties"]["tags"]
    assert tags["type"] == "array"
    assert tags["items"]["type"] == "string"


def test_optional_annotation_marks_field_nullable():
    class _SerWithOpt(Serializer):
        bio: str | None

    class _View(AsyncListAPIView):
        serializer_class = _SerWithOpt
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return []

    schema = _build_schema(_View.as_view())
    components = schema.get("components", {}).get("schemas", {})

    target = None
    for name, comp in components.items():
        if "SerWithOpt" in name:
            target = comp
            break
    assert target is not None
    bio = target["properties"]["bio"]
    assert bio.get("nullable") is True or bio.get("type") == ["string", "null"]


def test_view_without_action_config_uses_default_serializer():
    class _VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        schema = RestflowAutoSchema()

        def get_queryset(self):
            return []

    view = _VS.as_view({"get": "list"})
    schema = _build_schema(view)
    paths = schema["paths"]
    op = paths["/widgets/"]["get"]
    response = op["responses"]["200"]["content"]["application/json"]["schema"]
    schemas = schema.get("components", {}).get("schemas", {})
    name = _resolve_ref(response, schemas) or _ref_name(response)
    assert "_DefaultSer" in name or "DefaultSer" in str(name) or "Default" in str(name)


def test_apiview_serializer_class_picked_up_in_schema():
    from restflow.views import APIView

    class V(APIView):
        serializer_class = _ListSer
        schema = RestflowAutoSchema()

        def get(self, request):
            return self.serialized_response(None)

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    response = op["responses"]["200"]["content"]["application/json"]["schema"]
    name = _ref_name(response)
    assert "ListSer" in name


def test_apiview_pagination_wraps_response_in_paginator_schema():
    from rest_framework.pagination import PageNumberPagination

    from restflow.views import APIView

    class _Page(PageNumberPagination):
        page_size = 10

    class V(APIView):
        serializer_class = _ListSer
        pagination_class = _Page
        schema = RestflowAutoSchema()

        def get(self, request):
            return self.paginated_response([])

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    response = op["responses"]["200"]["content"]["application/json"]["schema"]
    components = schema.get("components", {}).get("schemas", {})
    resolved = _resolve_object(response, components)
    props = resolved["properties"]
    assert "count" in props
    assert "next" in props
    assert "previous" in props
    assert "results" in props
    assert props["results"]["type"] == "array"


def test_async_apiview_pagination_wraps_response_in_paginator_schema():
    from rest_framework.pagination import PageNumberPagination

    from restflow.views import AsyncAPIView

    class _Page(PageNumberPagination):
        page_size = 10

    class V(AsyncAPIView):
        serializer_class = _ListSer
        pagination_class = _Page
        schema = RestflowAutoSchema()

        async def get(self, request):
            return await self.apaginated_response([])

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    response = op["responses"]["200"]["content"]["application/json"]["schema"]
    components = schema.get("components", {}).get("schemas", {})
    resolved = _resolve_object(response, components)
    props = resolved["properties"]
    assert "count" in props
    assert "results" in props


def test_apiview_without_pagination_returns_single_object_schema():
    from restflow.views import APIView

    class V(APIView):
        serializer_class = _ListSer
        schema = RestflowAutoSchema()

        def get(self, request):
            return self.serialized_response(None)

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    response = op["responses"]["200"]["content"]["application/json"]["schema"]
    name = _ref_name(response)
    assert "ListSer" in name


def test_apiview_request_response_split_in_schema():
    from restflow.views import APIView

    class _InputSer(drf_serializers.Serializer):
        name = drf_serializers.CharField()
        password = drf_serializers.CharField(write_only=True)

    class _OutputSer(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        name = drf_serializers.CharField()

    class V(APIView):
        request_serializer_class = _InputSer
        response_serializer_class = _OutputSer
        schema = RestflowAutoSchema()

        def post(self, request):
            self.validated_serializer()
            return self.serialized_response(None)

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["post"]

    request_schema = op["requestBody"]["content"][
        "application/json"
    ]["schema"]
    request_name = _ref_name(request_schema)
    assert "InputSer" in request_name

    response_schema = op["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    response_name = _ref_name(response_schema)
    assert "OutputSer" in response_name


def test_action_config_request_response_split_in_schema():
    class _CreateInput(drf_serializers.Serializer):
        name = drf_serializers.CharField()
        secret = drf_serializers.CharField(write_only=True)

    class _CreateOutput(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        name = drf_serializers.CharField()

    class _VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        schema = RestflowAutoSchema()
        action_configs = {
            "create": ActionConfig(
                request_serializer_class=_CreateInput,
                response_serializer_class=_CreateOutput,
            ),
        }

        def get_queryset(self):
            return []

    view = _VS.as_view({"post": "create"})
    schema = _build_schema(view)
    op = schema["paths"]["/widgets/"]["post"]

    request_name = _ref_name(
        op["requestBody"]["content"]["application/json"]["schema"]
    )
    response_name = _ref_name(
        op["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert "CreateInput" in request_name
    assert "CreateOutput" in response_name


def test_action_config_request_only_falls_back_for_response():
    class _ReqSer(drf_serializers.Serializer):
        name = drf_serializers.CharField()

    class _VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        schema = RestflowAutoSchema()
        action_configs = {
            "create": ActionConfig(request_serializer_class=_ReqSer),
        }

        def get_queryset(self):
            return []

    view = _VS.as_view({"post": "create"})
    schema = _build_schema(view)
    op = schema["paths"]["/widgets/"]["post"]
    request_name = _ref_name(
        op["requestBody"]["content"]["application/json"]["schema"]
    )
    assert "ReqSer" in request_name
    response_name = _ref_name(
        op["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert "DefaultSer" in response_name or "Default" in response_name


def test_action_config_response_only_falls_back_for_request():
    class _RespSer(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()

    class _VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        schema = RestflowAutoSchema()
        action_configs = {
            "create": ActionConfig(response_serializer_class=_RespSer),
        }

        def get_queryset(self):
            return []

    view = _VS.as_view({"post": "create"})
    schema = _build_schema(view)
    op = schema["paths"]["/widgets/"]["post"]
    request_name = _ref_name(
        op["requestBody"]["content"]["application/json"]["schema"]
    )
    assert "DefaultSer" in request_name or "Default" in request_name
    response_name = _ref_name(
        op["responses"]["201"]["content"]["application/json"]["schema"]
    )
    assert "RespSer" in response_name


def test_plain_drf_view_falls_back_to_super_request_serializer():
    from rest_framework.generics import GenericAPIView

    class V(GenericAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _DefaultSer

        def post(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["post"]
    assert "requestBody" in op


def test_view_with_raising_get_request_serializer_class_falls_back():
    from rest_framework.generics import GenericAPIView

    err = "boom"

    class V(GenericAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _DefaultSer

        def get_request_serializer_class(self):
            raise AttributeError(err)

        def post(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["post"]
    assert "requestBody" in op


def test_view_with_raising_get_response_serializer_class_falls_back():
    from rest_framework.generics import GenericAPIView

    err = "boom"

    class V(GenericAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _DefaultSer

        def get_response_serializer_class(self):
            raise AttributeError(err)

        def get(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_view_with_request_serializer_class_returning_none_uses_super():
    from rest_framework.generics import GenericAPIView

    class V(GenericAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _DefaultSer

        def get_request_serializer_class(self):
            return None

        def post(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["post"]
    assert "requestBody" in op


def test_view_with_response_serializer_class_returning_none_uses_super():
    from rest_framework.generics import GenericAPIView

    class V(GenericAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _DefaultSer

        def get_response_serializer_class(self):
            return None

        def get(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_paginated_list_with_no_action_config_uses_serializer_class_attr():
    from rest_framework.pagination import PageNumberPagination
    from rest_framework.views import APIView as DRFAPIView

    class _Page(PageNumberPagination):
        page_size = 10

    class V(DRFAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _ListSer
        pagination_class = _Page

        def get(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_paginated_list_with_raising_get_serializer_class_falls_back():
    from rest_framework.pagination import PageNumberPagination
    from rest_framework.views import APIView as DRFAPIView

    err = "boom"

    class _Page(PageNumberPagination):
        page_size = 10

    class V(DRFAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _ListSer
        pagination_class = _Page

        def get_serializer_class(self):
            raise AttributeError(err)

        def get(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_action_config_pagination_class_resolved():
    from rest_framework.pagination import PageNumberPagination

    class _Page(PageNumberPagination):
        page_size = 10

    class _VS(AsyncModelViewSet):
        serializer_class = _ListSer
        schema = RestflowAutoSchema()
        action_configs = {
            "list": ActionConfig(pagination_class=_Page),
        }

        def get_queryset(self):
            return []

    view_instance = _VS()
    view_instance.action = "list"
    schema_obj = RestflowAutoSchema()
    schema_obj.view = view_instance
    assert schema_obj.resolved_pagination_class() is _Page


def test_view_with_raising_get_pagination_class_falls_back():
    from rest_framework.pagination import PageNumberPagination
    from rest_framework.views import APIView as DRFAPIView

    err = "boom"

    class _Page(PageNumberPagination):
        page_size = 10

    class V(DRFAPIView):
        schema = RestflowAutoSchema()
        serializer_class = _ListSer
        pagination_class = _Page

        def get_pagination_class(self):
            raise AttributeError(err)

        def get(self, request):
            return None

    schema = _build_schema(V.as_view())
    op = schema["paths"]["/widgets/"]["get"]
    assert "responses" in op


def test_detail_route_with_lookup_url_kwarg_disables_pagination():
    from rest_framework.pagination import PageNumberPagination

    from restflow.views import APIView

    class _Page(PageNumberPagination):
        page_size = 10

    class V(APIView):
        serializer_class = _ListSer
        pagination_class = _Page
        lookup_url_kwarg = "pk"
        schema = RestflowAutoSchema()

        def get(self, request, pk=None):
            return self.serialized_response(None)

    schema_obj = RestflowAutoSchema()
    schema_obj.view = V()
    schema_obj.method = "GET"
    schema_obj.path_regex = "^/widgets/(?P<pk>[^/.]+)/$"
    schema_obj.path = "/widgets/{pk}/"
    assert schema_obj.should_paginate() is False


def test_detail_route_with_lookup_field_only_via_path_match():
    from rest_framework.pagination import PageNumberPagination

    from restflow.views import APIView

    class _Page(PageNumberPagination):
        page_size = 10

    class V(APIView):
        serializer_class = _ListSer
        pagination_class = _Page
        lookup_field = "slug"
        schema = RestflowAutoSchema()

        def get(self, request, slug=None):
            return self.serialized_response(None)

    schema_obj = RestflowAutoSchema()
    schema_obj.view = V()
    schema_obj.method = "GET"
    schema_obj.path_regex = ""
    schema_obj.path = "/widgets/{slug}/"
    assert schema_obj.should_paginate() is False


def test_should_paginate_false_for_non_get_method():
    from restflow.views import APIView

    class V(APIView):
        serializer_class = _ListSer
        schema = RestflowAutoSchema()

        def post(self, request):
            return self.serialized_response(None)

    schema_obj = RestflowAutoSchema()
    schema_obj.view = V()
    schema_obj.method = "POST"
    schema_obj.path_regex = ""
    schema_obj.path = "/widgets/"
    assert schema_obj.should_paginate() is False


def _ref_name(schema_obj):
    ref = schema_obj.get("$ref")
    if ref:
        return ref.split("/")[-1]
    if schema_obj.get("type") == "array":
        items = schema_obj.get("items", {})
        if items.get("$ref"):
            return items["$ref"].split("/")[-1]
    return ""


def _resolve_ref(schema_obj, components):
    name = _ref_name(schema_obj)
    if name and name in components:
        return name
    return ""


def _resolve_object(schema_obj, components):
    name = _ref_name(schema_obj)
    if name and name in components:
        return components[name]
    return schema_obj
