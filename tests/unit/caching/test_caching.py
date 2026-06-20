import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.core.cache import cache
from django.db import models
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from restflow.caching import (
    ArgsKeyField,
    CacheKeyField,
    ConstantKeyField,
    DefaultKeyConstructor,
    DjangoModelKeyField,
    DrfSerializerKeyField,
    InlineKeyConstructor,
    KeyConstructor,
    QueryParamsKeyField,
    RequestValueKeyField,
    cache_result,
)


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.fixture
def mock_user():
    user = Mock()
    user.id = 123
    user.username = "testuser"
    user.profile = Mock()
    user.profile.id = 456
    user.profile.organization = Mock()
    user.profile.organization.id = 789
    user.profile.organization.name = "TestOrg"
    return user


@pytest.fixture
def drf_request(request_factory, mock_user):
    django_request = request_factory.get("/test/?page=1&size=10&filter=active")
    drf_req = Request(django_request)
    drf_req.user = mock_user
    return drf_req


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class MockAddressSerializer(serializers.Serializer):
    street = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=50)
    country = serializers.CharField(max_length=50, default="US")


class MockUserSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField()
    age = serializers.IntegerField(min_value=0, max_value=150, required=False)
    address = MockAddressSerializer()
    tags = serializers.ListField(child=serializers.CharField(), required=False)


class MockChoiceSerializer(serializers.Serializer):
    CHOICES = [("A", "Option A"), ("B", "Option B")]
    choice_field = serializers.ChoiceField(choices=CHOICES)


class _DummyField(CacheKeyField):
    def __init__(self, payload, hash_value=False):
        super().__init__(hash_value=hash_value)
        self._payload = payload

    def get_key_payload(self, func, args, kwargs):
        return self._payload


def _top_level_function_for_identifier_tests():
    return None


class TestCacheKeyFields:

    def test_constant_key_field_returns_static_payload(self):
        field = ConstantKeyField("version", "1.0")
        result = field.get_key_payload(None, [], {})
        assert result == {"version": "1.0"}

    def test_constant_key_field_stringifies_any_value_type(self):
        for key, value in [
            ("string_val", "test"),
            ("int_val", 42),
            ("float_val", 3.14),
            ("bool_val", True),
            ("none_val", None),
            ("list_val", [1, 2, 3]),
            ("dict_val", {"key": "value"}),
        ]:
            field = ConstantKeyField(key, value)
            assert field.get_key_payload(None, [], {}) == {key: str(value)}

    def test_stringify_canonicalizes_dict_list_none_and_datetime(self):
        field = _DummyField({"b": 2, "a": 1})
        key_part = field.get_cache_key_part(None, (), {})
        assert key_part == "a:1||b:2"

        field = _DummyField(["x", 1, None])
        key_part = field.get_cache_key_part(None, (), {})
        assert key_part == "1,null,x"

        dt = datetime(2024, 1, 1, 12, 0, 0)
        field = _DummyField({"dt": dt, "nested": [3, 2, 1]})
        key_part = field.get_cache_key_part(None, (), {})
        assert "dt:2024-01-01T12:00:00" in key_part

    def test_stringify_hashes_to_sha256_when_hash_value_true(self):
        field = _DummyField({"a": 1, "b": 2}, hash_value=True)
        key_part = field.get_cache_key_part(None, (), {})
        assert len(key_part) == 64

    def test_resolve_attr_path_returns_sentinel_for_missing_segment(self):
        from restflow.caching.constants import MISSING_VALUE

        obj = {"a": {"b": 1}}
        assert CacheKeyField._resolve_attr_path(obj, "a.c") == MISSING_VALUE
        assert CacheKeyField._resolve_attr_path(obj, "") == obj

    def test_normalize_request_passes_through_none_and_unknown_objects(self):
        assert QueryParamsKeyField._normalize_request(None) is None
        sentinel = object()
        assert QueryParamsKeyField._normalize_request(sentinel) is sentinel


