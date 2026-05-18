import asyncio
import collections.abc
import copy
import json
import pickle
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from restflow.serializers import (
    Email,
    Field,
    Serializer,
    ValidatedData,
)
from restflow.serializers.validated_data import normalize_default, transform_validated_data


def _run(coro):
    return asyncio.run(coro)


def test_attribute_and_item_access_match():
    class S(Serializer):
        name: str
        age: int

    s = S(data={"name": "x", "age": 1})
    assert s.is_valid()
    vd = s.validated_data

    assert isinstance(vd, ValidatedData)
    assert vd.name == "x"
    assert vd["name"] == "x"
    assert vd.age == 1
    assert vd.get("name") == "x"


def test_is_dict_subclass_and_mapping():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    vd = s.validated_data

    assert isinstance(vd, dict)
    assert isinstance(vd, collections.abc.Mapping)
    assert isinstance(vd, collections.abc.MutableMapping)
    assert vd == {"a": 1}
    assert dict(vd) == {"a": 1}


def test_unpacking_into_callable():
    class Stub:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class S(Serializer):
        name: str
        age: int

    s = S(data={"name": "x", "age": 1})
    s.is_valid()
    obj = Stub(**s.validated_data)
    assert obj.name == "x"
    assert obj.age == 1


def test_optional_field_returns_none():
    class S(Serializer):
        bio: str | None

    s = S(data={"bio": None})
    s.is_valid()
    assert s.validated_data.bio is None


def test_nested_serializer_is_wrapped():
    class Inner(Serializer):
        a: int
        b: str

    class Outer(Serializer):
        x: int
        y: Inner

    s = Outer(data={"x": 1, "y": {"a": 2, "b": "hi"}})
    s.is_valid()
    vd = s.validated_data

    assert isinstance(vd.y, ValidatedData)
    assert vd.y.a == 2
    assert vd.y.b == "hi"


def test_list_of_nested_is_wrapped_per_element():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        entries: list[Inner]

    s = Outer(data={"entries": [{"name": "a"}, {"name": "b"}]})
    s.is_valid()
    vd = s.validated_data

    assert isinstance(vd.entries, list)
    assert all(isinstance(item, ValidatedData) for item in vd.entries)
    assert vd.entries[0].name == "a"
    assert vd.entries[1].name == "b"


def test_field_name_colliding_with_dict_method_reachable_via_item():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        items: list[Inner]

    s = Outer(data={"items": [{"name": "a"}]})
    s.is_valid()
    vd = s.validated_data

    assert callable(vd.items)
    payload = vd["items"]
    assert isinstance(payload, list)
    assert payload[0].name == "a"


def test_deeply_nested_resolves():
    class Leaf(Serializer):
        v: int

    class Mid(Serializer):
        leaf: Leaf

    class Root(Serializer):
        mid: Mid

    s = Root(data={"mid": {"leaf": {"v": 42}}})
    s.is_valid()
    assert s.validated_data.mid.leaf.v == 42


def test_missing_attribute_raises_attribute_error():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    vd = s.validated_data

    with pytest.raises(AttributeError):
        _ = vd.missing
    with pytest.raises(KeyError):
        _ = vd["missing"]


def test_attribute_write_mirrors_item_write():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    vd = s.validated_data

    vd.b = 2
    assert vd["b"] == 2
    vd["c"] = 3
    assert vd.c == 3

    del vd.b
    assert "b" not in vd


def test_validate_can_inject_keys_after_wrap():
    class S(Serializer):
        a: int
        b: int

        def validate(self, attrs):
            attrs["sum"] = attrs["a"] + attrs["b"]
            return attrs

    s = S(data={"a": 1, "b": 2})
    s.is_valid()
    assert s.validated_data.sum == 3


def test_equality_with_plain_dict():
    class S(Serializer):
        a: int
        b: str

    s = S(data={"a": 1, "b": "x"})
    s.is_valid()
    assert s.validated_data == {"a": 1, "b": "x"}


def test_repr_distinguishes_from_dict():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    assert repr(s.validated_data).startswith("ValidatedData(")


def test_pickle_roundtrip_preserves_wrapping():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        inner: Inner

    s = Outer(data={"inner": {"name": "n"}})
    s.is_valid()

    revived = pickle.loads(pickle.dumps(s.validated_data))
    assert isinstance(revived, ValidatedData)
    assert revived.inner.name == "n"


def test_deepcopy_roundtrip_preserves_wrapping():
    class Inner(Serializer):
        name: str

    class Outer(Serializer):
        inner: Inner

    s = Outer(data={"inner": {"name": "n"}})
    s.is_valid()

    cloned = copy.deepcopy(s.validated_data)
    assert isinstance(cloned, ValidatedData)
    assert cloned.inner.name == "n"
    assert cloned == s.validated_data


def test_to_json_basic_roundtrip():
    class S(Serializer):
        a: int
        b: str

    s = S(data={"a": 1, "b": "x"})
    s.is_valid()
    assert json.loads(s.validated_data.to_json()) == {"a": 1, "b": "x"}


def test_to_json_indent_kwarg_honored():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    rendered = s.validated_data.to_json(indent=2)
    assert "\n  " in rendered


