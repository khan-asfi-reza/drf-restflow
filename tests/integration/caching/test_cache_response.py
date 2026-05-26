import asyncio

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response as DRFResponse
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from restflow.caching import (
    ArgsKeyField,
    CacheRegister,
    InvalidationRule,
    KeyConstructor,
    QueryParamsKeyField,
    ResponseCacheKeyConstructor,
    ViewKwargsKeyField,
    cache_response,
)
from restflow.responses import Response as RestflowResponse
from restflow.views import AsyncAPIView
from tests.models import SampleModel


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    CacheRegister._disconnect_all_signals()
    CacheRegister._connected_models.clear()
    yield
    cache.clear()


def _get(path="/", query=""):
    factory = APIRequestFactory()
    url = f"{path}?{query}" if query else path
    return factory.get(url)


# ---------- sync view caching ----------


def test_sync_view_caches_and_short_circuits():
    calls = []

    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            calls.append(1)
            return DRFResponse({"v": len(calls)})

    view = V.as_view()
    first = view(_get())
    second = view(_get())

    assert isinstance(first, HttpResponse)
    assert isinstance(second, HttpResponse)
    assert first.content == second.content
    assert len(calls) == 1


def test_sync_view_hit_returns_plain_httpresponse():
    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            return DRFResponse({"ok": True})

    view = V.as_view()
    view(_get())
    hit = view(_get())

    assert type(hit) is HttpResponse
    assert hit["Content-Type"].startswith("application/json")


def test_query_string_changes_force_miss():
    calls = []

    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            calls.append(request.query_params.get("q"))
            return DRFResponse({"q": request.query_params.get("q")})

    view = V.as_view()
    view(_get(query="q=a"))
    view(_get(query="q=a"))
    view(_get(query="q=b"))

    assert calls == ["a", "b"]


def test_path_kwargs_change_force_miss():
    calls = []

    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request, pk=None):
            calls.append(pk)
            return DRFResponse({"pk": pk})

    view = V.as_view()
    view(_get(), pk=1)
    view(_get(), pk=1)
    view(_get(), pk=2)

    assert calls == [1, 2]


# ---------- async view caching ----------


def test_async_view_caches_and_short_circuits():
    calls = []

    class V(AsyncAPIView):
        @cache_response(ttl=60)
        async def get(self, request):
            calls.append(1)
            return RestflowResponse({"v": len(calls)})

    view = V.as_view()
    first = _run(view(_get()))
    second = _run(view(_get()))

    assert isinstance(first, HttpResponse)
    assert first.content == second.content
    assert len(calls) == 1


def test_async_view_returns_restflow_response_arender_path():
    """Async view path renders via arender (RestflowResponse) and caches the rendered triple."""

    class V(AsyncAPIView):
        @cache_response(ttl=60)
        async def get(self, request):
            return RestflowResponse({"v": 1})

    view = V.as_view()
    response = _run(view(_get()))
    assert response.status_code == 200
    assert response.content == b'{"v":1}'


def test_async_view_falls_back_to_sync_render_for_drf_response():
    class V(AsyncAPIView):
        @cache_response(ttl=60)
        async def get(self, request):
            return DRFResponse({"v": 1})

    view = V.as_view()
    response = _run(view(_get()))

    assert response.content == b'{"v":1}'


# ---------- cache_if ----------


def test_cache_if_skips_when_predicate_false():
    calls = []

    class V(APIView):
        @cache_response(
            ttl=60,
            cache_if=lambda response: response.status_code < 400,
        )
        def get(self, request):
            calls.append(1)
            return DRFResponse({"err": "boom"}, status=500)

    view = V.as_view()
    view(_get())
    view(_get())

    assert len(calls) == 2  # never cached


# ---------- key constructor defaults ----------


def test_default_constructor_has_query_and_view_kwargs_fields():
    ctor = ResponseCacheKeyConstructor()
    fields = ctor.get_fields()
    assert isinstance(fields["query_params"], QueryParamsKeyField)
    assert isinstance(fields["path_params"], ViewKwargsKeyField)