class TestQueryParamsKeyField:

    def test_extracts_all_query_parameters_when_no_filter(self, drf_request):
        field = QueryParamsKeyField()

        def mock_func(request):
            pass

        result = field.get_key_payload(mock_func, (drf_request,), {})
        assert result == {"page": "1", "size": "10", "filter": "active"}

    def test_extracts_only_listed_query_parameters(self, drf_request):
        field = QueryParamsKeyField(["page", "size"])

        def mock_func(request):
            pass

        result = field.get_key_payload(mock_func, (drf_request,), {})
        assert result == {"page": "1", "size": "10"}

    def test_resolves_request_via_custom_argument_name(self, drf_request):
        field = QueryParamsKeyField(["page"], request_arg="http_request")

        def mock_func(http_request):
            pass

        result = field.get_key_payload(mock_func, (drf_request,), {})
        assert result == {"page": "1"}

    def test_sorts_repeated_query_param_values(self, request_factory, mock_user):
        django_request = request_factory.get("/t/?tag=c&tag=a&tag=b&page=2")
        req = Request(django_request)
        req.user = mock_user

        field = QueryParamsKeyField("*")

        def f(request):
            pass

        result = field.get_key_payload(f, (req,), {})
        assert result["tag"] == ["a", "b", "c"]
        assert result["page"] == "2"

    def test_returns_empty_when_no_request_in_arguments(self):
        field = QueryParamsKeyField()

        def mock_func(data):
            pass

        result = field.get_key_payload(mock_func, ("some_data",), {})
        assert result == {}

    def test_resolves_request_from_kwargs_and_from_view_self_request(self, drf_request):
        field = QueryParamsKeyField(["page"])

        def f(request):
            pass

        res = field.get_key_payload(f, (), {"request": drf_request})
        assert res == {"page": "1"}

        class ViewLike:
            def __init__(self, request):
                self.request = request

        view = ViewLike(drf_request)
        res2 = field.get_key_payload(f, (view,), {})
        assert res2 == {"page": "1"}

    def test_handles_request_with_plain_dict_query_params(self):
        class SimpleReq:
            def __init__(self, qp):
                self.query_params = qp

        req = SimpleReq({"page": "7", "other": "x"})
        field = QueryParamsKeyField(["page"])

        def f(request):
            pass

        res = field.get_key_payload(f, (req,), {})
        assert res == {"page": "7"}

    def test_falls_back_to_first_arg_self_request_attribute(self):
        class SimpleReq:
            def __init__(self):
                self.query_params = {"page": "5"}

        class ViewLike:
            def __init__(self, request):
                self.request = request

        field = QueryParamsKeyField(["page"])

        def f(x):
            pass

        view = ViewLike(SimpleReq())
        res = field.get_key_payload(f, (view,), {})
        assert res == {"page": "5"}


class TestFuncArgumentKeyField:

    def test_captures_every_bound_argument_by_default(self):
        field = ArgsKeyField()

        def mock_func(a, b, c=10):
            pass

        result = field.get_key_payload(mock_func, (1, 2), {"c": 3})
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_captures_only_listed_arguments(self):
        field = ArgsKeyField(["a", "c"])

        def mock_func(a, b, c=10):
            pass

        result = field.get_key_payload(mock_func, (1, 2), {"c": 3})
        assert result == {"a": 1, "c": 3}

    def test_path_traversal_with_normalizer_returns_terminal_value(self):
        user = Mock()
        user.profile = Mock()
        user.profile.id = 456

        def mock_normalizer(value):
            if hasattr(value, "_mock_name") or str(type(value)).startswith(
                "<class 'unittest.mock"
            ):
                if (
                    hasattr(value, "return_value")
                    and value.return_value is not Mock.return_value
                ):
                    return value.return_value
                if hasattr(value, "_mock_name") and not value._mock_name:
                    return value
                return str(value)
            return value

        field = ArgsKeyField("user", path="profile.id", normalizer=mock_normalizer)

        def mock_func(user):
            pass

        result = field.get_key_payload(mock_func, (user,), {})
        assert "user" in result
        assert result["user"] == 456

    def test_normalizer_exception_is_swallowed_and_raw_value_kept(self):
        def boom(x):
            raise RuntimeError("nope")

        field = ArgsKeyField(["a"], normalizer=boom)

        def f(a):
            pass

        res = field.get_key_payload(f, (123,), {})
        assert res == {"a": 123}

    def test_datetime_argument_serializes_to_iso_format(self):
        field = ArgsKeyField("timestamp")

        def mock_func(timestamp):
            pass

        test_datetime = datetime(2024, 1, 15, 10, 30, 45)
        result = field.stringify(field.get_key_payload(mock_func, (test_datetime,), {}))
        assert result == "timestamp:2024-01-15T10:30:45"

    def test_equal_datetime_args_produce_the_same_cache_key(self):
        dt1 = datetime(2024, 1, 15, 10, 30, 45)
        dt2 = datetime(2024, 1, 15, 10, 30, 45)
        dt3 = datetime(2024, 1, 15, 10, 30, 46)

        call_count = 0

        @cache_result({"fields": {"timestamp": ArgsKeyField("dt")}}, ttl=3600)
        def f(dt):
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        f(dt1)
        f(dt2)
        assert call_count == 1
        f(dt3)
        assert call_count == 2


class TestRequestValueKeyField:

    def test_simple_path_resolution(self, drf_request):
        field = RequestValueKeyField("user.id")

        def mock_func(request):
            pass

        result = field.get_key_payload(mock_func, (drf_request,), {})
        assert result == {"user_id": "123"}

    def test_nested_path_resolution(self, drf_request):
        field = RequestValueKeyField("user.profile.organization.name")

        def mock_func(request):
            pass

        result = field.get_key_payload(mock_func, (drf_request,), {})
        assert result == {"user_profile_organization_name": "TestOrg"}

    def test_custom_request_kwarg_and_missing_request(self, drf_request):
        field = RequestValueKeyField("user.username", request_arg="http_request")

        def f(http_request):
            pass

        res = field.get_key_payload(f, (), {"http_request": drf_request})
        assert res == {"user_username": "testuser"}

        res2 = field.get_key_payload(f, (), {})
        assert res2 == {}

    def test_falls_back_to_first_arg_self_request_attribute(self, drf_request):
        class ViewLike:
            def __init__(self, request):
                self.request = request

        field = RequestValueKeyField("user.id")

        def f(x):
            pass

        view = ViewLike(drf_request)
        res = field.get_key_payload(f, (view,), {})
        assert res == {"user_id": "123"}