def test_to_json_decimal_serialized_via_default():
    class S(Serializer):
        price: Decimal

    s = S(data={"price": "10.5"})
    s.is_valid()
    payload = json.loads(s.validated_data.to_json())
    assert payload["price"] == "10.500000"


def test_to_json_user_default_chains_with_restflow_default():
    class Tagged:
        def __init__(self, value):
            self.value = value

    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    vd = s.validated_data
    vd.tag = Tagged("hello")

    def tagged_only(obj):
        if isinstance(obj, Tagged):
            return {"tag": obj.value}
        msg = "unsupported"
        raise TypeError(msg)

    rendered = vd.to_json(default=tagged_only)
    payload = json.loads(rendered)
    assert payload["tag"] == {"tag": "hello"}


def test_to_json_handles_datetime_date_uuid():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    vd = s.validated_data
    vd.when = datetime(2026, 5, 8, 12, 30, 0, tzinfo=timezone.utc)
    vd.day = date(2026, 5, 8)
    vd.id = UUID("12345678-1234-5678-1234-567812345678")

    payload = json.loads(vd.to_json())
    assert payload["when"].startswith("2026-05-08T12:30:00")
    assert payload["day"] == "2026-05-08"
    assert payload["id"] == "12345678-1234-5678-1234-567812345678"


def test_dunder_json_returns_plain_dict():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    plain = s.validated_data.__json__()
    assert type(plain) is dict
    assert plain == {"a": 1}


def test_write_only_field_still_present_in_validated_data():
    class S(Serializer):
        secret: str = Field(write_only=True)

    s = S(data={"secret": "shh"})
    s.is_valid()
    assert s.validated_data.secret == "shh"


def test_validated_data_before_is_valid_raises():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    with pytest.raises(AssertionError):
        _ = s.validated_data


def test_validated_data_idempotent_on_repeat_access():
    class S(Serializer):
        a: int

    s = S(data={"a": 1})
    s.is_valid()
    first = s.validated_data
    second = s.validated_data
    assert first is second


def test_async_path_yields_wrapped_validated_data():
    class Inner(Serializer):
        a: int

    class Outer(Serializer):
        x: int
        y: Inner

    s = Outer(data={"x": 1, "y": {"a": 2}})
    assert _run(s.ais_valid())
    vd = s.validated_data
    assert isinstance(vd, ValidatedData)
    assert vd.x == 1
    assert vd.y.a == 2


def test_async_validate_injects_keys_visible_via_attribute():
    class S(Serializer):
        a: int
        b: int

        async def validate(self, attrs):
            attrs["sum"] = attrs["a"] + attrs["b"]
            return attrs

    s = S(data={"a": 2, "b": 3})
    _run(s.ais_valid())
    assert s.validated_data.sum == 5


def test_email_field_value_accessible_as_attribute():
    class S(Serializer):
        email: Email

    s = S(data={"email": "a@example.com"})
    s.is_valid()
    assert s.validated_data.email == "a@example.com"


def test_delattr_missing_key_raises_attribute_error():
    vd = ValidatedData({"a": 1})
    with pytest.raises(AttributeError):
        del vd.missing


def test_restflow_default_unwraps_validated_data():
    vd = ValidatedData({"b": 2})
    plain = normalize_default(vd)
    assert type(plain) is dict
    assert plain == {"b": 2}


def test_restflow_default_raises_for_unsupported_type():
    class Unsupported:
        pass

    with pytest.raises(TypeError):
        normalize_default(Unsupported())


def test_to_json_chained_user_default_falls_back_to_restflow_default():
    def user_default(_obj):
        msg = "user can't handle"
        raise TypeError(msg)

    vd = ValidatedData({"price": Decimal("1.5")})
    rendered = vd.to_json(default=user_default)
    assert json.loads(rendered) == {"price": "1.5"}


def test_wrap_returns_existing_validated_data_unchanged():
    original = ValidatedData({"a": 1})
    assert transform_validated_data(original) is original


def test_wrap_top_level_list_initializes_seen_set():
    wrapped = transform_validated_data([{"a": 1}, {"a": 2}])
    assert all(isinstance(item, ValidatedData) for item in wrapped)
    assert wrapped[0].a == 1


def test_wrap_breaks_dict_cycle():
    payload: dict = {"a": 1}
    payload["self"] = payload
    wrapped = transform_validated_data(payload)
    assert wrapped.a == 1
    assert wrapped.self is payload


def test_wrap_breaks_list_cycle():
    payload: list = [1, 2]
    payload.append(payload)
    wrapped = transform_validated_data(payload)
    assert wrapped[0] == 1
    assert wrapped[2] is payload


def test_save_path_consumes_validated_data_via_unpack():
    captured = {}

    class S(Serializer):
        a: int
        b: str

        def create(self, validated_data):
            captured.update(validated_data)
            return type("I", (), {"pk": 1, **validated_data})()

    s = S(data={"a": 1, "b": "x"})
    s.is_valid()
    instance = s.save()
    assert captured == {"a": 1, "b": "x"}
    assert instance.a == 1
    assert instance.b == "x"
