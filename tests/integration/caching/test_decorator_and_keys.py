import asyncio
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from rest_framework import serializers as drf_serializers

from restflow.caching import (
    ArgsKeyField,
    ConstantKeyField,
    DefaultKeyConstructor,
    InlineKeyConstructor,
    KeyConstructor,
    QueryParamsKeyField,
    RequestValueKeyField,
    cache_result,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_cache_result_decorator_caches_sync_result():
    calls = {"n": 0}

    @cache_result(
        key_constructor={"fields": {"args": ArgsKeyField("*")}, "namespace": "p1"},
        ttl=60,
    )
    def add(a, b):
        calls["n"] += 1
        return a + b

    assert add(1, 2) == 3
    assert add(1, 2) == 3
    assert calls["n"] == 1


def test_cache_result_decorator_caches_async_result():
    calls = {"n": 0}

    @cache_result(
        key_constructor={"fields": {"args": ArgsKeyField("*")}, "namespace": "p2"},
        ttl=60,
    )
    async def addr(a, b):
        calls["n"] += 1
        return a + b

    assert _run(addr(2, 3)) == 5
    assert _run(addr(2, 3)) == 5
    assert calls["n"] == 1


def test_cache_result_separate_args_produce_different_keys():
    @cache_result(
        key_constructor={
            "fields": {"args": ArgsKeyField("x")},
            "namespace": "p3",
        },
        ttl=60,
    )
    def f(x):
        return x * 2

    assert f(1) == 2
    assert f(2) == 4
    assert f(3) == 6


def test_cache_result_with_cache_if_skips_when_predicate_false():
    @cache_result(
        key_constructor={
            "fields": {"args": ArgsKeyField("*")},
            "namespace": "p4",
        },
        ttl=60,
        cache_if=lambda r: r != 0,
    )
    def f(x):
        return x

    assert f(0) == 0
    assert f(1) == 1


def test_cache_result_with_cache_unless_skips_when_predicate_true():
    @cache_result(
        key_constructor={
            "fields": {"args": ArgsKeyField("*")},
            "namespace": "p5",
        },
        ttl=60,
        cache_unless=lambda r: r is None,
    )
    def f(x):
        return None if x else "ok"

    assert f(False) == "ok"
    assert f(True) is None


def test_cache_result_invalid_constructor_raises():
    with pytest.raises(ValueError, match="Invalid KeyConstructor"):
        cache_result(key_constructor="not a constructor", ttl=60)(lambda: None)


def test_cache_result_with_class_constructor():
    class K(KeyConstructor):
        class Meta:
            namespace = "p7"

    @cache_result(key_constructor=K, ttl=60)
    def f(x):
        return x

    assert f(1) == 1


def test_cache_result_default_constructor_is_default_when_omitted():
    @cache_result(ttl=60)
    def f(x):
        return x * 2

    assert f(7) == 14
    assert f(7) == 14


def test_cache_result_partition_field_separates_keys():
    @cache_result(
        key_constructor={
            "fields": {"user": ArgsKeyField("user", partition=True)},
            "namespace": "p8",
        },
        ttl=60,
    )
    def f(user):
        return f"user-{user}"

    assert f("a") == "user-a"
    assert f("b") == "user-b"
    cached_a = f("a")
    assert cached_a == "user-a"


def test_inline_constructor_callable_form():
    constructor = InlineKeyConstructor(
        fields={"env": ConstantKeyField("env", "prod")},
        namespace="p9",
    )
    instance = constructor()
    assert isinstance(instance, KeyConstructor)


def test_constant_key_field_emits_fixed_value_regardless_of_args():
    field = ConstantKeyField("env", "production")
    payload = field.get_key_payload(None, (), {})
    assert payload == {"env": "production"}


def test_args_key_field_grabs_all_when_arguments_is_star():
    def fn(a, b, c):
        return None

    field = ArgsKeyField("*")
    payload = field.get_key_payload(fn, (1, 2, 3), {})
    assert payload == {"a": 1, "b": 2, "c": 3}


def test_args_key_field_with_path_walks_attribute_chain():
    obj = Mock()
    obj.user.id = 99

    def fn(user):
        return None

    field = ArgsKeyField("user", path="id")
    payload = field.get_key_payload(fn, (obj.user,), {})
    assert payload == {"user": 99}


def test_args_key_field_with_normalizer_applied():
    def fn(value):
        return None

    field = ArgsKeyField("value", normalizer=lambda v: v.upper())
    payload = field.get_key_payload(fn, ("hello",), {})
    assert payload == {"value": "HELLO"}


def test_request_value_key_field_with_dotted_path():
    request = Mock()
    request.user.id = 42

    def fn(request):
        return None

    field = RequestValueKeyField("user.id")
    payload = field.get_key_payload(fn, (request,), {})
    assert payload == {"user_id": "42"}


def test_request_value_key_field_returns_empty_when_no_request():
    def fn():
        return None

    field = RequestValueKeyField("user.id")
    payload = field.get_key_payload(fn, (), {})
    assert payload == {}


def test_query_params_key_field_extracts_named_params():
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    request = Request(
        factory.get("/?status=active&role=admin&extra=skip")
    )

    def fn(request):
        return None

    field = QueryParamsKeyField(["status", "role"])
    payload = field.get_key_payload(fn, (request,), {})
    assert payload == {"status": "active", "role": "admin"}


def test_query_params_key_field_with_star_grabs_all():
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    request = Request(factory.get("/?a=1&b=2"))

    def fn(request):
        return None

    field = QueryParamsKeyField("*")
    payload = field.get_key_payload(fn, (request,), {})
    assert payload == {"a": "1", "b": "2"}


def test_normalize_dict_sorts_keys():
    field = ConstantKeyField("k", "v")
    result = field.normalize({"b": 2, "a": 1})
    keys = list(result.keys())
    assert keys == sorted(keys)


def test_normalize_list_with_sort_lists_true():
    field = ArgsKeyField("*", sort_lists=True)
    assert field.normalize([3, 1, 2]) == ["1", "2", "3"]


def test_normalize_list_with_sort_lists_false_preserves_order():
    field = ArgsKeyField("*", sort_lists=False)
    assert field.normalize([3, 1, 2]) == ["3", "1", "2"]


def test_normalize_none_becomes_null_string():
    field = ConstantKeyField("k", "v")
    assert field.normalize(None) == "null"


def test_stringify_dict_uses_pipe_and_colon():
    field = ConstantKeyField("k", "v")
    s = field.stringify({"a": "1", "b": "2"})
    assert "||" in s
    assert "a:1" in s
    assert "b:2" in s


def test_hash_value_produces_short_hash():
    field = ConstantKeyField("k", "v" * 1000, hash_value=True)
    payload = field.get_cache_key_part(None, (), {})
    assert len(payload) <= 64


def test_cache_result_returns_distinct_values_for_distinct_kwargs():
    @cache_result(
        key_constructor={
            "fields": {"args": ArgsKeyField("*")},
            "namespace": "p10",
        },
        ttl=60,
    )
    def f(a, b):
        return [a, b]

    assert f(1, 2) == [1, 2]
    assert f(2, 1) == [2, 1]


def test_cache_result_cache_if_with_async_predicate_runs():
    @cache_result(
        key_constructor={"fields": {}, "namespace": "p11"},
        ttl=60,
        cache_if=lambda r: True,
    )
    async def f():
        return 99

    assert _run(f()) == 99


def test_cache_result_decorated_method_attribute_set():
    @cache_result(ttl=60)
    def f():
        return 1

    assert getattr(f, "is_cached_function", False) is True


def test_args_key_field_partial_args_does_not_fail():
    def fn(a, b=10):
        return None

    field = ArgsKeyField("*")
    payload = field.get_key_payload(fn, (1,), {})
    assert payload == {"a": 1, "b": 10}


def test_args_key_field_specific_arg_when_missing_returns_empty():
    def fn(a):
        return None

    field = ArgsKeyField("nonexistent")
    payload = field.get_key_payload(fn, (1,), {})
    assert payload == {}


def test_default_key_constructor_includes_function_id_partition():
    @cache_result(ttl=60)
    def f1():
        return "f1"

    @cache_result(ttl=60)
    def f2():
        return "f2"

    assert f1() == "f1"
    assert f2() == "f2"
    assert f1() == "f1"
    assert f2() == "f2"