class TestDrfSerializerKeyField:

    def test_captures_basic_serializer_fields(self):
        field = DrfSerializerKeyField(MockAddressSerializer)

        def mock_func():
            pass

        result = field.get_key_payload(mock_func, [], {})

        assert "serializer_structure" in result
        structure = result["serializer_structure"]
        assert structure["name"] == "MockAddressSerializer"
        assert "fields" in structure

        fields = structure["fields"]
        assert "street" in fields
        assert "city" in fields
        assert "country" in fields
        assert fields["street"]["type"] == "CharField"

    def test_captures_nested_serializer_recursively(self):
        field = DrfSerializerKeyField(MockUserSerializer)

        def mock_func():
            pass

        result = field.get_key_payload(mock_func, [], {})
        structure = result["serializer_structure"]

        assert "address" in structure["fields"]
        address_field = structure["fields"]["address"]

        if "nested_serializer" in address_field:
            nested_structure = address_field["nested_serializer"]
            assert nested_structure["name"] == "MockAddressSerializer"
            assert "street" in nested_structure["fields"]

    def test_captures_list_serializer_child_structure(self):
        class GroupSerializer(serializers.Serializer):
            members = MockUserSerializer(many=True)

        field = DrfSerializerKeyField(GroupSerializer)

        def mock_func():
            pass

        result = field.get_key_payload(mock_func, [], {})
        structure = result["serializer_structure"]
        assert "members" in structure["fields"]
        members_field = structure["fields"]["members"]
        assert members_field["type"] == "ListSerializer"
        assert "list_child_serializer" in members_field
        assert members_field["list_child_serializer"]["name"] == "MockUserSerializer"

    def test_raises_when_serializer_class_is_not_a_class(self):
        with pytest.raises(ValueError, match="Failed to initialize serializer class"):
            field = DrfSerializerKeyField("not_a_class")
            field.get_key_payload(None, [], {})

    def test_raises_when_serializer_requires_constructor_args(self):
        class ProblematicSerializer(serializers.Serializer):
            def __init__(self, required_arg, *args, **kwargs):
                super().__init__(*args, **kwargs)

        with pytest.raises(ValueError, match="Failed to initialize serializer class"):
            field = DrfSerializerKeyField(ProblematicSerializer)
            field.get_key_payload(None, [], {})

    def test_returns_empty_when_serializer_class_is_none(self):
        field = DrfSerializerKeyField(None)
        assert field.get_key_payload(None, (), {}) == {}


class TestDjangoModelKeyField:

    def test_captures_model_fields_with_types(self):
        class SimpleModel(models.Model):
            a = models.CharField(max_length=32)
            b = models.IntegerField()

            class Meta:
                app_label = "tests"

        field = DjangoModelKeyField(SimpleModel)

        def f():
            pass

        result = field.get_key_payload(f, (), {})
        assert "model_structure" in result
        structure = result["model_structure"]
        assert structure["name"] == "SimpleModel"
        assert set(structure["fields"].keys()) == {"a", "b", "id"}
        assert structure["fields"]["a"]["type"] == "CharField"
        assert structure["fields"]["b"]["type"] == "IntegerField"
        assert (
            structure["fields"]["id"]["type"]
            == SimpleModel._meta.pk.__class__.__name__
        )

    def test_returns_empty_when_model_class_is_none(self):
        field = DjangoModelKeyField(None)

        def f():
            pass

        assert field.get_key_payload(f, (), {}) == {}

    def test_raises_when_model_class_is_not_a_class(self):
        field = DjangoModelKeyField("not_a_class")

        with pytest.raises(ValueError, match="Invalid model class"):
            field.get_key_payload(lambda: None, (), {})