def test_view_kwargs_field_skips_self_and_request():
    field = ViewKwargsKeyField("*")

    class V:
        def get(self, request, pk=None):
            pass

    payload = field.get_key_payload(V.get, (V(), "REQ"), {"pk": 7})
    assert "self" not in payload
    assert "request" not in payload
    assert payload["pk"] == 7


# ---------- inherited wrapper surface ----------


def test_bypass_cache_skips_io():
    calls = []

    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            calls.append(1)
            return DRFResponse({"v": len(calls)})

    view = V.as_view()
    view(_get())  # warm
    # bypass invokes the wrapped function directly
    V.get.bypass_cache(V(), _get())
    assert len(calls) == 2


def test_delete_cache_clears_entry():
    calls = []

    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            calls.append(1)
            return DRFResponse({"v": 1})

    view = V.as_view()
    view(_get())
    V.get.delete_cache(V(), _get())
    view(_get())

    assert len(calls) == 2


# ---------- subclassable constructor ----------


def test_subclassed_constructor_partitions_by_user_id():
    class UserMeKey(ResponseCacheKeyConstructor):
        user_id = ArgsKeyField("user_id", partition=True)

        class Meta:
            version = 1
            namespace = "UserMe"

    calls = []

    class V(APIView):
        @cache_response(key_constructor=UserMeKey, ttl=60)
        def get(self, request, user_id=None):
            calls.append(user_id)
            return DRFResponse({"u": user_id})

    view = V.as_view()
    view(_get(), user_id=1)
    view(_get(), user_id=1)
    view(_get(), user_id=2)

    assert calls == [1, 2]


# ---------- set_cache_headers ----------


def test_set_cache_headers_attaches_status_on_hit_and_miss():
    class V(APIView):
        @cache_response(ttl=60, set_cache_headers=True)
        def get(self, request):
            return DRFResponse({"v": 1})

    view = V.as_view()
    miss = view(_get())
    hit = view(_get())

    assert miss["X-Cache-status"] == "MISS"
    assert hit["X-Cache-status"] == "HIT"
    assert "X-Cached-at" in miss
    assert "X-Cached-at" in hit


def test_set_cache_headers_async_attaches_status_on_hit_and_miss():
    class V(AsyncAPIView):
        @cache_response(ttl=60, set_cache_headers=True)
        async def get(self, request):
            return RestflowResponse({"v": 1})

    view = V.as_view()
    miss = _run(view(_get()))
    hit = _run(view(_get()))

    assert miss["X-Cache-status"] == "MISS"
    assert hit["X-Cache-status"] == "HIT"


def test_set_cache_headers_default_false_does_not_attach():
    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            return DRFResponse({"v": 1})

    view = V.as_view()
    response = view(_get())
    assert "X-Cache-status" not in response


def test_async_cache_if_skips_when_predicate_false():
    calls = []

    class V(AsyncAPIView):
        @cache_response(
            ttl=60,
            cache_if=lambda response: response.status_code < 400,
        )
        async def get(self, request):
            calls.append(1)
            return RestflowResponse({"err": "boom"}, status=500)

    view = V.as_view()
    _run(view(_get()))
    _run(view(_get()))

    assert len(calls) == 2


def test_extract_view_and_request_finds_request_in_kwargs():
    class V(APIView):
        @cache_response(ttl=60)
        def get(self, request):
            return DRFResponse({"v": 1})

    wrapper = V.__dict__["get"]
    view_instance = V()
    request_obj = _get()
    view, req = wrapper.extract_view_and_request(
        args=(view_instance,),
        kwargs={"request": request_obj},
    )
    assert view is view_instance
    assert req is request_obj


# ---------- @api_view (function-based) ----------

# DRF @api_view dispatches synchronously, so only the sync variant is
# supported by DRF itself. Async functions wrapped in @api_view return
# coroutines that DRF's sync dispatch cannot await. For async function-
# based caching, use restflow's AsyncAPIView class (covered above).


