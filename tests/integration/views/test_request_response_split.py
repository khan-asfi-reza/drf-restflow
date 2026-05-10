import asyncio
import json

from django.test import RequestFactory
from rest_framework import serializers as drf_serializers

from restflow.views import (
    ActionConfig,
    APIView,
    AsyncAPIView,
    AsyncModelViewSet,
)


def _run(coro):
    return asyncio.run(coro)


class _InputSer(drf_serializers.Serializer):
    name = drf_serializers.CharField()
    password = drf_serializers.CharField(write_only=True)


class _OutputSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False, default=1)
    name = drf_serializers.CharField()


class _DefaultSer(drf_serializers.Serializer):
    pk = drf_serializers.IntegerField(required=False, default=99)
    name = drf_serializers.CharField()


def _bind(view_cls, method="get", path="/", data=None, **extra):
    view = view_cls(**extra)
    factory = RequestFactory()
    if data is not None:
        raw = getattr(factory, method)(
            path, data=json.dumps(data), content_type="application/json"
        )
    else:
        raw = getattr(factory, method)(path)
    view.request = view.initialize_request(raw)
    view.format_kwarg = None
    return view


def test_request_serializer_class_used_by_validated_serializer():
    class V(APIView):
        request_serializer_class = _InputSer
        response_serializer_class = _OutputSer

    view = _bind(
        V, method="post", data={"name": "khan", "password": "pw"}
    )
    ser = view.validated_serializer()
    assert isinstance(ser, _InputSer)
    assert ser.validated_data == {"name": "khan", "password": "pw"}


def test_response_serializer_class_used_by_serialized_response():
    class V(APIView):
        request_serializer_class = _InputSer
        response_serializer_class = _OutputSer

    view = _bind(V)
    obj = type("O", (), {"pk": 7, "name": "khan"})()
    response = view.serialized_response(obj)
    assert response.status_code == 200
    assert response.data == {"pk": 7, "name": "khan"}


def test_serializer_class_is_unified_default():
    class V(APIView):
        serializer_class = _DefaultSer

    view = _bind(V, method="post", data={"name": "x"})
    ser = view.validated_serializer()
    assert isinstance(ser, _DefaultSer)

    view2 = _bind(V)
    obj = type("O", (), {"pk": 99, "name": "x"})()
    response = view2.serialized_response(obj)
    assert response.data == {"pk": 99, "name": "x"}


def test_explicit_kwarg_wins_over_request_serializer_class():
    class _AltInput(drf_serializers.Serializer):
        name = drf_serializers.CharField()
        token = drf_serializers.CharField()

    class V(APIView):
        request_serializer_class = _InputSer

    view = _bind(
        V, method="post", data={"name": "x", "token": "t"}
    )
    ser = view.validated_serializer(serializer_class=_AltInput)
    assert isinstance(ser, _AltInput)


def test_explicit_kwarg_wins_over_response_serializer_class():
    class _AltOutput(drf_serializers.Serializer):
        slug = drf_serializers.CharField()

    class V(APIView):
        response_serializer_class = _OutputSer

    view = _bind(V)
    obj = type("O", (), {"slug": "abc"})()
    response = view.serialized_response(obj, serializer_class=_AltOutput)
    assert response.data == {"slug": "abc"}


def test_request_only_falls_through_to_serializer_class():
    class V(APIView):
        serializer_class = _DefaultSer
        response_serializer_class = _OutputSer

    view = _bind(V, method="post", data={"name": "y"})
    ser = view.validated_serializer()
    assert isinstance(ser, _DefaultSer)


def test_response_only_falls_through_to_serializer_class():
    class V(APIView):
        serializer_class = _DefaultSer
        request_serializer_class = _InputSer

    view = _bind(V)
    obj = type("O", (), {"pk": 99, "name": "n"})()
    response = view.serialized_response(obj)
    assert response.data == {"pk": 99, "name": "n"}


def test_async_avalidated_serializer_uses_request_serializer_class():
    class V(AsyncAPIView):
        request_serializer_class = _InputSer
        response_serializer_class = _OutputSer

    view = _bind(
        V, method="post", data={"name": "khan", "password": "pw"}
    )
    ser = _run(view.avalidated_serializer())
    assert isinstance(ser, _InputSer)


def test_async_aserialized_response_uses_response_serializer_class():
    class V(AsyncAPIView):
        request_serializer_class = _InputSer
        response_serializer_class = _OutputSer

    view = _bind(V)
    obj = type("O", (), {"pk": 5, "name": "x"})()
    response = _run(view.aserialized_response(obj))
    assert response.data == {"pk": 5, "name": "x"}


def test_action_config_per_action_request_response_split():
    class _CreateInput(drf_serializers.Serializer):
        name = drf_serializers.CharField()
        secret = drf_serializers.CharField(write_only=True)

    class _CreateOutput(drf_serializers.Serializer):
        pk = drf_serializers.IntegerField()
        name = drf_serializers.CharField()

    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "create": ActionConfig(
                request_serializer_class=_CreateInput,
                response_serializer_class=_CreateOutput,
            ),
        }

    view = VS()
    view.action = "create"
    factory = RequestFactory()
    view.request = factory.post("/")

    assert view.get_request_serializer_class() is _CreateInput
    assert view.get_response_serializer_class() is _CreateOutput


def test_action_config_request_response_falls_through_to_serializer_class():
    class VS(AsyncModelViewSet):
        serializer_class = _DefaultSer
        action_configs = {
            "list": ActionConfig(serializer_class=_OutputSer),
        }

    view = VS()
    view.action = "list"
    factory = RequestFactory()
    view.request = factory.get("/")

    assert view.get_request_serializer_class() is _OutputSer
    assert view.get_response_serializer_class() is _OutputSer