class TestKeyConstructor:

    def test_only_cachekeyfield_attributes_become_declared_fields(self):
        class TestConstructor(KeyConstructor):
            version = ConstantKeyField("version", "1.0")
            page = QueryParamsKeyField(["page"])
            non_field_attr = "not_a_field"

        constructor = TestConstructor()
        assert len(constructor.fields) >= 2
        assert "version" in constructor.fields
        assert "page" in constructor.fields
        assert "non_field_attr" not in constructor.fields

    def test_prefix_includes_namespace_and_partition_fields(self, drf_request):
        class Constructor(KeyConstructor):
            user = RequestValueKeyField("user.id", partition=True)
            params = QueryParamsKeyField(["page"])

            class Meta:
                namespace = "ns"
                key_identifier = "test_prefix"

        def f(request):
            pass

        constructor = Constructor()
        prefix = constructor.build_key_prefix(f, (drf_request,), {})
        assert prefix.startswith("ns::test_prefix::")
        assert "user_id:123::" in prefix

        suffix = constructor.build_key_suffix(f, (drf_request,), {})
        assert suffix.endswith("page:1")

    @pytest.mark.parametrize("ns", ("", "namespace"))
    def test_generate_key_combines_namespace_function_id_and_fields(
        self, drf_request, ns
    ):
        class Constructor(KeyConstructor):
            constant = ConstantKeyField("version", "1.0")
            params = QueryParamsKeyField(["page"])

            class Meta:
                namespace = ns

        def test_func(request):
            pass

        cache_key = Constructor().generate_key(test_func, (drf_request,), {})
        expected_key = (
            f"{__name__}.TestKeyConstructor."
            "test_generate_key_combines_namespace_function_id_and_fields.<locals>.test_func"
            "::version:1.0::page:1"
        )
        if ns:
            expected_key = f"{ns}::{expected_key}"

        assert cache_key == expected_key

    def test_function_identifier_handles_function_method_and_classmethod(
        self, drf_request
    ):
        class C:
            def ins(self, request):
                pass

            @classmethod
            def clsm(cls, request):
                pass

        ctor = KeyConstructor()

        def f(request):
            pass

        rid = ctor.get_function_identifier(f)
        assert rid.endswith(".f")

        instance = C()
        rid2 = ctor.get_function_identifier(instance.ins)
        assert rid2.endswith(".C.ins")

        rid3 = ctor.get_function_identifier(C.clsm)
        assert ".C.clsm" in rid3

    def test_function_identifier_for_module_level_function(self):
        ctor = KeyConstructor()
        rid = ctor.get_function_identifier(_top_level_function_for_identifier_tests)
        assert rid.endswith("._top_level_function_for_identifier_tests")

    def test_build_partition_returns_empty_when_args_and_kwargs_are_none(self):
        kc = InlineKeyConstructor({"c": ConstantKeyField("v", "1")})()
        assert kc.build_partition(lambda: None, None, None) == ""

    def test_subclass_field_overrides_parent_field_via_mro(self):
        class BaseKC(KeyConstructor):
            dup = ConstantKeyField("v", "class")

        class ChildKC(BaseKC):
            dup = ConstantKeyField("v", "dict")

        ctor = ChildKC()
        assert isinstance(ctor.fields["dup"], ConstantKeyField)
        assert ctor.fields["dup"].value == "dict"


class TestDefaultKeyConstructor:

    def test_captures_all_function_arguments(self):
        constructor = DefaultKeyConstructor()

        def test_func(a, b, c=10):
            pass

        result_key = constructor.generate_key(test_func, (1, 2), {"c": 3})
        assert ":" in result_key
        assert "arguments" in constructor.fields
        assert isinstance(constructor.fields["arguments"], ArgsKeyField)
        assert constructor.fields["arguments"].arguments == "*"