def test_api_view_sync_caches_and_short_circuits():
    calls = []

    @api_view(["GET"])
    @cache_response(ttl=60)
    def my_view(request):
        calls.append(1)
        return DRFResponse({"v": len(calls)})

    first = my_view(_get())
    second = my_view(_get())

    assert isinstance(first, HttpResponse)
    assert isinstance(second, HttpResponse)
    assert first.content == second.content
    assert len(calls) == 1


def test_api_view_sync_query_change_forces_miss():
    calls = []

    @api_view(["GET"])
    @cache_response(ttl=60)
    def my_view(request):
        calls.append(request.query_params.get("q"))
        return DRFResponse({"q": request.query_params.get("q")})

    my_view(_get(query="q=a"))
    my_view(_get(query="q=a"))
    my_view(_get(query="q=b"))

    assert calls == ["a", "b"]


# ---------- invalidates_on ----------


@pytest.mark.django_db(transaction=True)
def test_class_based_sync_invalidates_on_model_save():
    CacheRegister.clear()
    instance = SampleModel.objects.create(integer_field=1)
    calls = []

    class Key(KeyConstructor):
        pk = ArgsKeyField("pk", partition=True)

        class Meta:
            version = 1
            namespace = "InvSync"

    class V(APIView):
        @cache_response(
            key_constructor=Key,
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=SampleModel,
                    field_mapping={"pk": "pk"},
                ),
            ],
        )
        def get(self, request, pk=None):
            calls.append(pk)
            obj = SampleModel.objects.get(pk=pk)
            return DRFResponse({"v": obj.integer_field})

    CacheRegister.auto_discover()

    view = V.as_view()
    view(_get(), pk=instance.pk)
    view(_get(), pk=instance.pk)
    assert len(calls) == 1

    instance.integer_field = 2
    instance.save()

    response = view(_get(), pk=instance.pk)
    assert len(calls) == 2
    assert b'"v":2' in response.content


@pytest.mark.django_db(transaction=True)
def test_class_based_async_invalidates_on_model_save():
    CacheRegister.clear()
    instance = SampleModel.objects.create(integer_field=1)
    calls = []

    class Key(KeyConstructor):
        pk = ArgsKeyField("pk", partition=True)

        class Meta:
            version = 1
            namespace = "InvAsync"

    class V(AsyncAPIView):
        @cache_response(
            key_constructor=Key,
            ttl=60,
            invalidates_on=[
                InvalidationRule(
                    model=SampleModel,
                    field_mapping={"pk": "pk"},
                ),
            ],
        )
        async def get(self, request, pk=None):
            calls.append(pk)
            obj = await SampleModel.objects.aget(pk=pk)
            return RestflowResponse({"v": obj.integer_field})

    CacheRegister.auto_discover()

    view = V.as_view()
    _run(view(_get(), pk=instance.pk))
    _run(view(_get(), pk=instance.pk))
    assert len(calls) == 1

    instance.integer_field = 2
    instance.save()

    response = _run(view(_get(), pk=instance.pk))
    assert len(calls) == 2
    assert b'"v":2' in response.content


@pytest.mark.django_db(transaction=True)
def test_api_view_sync_invalidates_on_model_save():
    CacheRegister.clear()
    instance = SampleModel.objects.create(integer_field=1)
    calls = []

    class Key(KeyConstructor):
        pk = ArgsKeyField("pk", partition=True)

        class Meta:
            version = 1
            namespace = "InvFbvSync"

    @api_view(["GET"])
    @cache_response(
        key_constructor=Key,
        ttl=60,
        invalidates_on=[
            InvalidationRule(
                model=SampleModel,
                field_mapping={"pk": "pk"},
            ),
        ],
    )
    def my_view(request, pk=None):
        calls.append(pk)
        obj = SampleModel.objects.get(pk=pk)
        return DRFResponse({"v": obj.integer_field})

    CacheRegister.auto_discover()

    my_view(_get(), pk=instance.pk)
    my_view(_get(), pk=instance.pk)
    assert len(calls) == 1

    instance.integer_field = 2
    instance.save()

    response = my_view(_get(), pk=instance.pk)
    assert len(calls) == 2
    assert b'"v":2' in response.content


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
