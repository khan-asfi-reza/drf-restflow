import asyncio

import pytest

from restflow.serializers import ModelSerializer, Serializer
from tests.models import (
    SampleModel,
)


def _run(coro):
    return asyncio.run(coro)


def test_async_validate_field_method_works_under_ais_valid():
    class S(Serializer):
        name: str

        async def validate_name(self, value):
            return value.upper()

    s = S(data={"name": "lower"})
    assert _run(s.ais_valid())
    assert s.validated_data == {"name": "LOWER"}


def test_sync_is_valid_raises_on_async_validate_field_method():
    class S(Serializer):
        name: str

        async def validate_name(self, value):
            return value

    s = S(data={"name": "x"})
    with pytest.raises(TypeError, match="ato_internal_value"):
        s.is_valid()


def test_async_validate_top_level_works_under_ais_valid():
    class S(Serializer):
        a: int
        b: int

        async def validate(self, attrs):
            attrs["sum"] = attrs["a"] + attrs["b"]
            return attrs

    s = S(data={"a": 2, "b": 3})
    assert _run(s.ais_valid())
    assert s.validated_data["sum"] == 5


def test_sync_run_validation_raises_on_async_validate():
    class S(Serializer):
        a: int

        async def validate(self, attrs):
            return attrs

    s = S(data={"a": 1})
    with pytest.raises(TypeError, match="arun_validation"):
        s.is_valid()


def test_sync_validators_still_work_in_async_path():
    class S(Serializer):
        name: str

        def validate_name(self, value):
            return value + "!"

    s = S(data={"name": "x"})
    assert _run(s.ais_valid())
    assert s.validated_data == {"name": "x!"}


def test_async_validation_collects_errors():
    class S(Serializer):
        age: int

        async def validate_age(self, value):
            if value < 0:
                from rest_framework.exceptions import ValidationError

                raise ValidationError("must be positive")
            return value

    s = S(data={"age": -1})
    assert not _run(s.ais_valid())
    assert "age" in s.errors


def test_asave_with_acreate_returns_instance():
    instances = []

    class Stub:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.pk = len(instances) + 1
            instances.append(self)

    class S(Serializer):
        integer_field: int

        async def acreate(self, validated_data):
            return Stub(**validated_data)

    s = S(data={"integer_field": 7})
    assert _run(s.ais_valid())
    instance = _run(s.asave())
    assert instance.pk == 1
    assert instance.integer_field == 7


def test_asave_with_aupdate_returns_instance():
    class Stub:
        integer_field = 1

    instance = Stub()

    class S(Serializer):
        integer_field: int

        async def aupdate(self, instance, validated_data):
            for k, v in validated_data.items():
                setattr(instance, k, v)
            return instance

    s = S(instance=instance, data={"integer_field": 99})
    assert _run(s.ais_valid())
    _run(s.asave())
    assert instance.integer_field == 99


def test_asave_falls_back_to_sync_create_when_no_acreate():
    class Stub:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class S(Serializer):
        integer_field: int

        def create(self, validated_data):
            return Stub(**validated_data)

    s = S(data={"integer_field": 12})
    assert _run(s.ais_valid())
    instance = _run(s.asave())
    assert instance.integer_field == 12


def test_sync_save_raises_on_async_create():
    class S(Serializer):
        integer_field: int

        async def create(self, validated_data):
            return None

    s = S(data={"integer_field": 5})
    s.is_valid()
    with pytest.raises(TypeError, match="asave"):
        s.save()


def test_ato_representation_awaits_async_override():
    class S(Serializer):
        name: str

        async def to_representation(self, instance):
            return {"name": instance["name"].upper()}

    s = S()
    rep = _run(s.ato_representation({"name": "lower"}))
    assert rep == {"name": "LOWER"}


def test_default_save_path_raises_not_implemented():
    class S(Serializer):
        integer_field: int

    s = S(data={"integer_field": 1})
    _run(s.ais_valid())
    with pytest.raises(NotImplementedError, match="create"):
        _run(s.asave())