class TestKeyConstructorWipe:

    def test_wrapper_registers_on_its_constructor_class(self):
        class WipeKC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        @cache_result(WipeKC, ttl=60)
        def f(user_id):
            return user_id

        assert f in WipeKC._cache_wrappers

    def test_each_constructor_class_has_an_isolated_registry(self):
        class KCa(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        class KCb(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        @cache_result(KCa, ttl=60)
        def fa(user_id):
            return user_id

        @cache_result(KCb, ttl=60)
        def fb(user_id):
            return user_id

        assert fa in KCa._cache_wrappers
        assert fa not in KCb._cache_wrappers
        assert fb in KCb._cache_wrappers
        assert fb not in KCa._cache_wrappers

    def test_wipe_with_args_calls_delete_by_prefix_on_each_wrapper(self):
        class KC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        w1, w2 = Mock(), Mock()
        KC._cache_wrappers[:] = [w1, w2]

        KC.wipe(user_id=1)

        w1.delete_by_prefix.assert_called_once_with(user_id=1)
        w2.delete_by_prefix.assert_called_once_with(user_id=1)
        w1.invalidate_all.assert_not_called()
        w2.invalidate_all.assert_not_called()

    def test_wipe_without_args_calls_invalidate_all_on_each_wrapper(self):
        class KC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        w1, w2 = Mock(), Mock()
        KC._cache_wrappers[:] = [w1, w2]

        KC.wipe()

        w1.invalidate_all.assert_called_once_with()
        w2.invalidate_all.assert_called_once_with()
        w1.delete_by_prefix.assert_not_called()
        w2.delete_by_prefix.assert_not_called()

    def test_awipe_with_args_calls_adelete_by_prefix_on_each_wrapper(self):
        class KC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        w1 = Mock()
        w1.adelete_by_prefix = AsyncMock()
        w1.ainvalidate_all = AsyncMock()
        KC._cache_wrappers[:] = [w1]

        asyncio.run(KC.awipe(user_id=1))

        w1.adelete_by_prefix.assert_awaited_once_with(user_id=1)
        w1.ainvalidate_all.assert_not_awaited()

    def test_awipe_without_args_calls_ainvalidate_all_on_each_wrapper(self):
        class KC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)

        w1 = Mock()
        w1.adelete_by_prefix = AsyncMock()
        w1.ainvalidate_all = AsyncMock()
        KC._cache_wrappers[:] = [w1]

        asyncio.run(KC.awipe())

        w1.ainvalidate_all.assert_awaited_once_with()
        w1.adelete_by_prefix.assert_not_awaited()

    def test_wipe_raises_when_backend_has_no_delete_pattern(self):
        class KC(KeyConstructor):
            user = ArgsKeyField("user_id", partition=True)
            v = ConstantKeyField("v", "1")

        @cache_result(KC, ttl=60)
        def f(user_id):
            return user_id

        f(1)

        with pytest.raises(NotImplementedError):
            KC.wipe(1)


class TestKeyConstructorDeletePreviousVersions:

    def test_does_nothing_on_version_1(self):
        class KC(KeyConstructor):
            class Meta:
                namespace = "prev_noop"
                version = 1

        cache.set("prev_noop::k", "value", version=1)

        assert KC.delete_previous_versions() is None
        assert cache.get("prev_noop::k", version=1) == "value"

    def test_requires_a_namespace_when_version_is_above_1(self):
        class KC(KeyConstructor):
            class Meta:
                version = 2

        with pytest.raises(ValueError):
            KC.delete_previous_versions()

    def test_raises_when_backend_has_no_delete_pattern(self):
        class KC(KeyConstructor):
            class Meta:
                namespace = "prev_ns"
                version = 2

        with pytest.raises(NotImplementedError):
            KC.delete_previous_versions()

    def test_async_does_nothing_on_version_1(self):
        class KC(KeyConstructor):
            class Meta:
                namespace = "prev_noop_async"
                version = 1

        assert asyncio.run(KC.adelete_previous_versions()) is None

    def test_async_requires_a_namespace_when_version_is_above_1(self):
        class KC(KeyConstructor):
            class Meta:
                version = 2

        with pytest.raises(ValueError):
            asyncio.run(KC.adelete_previous_versions())


class TestKeyConstructorConfigValidation:

    def test_non_integer_version_raises_type_error(self):
        import pytest

        from restflow.caching import KeyConstructor

        with pytest.raises(TypeError, match="version must be an integer"):
            class _Bad(KeyConstructor):
                class Meta:
                    version = 1.5  # float, not int / int-like string

    def test_non_string_namespace_raises_type_error(self):
        import pytest

        from restflow.caching import KeyConstructor

        with pytest.raises(TypeError, match="namespace must be a string"):
            class _Bad(KeyConstructor):
                class Meta:
                    namespace = 42

    def test_non_string_key_identifier_raises_type_error(self):
        import pytest

        from restflow.caching import KeyConstructor

        with pytest.raises(TypeError, match="key_identifier must be a string"):
            class _Bad(KeyConstructor):
                class Meta:
                    key_identifier = 42

    def test_non_int_max_key_suffix_length_raises_type_error(self):
        import pytest

        from restflow.caching import KeyConstructor

        class _Bad(KeyConstructor):
            class Meta:
                max_key_suffix_length = "not an int"

        with pytest.raises(
            TypeError, match="max_key_suffix_length must be an integer"
        ):
            _ = _Bad()._meta.max_key_suffix_length

    def test_non_bool_hash_suffix_on_overflow_raises_type_error(self):
        import pytest

        from restflow.caching import KeyConstructor

        class _Bad(KeyConstructor):
            class Meta:
                hash_suffix_on_overflow = "yes"

        with pytest.raises(
            TypeError, match="hash_suffix_on_overflow must be a boolean"
        ):
            _ = _Bad()._meta.hash_suffix_on_overflow

    def test_string_digit_version_is_coerced_to_int(self):
        from restflow.caching import KeyConstructor

        class _OK(KeyConstructor):
            class Meta:
                version = "7"

        assert _OK()._meta.version == 7


class TestRequireCelery:

    def test_raises_import_error_when_celery_unavailable(self):
        from unittest.mock import patch

        import pytest

        from restflow.caching.dispatchers.celery import _require_celery

        with patch("restflow.caching.dispatchers.celery._celery_current_app", None):
            with pytest.raises(ImportError, match="celery is required"):
                _require_celery()


class TestInlineKeyConstructor:

    def test_identical_specs_reuse_the_same_generated_class(self):
        fields = {"c": ConstantKeyField("v", "1")}
        KC1 = InlineKeyConstructor(
            fields, version="1", namespace="ns", key_identifier="kid"
        )
        KC2 = InlineKeyConstructor(
            fields, version="1", namespace="ns", key_identifier="kid"
        )
        assert KC1 is KC2

    def test_same_field_name_different_field_types_do_not_collide(self):
        KC1 = InlineKeyConstructor({"c": ConstantKeyField("v", "1")})
        KC2 = InlineKeyConstructor({"c": ArgsKeyField("v", partition=True)})

        assert KC1 is not KC2
        assert KC1().has_only_partition_fields is False
        assert KC2().has_only_partition_fields is True

    def test_same_field_type_different_partition_flag_do_not_collide(self):
        KC1 = InlineKeyConstructor({"u": ArgsKeyField("u")})
        KC2 = InlineKeyConstructor({"u": ArgsKeyField("u", partition=True)})

        assert KC1 is not KC2
        assert KC1().has_only_partition_fields is False
        assert KC2().has_only_partition_fields is True


class TestCacheResultDecorator:

    def test_repeated_call_with_same_args_returns_cached_value(self):
        call_count = 0

        @cache_result(
            {"fields": {"constant": ConstantKeyField("version", "1.0")}}, ttl=3600
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        assert test_func() == "result_1"
        assert call_count == 1
        assert test_func() == "result_1"
        assert call_count == 1

    def test_argument_dependent_caching(self, drf_request):
        call_count = 0

        @cache_result(
            {
                "fields": {
                    "params": QueryParamsKeyField(["page"]),
                    "args": ArgsKeyField(["multiplier"]),
                }
            },
            ttl=3600,
        )
        def test_func(request, multiplier):
            nonlocal call_count
            call_count += 1
            page = int(request.query_params.get("page", 1))
            return page * multiplier

        assert test_func(drf_request, 10) == 10
        assert call_count == 1
        assert test_func(drf_request, 10) == 10
        assert call_count == 1

    def test_refresh_forces_re_execution_and_re_caches(self):
        call_count = 0

        @cache_result(
            {"fields": {"constant": ConstantKeyField("version", "1.0")}}, ttl=3600
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        test_func()
        assert call_count == 1

        result2 = test_func.refresh()
        assert result2 == "result_2"
        assert call_count == 2

    def test_bypass_cache_executes_without_touching_storage(self):
        call_count = 0

        @cache_result(
            {"fields": {"constant": ConstantKeyField("version", "1.0")}}, ttl=3600
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            return f"x{call_count}"

        assert test_func() == "x1"
        assert call_count == 1
        assert test_func.bypass_cache() == "x2"
        assert call_count == 2
        assert test_func() == "x1"
        assert call_count == 2

    def test_default_constructor_keys_by_arguments(self):
        call_count = 0

        @cache_result()
        def test_func(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert test_func(1, 2) == 3
        assert call_count == 1
        assert test_func(1, 2) == 3
        assert call_count == 1
        assert test_func(2, 3) == 5
        assert call_count == 2

    def test_get_cache_key_is_deterministic_per_arguments(self):
        @cache_result(
            {
                "fields": {
                    "constant": ConstantKeyField("version", "1.0"),
                    "args": ArgsKeyField(["value"]),
                }
            },
            ttl=3600,
        )
        def test_func(value):
            return f"result_{value}"

        cache_key = test_func.get_cache_key(123)
        assert isinstance(cache_key, str)
        assert ":" in cache_key
        assert "test_func" in cache_key

        assert test_func.get_cache_key(123) == cache_key
        assert test_func.get_cache_key(456) != cache_key

    def test_accepts_keyconstructor_subclass_directly(self):
        class MyCtor(KeyConstructor):
            const = ConstantKeyField("v", "1")

        calls = {"n": 0}

        @cache_result(MyCtor, ttl=60)
        def f(x):
            calls["n"] += 1
            return x * 2

        assert f(3) == 6
        assert f(3) == 6
        assert calls["n"] == 1

    def test_raises_when_key_constructor_is_neither_dict_nor_class(self):
        with pytest.raises(ValueError):

            @cache_result(1)  # type: ignore[arg-type]
            def t(a):
                return a


class TestCacheManagementMethods:

    def test_delete_cache_removes_only_the_exact_key(self):
        call_count = 0

        @cache_result(
            {"fields": {"constant": ConstantKeyField("version", "1.0")}}, ttl=3600
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        test_func()
        test_func()
        assert call_count == 1

        test_func.delete_cache()
        test_func()
        assert call_count == 2

    def test_delete_cache_uses_constructor_version(self):
        call_count = 0

        @cache_result(
            {
                "fields": {"constant": ConstantKeyField("version", "1.0")},
                "version": 2,
            },
            ttl=3600,
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        test_func()
        test_func()
        assert call_count == 1

        test_func.delete_cache()
        test_func()
        assert call_count == 2

    def test_delete_by_prefix_calls_delete_pattern_with_wildcard(self):
        @cache_result({"fields": {"constant": ConstantKeyField("v", "1")}}, ttl=3600)
        def test_func(a):
            return a

        test_func(7)

        with patch.object(cache, "delete_pattern", create=True) as dp:
            test_func.delete_by_prefix(7)
            dp.assert_called_once()
            (pattern,) = dp.call_args.args
            assert pattern.endswith("*")

    def test_delete_by_prefix_raises_not_implemented_on_unsupported_backend(self):
        @cache_result({"fields": {"c": ConstantKeyField("v", "1")}}, ttl=60)
        def f(a):
            return a

        with pytest.raises(NotImplementedError, match="delete_pattern"):
            f.delete_by_prefix(5)

    def test_delete_by_prefix_falls_back_to_delete_cache_when_constructor_is_partition_only(self):
        calls = {"n": 0}

        @cache_result(
            {"fields": {"u": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
        )
        def f(user_id: int):
            calls["n"] += 1
            return f"v{calls['n']}"

        assert f(7) == "v1"
        assert f(7) == "v1"
        assert calls["n"] == 1

        f.delete_by_prefix(user_id=7)

        assert f(7) == "v2"
        assert calls["n"] == 2

    def test_delete_by_prefix_partition_fallback_does_not_touch_other_partitions(self):
        calls = {"n": 0}

        @cache_result(
            {"fields": {"u": ArgsKeyField("user_id", partition=True)}},
            ttl=60,
        )
        def f(user_id: int):
            calls["n"] += 1
            return f"u{user_id}-{calls['n']}"

        first_for_7 = f(7)
        first_for_8 = f(8)
        assert calls["n"] == 2

        f.delete_by_prefix(user_id=7)

        assert f(7) != first_for_7
        assert f(8) == first_for_8
        assert calls["n"] == 3

    def test_invalidate_all_raises_not_implemented_on_unsupported_backend(self):
        @cache_result({"fields": {"c": ConstantKeyField("v", "1")}}, ttl=60)
        def f():
            return 1

        with pytest.raises(NotImplementedError, match="delete_pattern"):
            f.invalidate_all()


class TestAPIViewIntegration:

    def test_apiview_method_returns_cached_response(self, drf_request):
        call_count = 0

        class TestAPIView(APIView):
            @cache_result(
                {
                    "fields": {
                        "user": RequestValueKeyField("user.id"),
                        "params": QueryParamsKeyField(["page"]),
                    }
                },
                ttl=3600,
            )
            def get(self, request):
                nonlocal call_count
                call_count += 1
                return {
                    "data": f"result_{call_count}",
                    "page": request.query_params.get("page", 1),
                }

        view = TestAPIView()
        response1 = view.get(drf_request)
        assert call_count == 1
        response2 = view.get(drf_request)
        assert call_count == 1
        assert response1 == response2

    def test_get_and_post_have_independent_caches(self, drf_request):
        get_count = 0
        post_count = 0

        class TestAPIView(APIView):
            @cache_result(
                {"fields": {"user": RequestValueKeyField("user.id")}}, ttl=3600
            )
            def get(self, request):
                nonlocal get_count
                get_count += 1
                return {"method": "get", "count": get_count}

            @cache_result(
                {"fields": {"user": RequestValueKeyField("user.id")}}, ttl=3600
            )
            def post(self, request):
                nonlocal post_count
                post_count += 1
                return {"method": "post", "count": post_count}

        view = TestAPIView()
        view.get(drf_request)
        view.get(drf_request)
        assert get_count == 1
        view.post(drf_request)
        view.post(drf_request)
        assert post_count == 1


class TestKeyConstructorComposition:

    def test_combines_partition_constant_query_serializer_and_args_fields(
        self, drf_request
    ):
        call_count = 0

        @cache_result(
            {
                "fields": {
                    "constant": ConstantKeyField("version", "1.0"),
                    "query": QueryParamsKeyField(["page", "size"]),
                    "user": RequestValueKeyField("user.profile.id"),
                    "args": ArgsKeyField(["category"]),
                    "serializer": DrfSerializerKeyField(MockUserSerializer),
                },
                "key_identifier": "integrated_view",
            },
            ttl=3600,
        )
        def integrated_view(request, category):
            nonlocal call_count
            call_count += 1
            return {
                "category": category,
                "page": request.query_params.get("page"),
                "call_count": call_count,
            }

        result1 = integrated_view(drf_request, "electronics")
        assert call_count == 1
        result2 = integrated_view(drf_request, "electronics")
        assert call_count == 1
        assert result1 == result2
        integrated_view(drf_request, "books")
        assert call_count == 2


class TestGetWithMetadata:

    def test_get_with_metadata_returns_value_and_metadata_dict(self):
        @cache_result({"fields": {"arg": ArgsKeyField(["x"])}}, ttl=10)
        def f(x: int):
            return x * 2

        f(5)

        value, meta = f.get_with_metadata(5)
        only_value = f.get_cache_only(5)
        assert value == only_value
        assert value == 10
        assert isinstance(meta, dict)
        assert "cached_at" in meta
        assert meta["cache_status"] == "HIT"

    def test_get_cached_metadata_returns_none_before_call_and_dict_after(self):
        calls = {"n": 0}

        @cache_result(
            {
                "fields": {
                    "const": ConstantKeyField("v", "1"),
                    "arg": ArgsKeyField(["x"]),
                }
            },
            ttl=10,
        )
        def f(x: int):
            calls["n"] += 1
            return calls["n"]

        assert f.get_cached_metadata(5) is None
        assert f(5) == 1
        meta = f.get_cached_metadata(5)
        assert isinstance(meta, dict)
        assert "cached_at" in meta
        assert "cache_reset_at" in meta

    def test_get_with_metadata_returns_tuple_after_warm_call(self):
        @cache_result({"fields": {"arg": ArgsKeyField(["x"])}}, ttl=10)
        def f(x: int):
            return x * 2

        f(3)
        result = f.get_with_metadata(3)
        assert isinstance(result, tuple)
        assert result[0] == 6
        assert isinstance(result[1], dict)
        assert "cached_at" in result[1]


class TestSetResponseCacheHeader:

    def test_writes_cached_at_and_status_headers_on_response(self):
        from rest_framework.renderers import JSONRenderer
        from rest_framework.response import Response as DRFResponse

        from restflow.caching import set_response_cache_header

        response = DRFResponse(data={"ok": True})
        response.accepted_renderer = JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        response.render()

        metadata = {
            "cached_at": "2024-01-01T00:00:00",
            "cache_status": "HIT",
        }
        result = set_response_cache_header(response, metadata)
        assert result["X-Cached-at"] == "2024-01-01T00:00:00"
        assert result["X-Cache-status"] == "HIT"

    def test_returns_response_unchanged_when_metadata_is_empty(self):
        from restflow.caching import set_response_cache_header

        class _Resp(dict):
            pass

        response = _Resp()
        assert set_response_cache_header(response, None) is response
        assert set_response_cache_header(response, {}) is response
        assert "X-Cached-at" not in response

    def test_writes_reset_at_header_when_present(self):
        from restflow.caching import set_response_cache_header

        class _Resp(dict):
            pass

        response = _Resp()
        metadata = {"cache_reset_at": "2024-01-01T01:00:00"}
        result = set_response_cache_header(response, metadata)
        assert result["X-Cache-reset-at"] == "2024-01-01T01:00:00"


class TestCacheIf:

    KEY = {"fields": {"c": ConstantKeyField("v", "1")}}

    def test_cache_if_true_caches_returned_value(self):
        call_count = 0

        @cache_result(self.KEY, cache_if=lambda x: x == "cache_me")
        def f():
            nonlocal call_count
            call_count += 1
            return "cache_me"

        assert f() == "cache_me"
        assert f() == "cache_me"
        assert call_count == 1

    def test_cache_if_false_skips_caching(self):
        call_count = 0

        @cache_result(self.KEY, cache_if=lambda x: x == "cache_me")
        def f():
            nonlocal call_count
            call_count += 1
            return "skip_me"

        assert f() == "skip_me"
        assert f() == "skip_me"
        assert call_count == 2

    def test_cache_if_receives_the_actual_function_result(self):
        received = []

        @cache_result(self.KEY, cache_if=lambda x: (received.append(x), True)[1])
        def f():
            return {"status": "ok", "count": 5}

        f()
        assert received == [{"status": "ok", "count": 5}]

    def test_cache_unless_skips_when_predicate_returns_true(self):
        call_count = 0

        @cache_result(self.KEY, cache_unless=lambda x: x is None)
        def f():
            nonlocal call_count
            call_count += 1

        assert f() is None
        assert f() is None
        assert call_count == 2

    def test_cache_unless_caches_when_predicate_returns_false(self):
        call_count = 0

        @cache_result(self.KEY, cache_unless=lambda x: x is None)
        def f():
            nonlocal call_count
            call_count += 1
            return "value"

        assert f() == "value"
        assert f() == "value"
        assert call_count == 1

    def test_cache_unless_skips_empty_dict(self):
        call_count = 0

        @cache_result(self.KEY, cache_unless=lambda x: not x)
        def f():
            nonlocal call_count
            call_count += 1
            return {}

        assert f() == {}
        assert f() == {}
        assert call_count == 2

    def test_cache_unless_caches_non_empty_dict(self):
        call_count = 0

        @cache_result(self.KEY, cache_unless=lambda x: not x)
        def f():
            nonlocal call_count
            call_count += 1
            return {"key": "val"}

        assert f() == {"key": "val"}
        assert f() == {"key": "val"}
        assert call_count == 1

    def test_default_behavior_caches_every_result_including_falsy(self):
        call_count = 0

        @cache_result(self.KEY)
        def f():
            nonlocal call_count
            call_count += 1

        assert f() is None
        assert f() is None
        assert call_count == 1

        call_count_list = 0

        @cache_result({"fields": {"c": ConstantKeyField("v", "list")}})
        def g():
            nonlocal call_count_list
            call_count_list += 1
            return []

        assert g() == []
        assert g() == []
        assert call_count_list == 1

    def test_cache_unless_with_custom_predicate(self):
        call_count = 0

        @cache_result(self.KEY, cache_unless=lambda x: x.get("error") is not None)
        def f():
            nonlocal call_count
            call_count += 1
            return {"error": "something went wrong"}

        assert f() == {"error": "something went wrong"}
        assert f() == {"error": "something went wrong"}
        assert call_count == 2