def test_default_aupdate_falls_through_to_sync_update():
    class S(Serializer):
        integer_field: int

    instance = type("I", (), {"integer_field": 0, "save": lambda self: None})()
    s = S(instance=instance, data={"integer_field": 1})
    _run(s.ais_valid())
    with pytest.raises(NotImplementedError, match="update"):
        _run(s.asave())


def test_explicit_acreate_path_raises_acreate_message():
    class S(Serializer):
        integer_field: int

        async def acreate(self, validated_data):
            await super().acreate(validated_data)

    s = S(data={"integer_field": 1})
    _run(s.ais_valid())
    with pytest.raises(NotImplementedError, match="acreate"):
        _run(s.asave())


def test_async_model_serializer_acreate_with_stub():
    class Stub:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.pk = 1

    class S(ModelSerializer):
        class Meta:
            model = SampleModel
            fields = ["integer_field"]

        async def acreate(self, validated_data):
            return Stub(**validated_data)

    s = S(data={"integer_field": 21})
    assert _run(s.ais_valid())
    instance = _run(s.asave())
    assert instance.integer_field == 21


def test_ato_internal_value_raises_when_data_is_not_mapping():
    from rest_framework.exceptions import ValidationError

    class S(Serializer):
        name: str

        async def validate_name(self, value):
            return value

    s = S(data="not a dict")
    with pytest.raises(ValidationError):
        _run(s.ais_valid(raise_exception=True))


def test_ato_internal_value_django_validation_error_collected():
    from django.core.exceptions import ValidationError as DjangoValidationError

    msg = "bad name"

    class S(Serializer):
        name: str

        async def validate_name(self, value):
            raise DjangoValidationError(msg)

    s = S(data={"name": "x"})
    assert not _run(s.ais_valid())
    assert "name" in s.errors


def test_ato_internal_value_skipfield_is_swallowed():
    from rest_framework.fields import SkipField

    class S(Serializer):
        name: str

        async def validate_name(self, value):
            raise SkipField()

    s = S(data={"name": "x"})
    assert _run(s.ais_valid())
    assert "name" not in s.validated_data


def test_avalidate_default_returns_attrs_unchanged():
    class S(Serializer):
        name: str

    s = S(data={"name": "x"})
    assert _run(s.ais_valid())
    assert s.validated_data == {"name": "x"}
    assert _run(s.avalidate({"name": "x"})) == {"name": "x"}


def test_arun_validation_returns_data_for_empty_when_read_only():
    from rest_framework.fields import empty

    class S(Serializer):
        name: str

    s = S(read_only=True, default={"name": "x"})
    result = _run(s.arun_validation(empty))
    assert result == {"name": "x"}


def test_arun_validation_wraps_django_validation_error():
    from django.core.exceptions import (
        ValidationError as DjangoValidationError,
    )
    from rest_framework.exceptions import ValidationError

    msg = "bad"

    class S(Serializer):
        a: int

        async def validate(self, attrs):
            raise DjangoValidationError(msg)

    s = S(data={"a": 1})
    with pytest.raises(ValidationError):
        _run(s.ais_valid(raise_exception=True))


def test_ais_valid_raise_exception_propagates():
    from rest_framework.exceptions import ValidationError

    class S(Serializer):
        a: int

    s = S(data={"a": "not-int"})
    with pytest.raises(ValidationError):
        _run(s.ais_valid(raise_exception=True))


def test_explicit_aupdate_path_raises_aupdate_message():
    class S(Serializer):
        integer_field: int

        async def aupdate(self, instance, validated_data):
            await super().aupdate(instance, validated_data)

    instance = type("I", (), {"integer_field": 0})()
    s = S(instance=instance, data={"integer_field": 1})
    _run(s.ais_valid())
    with pytest.raises(NotImplementedError, match="aupdate"):
        _run(s.asave())
