from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Union, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Model
from rest_framework import fields as drf_fields
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField, empty, get_error_detail
from rest_framework.serializers import raise_errors_on_nested_writes
from rest_framework.settings import api_settings
from rest_framework.utils import model_meta
from typing_extensions import dataclass_transform

from restflow.helpers import (
    RESERVED_SERIALIZER_ATTRS,
    maybe_await,
    require_sync,
)
from restflow.serializers.fields import Field, get_field_from_type
from restflow.serializers.validated_data import (
    ValidatedData,
    transform_validated_data,
)

if TYPE_CHECKING:
    from typing import Self


def build_explicit_fields(attrs: dict) -> list[tuple[str, drf_fields.Field]]:
    # Explicitly declared fields, DRF field instances
    fields = [
        (name, attrs.pop(name))
        for name, obj in list(attrs.items())
        if isinstance(obj, drf_fields.Field) and obj.__class__ is not Field
    ]
    fields.sort(key=lambda x: x[1]._creation_counter)
    return fields


def build_annotated_fields(
    klass, attrs: dict, existing_names: set[str]
) -> list[tuple[str, drf_fields.Field]]:
    # Fields generated from annotations IE: id: int, value: str
    annotations = getattr(klass, "__annotations__", {})
    result = []
    for field_name, field_type in annotations.items():
        if field_name in existing_names:
            continue
        if field_name in RESERVED_SERIALIZER_ATTRS:
            msg = (
                f"`{field_name}` collides with a Serializer attribute. "
                f"Choose a different name."
            )
            raise ValueError(msg)
        attr = klass.__dict__.get(field_name)
        # If there is a Field instance in the class
        # It must get preference over annotation.
        if attr is not None and attr.__class__ is Field:
            attrs.pop(field_name, None)
            result.append(
                (
                    field_name,
                    attr.clone(_type=field_type, field_name=field_name),
                )
            )
            continue
        result.append(
            (field_name, get_field_from_type(field_type, field_name=field_name))
        )
    return result


@dataclass_transform(field_specifiers=(Field,), eq_default=False)
class SerializerMetaClass(drf_serializers.SerializerMetaclass):
    """Metaclass that walks type annotations to populate _declared_fields, ordering inherited then annotated then explicit."""

    def __new__(cls, name, bases, attrs):
        klass = type.__new__(cls, name, bases, attrs)
        explicit = build_explicit_fields(attrs)
        explicit_names = {n for n, _ in explicit}
        annotated = build_annotated_fields(klass, attrs, explicit_names)
        known = explicit_names | {n for n, _ in annotated}
        inherited = []
        for base in bases:
            for n, f in getattr(base, "_declared_fields", {}).items():
                if n in known:
                    continue
                inherited.append((n, f))
                known.add(n)
        klass._declared_fields = dict(inherited + annotated + explicit)
        return klass


class AsyncSerializerMixin:
    """Sync hooks refuse async user callables. async variants await them."""

    def to_internal_value(self, data):
        """Convert primitive input data to native Python values, refusing async validate_<name> hooks."""
        if not isinstance(data, Mapping):
            message = self.error_messages["invalid"].format(
                datatype=type(data).__name__,
            )
            raise ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [message]},
                code="invalid",
            )

        ret: dict[str, Any] = {}
        errors: dict[str, Any] = {}
        for field in self._writable_fields:
            validate_method = getattr(self, f"validate_{field.field_name}", None)
            primitive_value = field.get_value(data)
            try:
                validated_value = field.run_validation(primitive_value)
                if validate_method is not None:
                    validated_value = require_sync(
                        validate_method(validated_value),
                        "ato_internal_value",
                    )
            except ValidationError as exc:
                errors[field.field_name] = exc.detail
            except DjangoValidationError as exc:
                errors[field.field_name] = get_error_detail(exc)
            except SkipField:
                pass
            else:
                self.set_value(ret, field.source_attrs, validated_value)

        if errors:
            raise ValidationError(errors)

        return ret

    def run_validation(self, data=empty):
        """Run validators and the user-supplied validate hook, refusing async user callables."""
        is_empty_value, data = self.validate_empty_values(data)
        if is_empty_value:
            return data

        value = self.to_internal_value(data)
        try:
            self.run_validators(value)
            value = require_sync(self.validate(value), "arun_validation")
            assert value is not None, ".validate() should return the validated data"
        except (ValidationError, DjangoValidationError) as exc:
            raise ValidationError(
                detail=drf_serializers.as_serializer_error(exc)
            ) from exc

        return value

    def save(self, **kwargs):
        """Persist validated data via create or update, refusing async create or update overrides."""
        assert hasattr(self, "_errors"), (
            "You must call `.is_valid()` before calling `.save()`."
        )
        assert not self.errors, (
            "You cannot call `.save()` on a serializer with invalid data."
        )
        assert "commit" not in kwargs, (
            "'commit' is not a valid keyword argument to the 'save()' method."
        )
        assert not hasattr(self, "_data"), (
            "You cannot call `.save()` after accessing `serializer.data`."
        )

        validated_data = {**self.validated_data, **kwargs}
        if self.instance is not None:
            self.instance = require_sync(
                self.update(self.instance, validated_data),
                "asave",
            )
            assert self.instance is not None, (
                "`update()` did not return an object instance."
            )
        else:
            self.instance = require_sync(
                self.create(validated_data),
                "asave",
            )
            assert self.instance is not None, (
                "`create()` did not return an object instance."
            )

        return self.instance

    async def ato_internal_value(self, data):
        """Async variant of to_internal_value that awaits async validate_<name> hooks."""
        if not isinstance(data, Mapping):
            message = self.error_messages["invalid"].format(
                datatype=type(data).__name__,
            )
            raise ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [message]},
                code="invalid",
            )

        ret: dict[str, Any] = {}
        errors: dict[str, Any] = {}
        for field in self._writable_fields:
            validate_method = getattr(self, f"validate_{field.field_name}", None)
            primitive_value = field.get_value(data)
            try:
                validated_value = field.run_validation(primitive_value)
                if validate_method is not None:
                    validated_value = await maybe_await(
                        validate_method(validated_value)
                    )
            except ValidationError as exc:
                errors[field.field_name] = exc.detail
            except DjangoValidationError as exc:
                errors[field.field_name] = get_error_detail(exc)
            except SkipField:
                pass
            else:
                self.set_value(ret, field.source_attrs, validated_value)

        if errors:
            raise ValidationError(errors)

        return ret

    async def avalidate(self, attrs):
        """Async variant of validate. Default returns attrs unchanged."""
        return attrs

    async def arun_validation(self, data=empty):
        """Async variant of run_validation that awaits the validate hook."""
        is_empty_value, data = self.validate_empty_values(data)
        if is_empty_value:
            return data

        value = await self.ato_internal_value(data)
        try:
            self.run_validators(value)
            value = await maybe_await(self.validate(value))
            assert value is not None, ".validate() should return the validated data"
        except (ValidationError, DjangoValidationError) as exc:
            raise ValidationError(
                detail=drf_serializers.as_serializer_error(exc)
            ) from exc

        return value

    async def ais_valid(self, *, raise_exception: bool = False):
        """Async variant of is_valid that drives arun_validation."""
        assert hasattr(self, "initial_data"), (
            "Cannot call `.ais_valid()` as no `data=` keyword argument was "
            "passed when instantiating the serializer instance."
        )

        if not hasattr(self, "_validated_data"):
            try:
                self._validated_data = await self.arun_validation(self.initial_data)
            except ValidationError as exc:
                self._validated_data = {}
                self._errors = exc.detail
            else:
                self._errors = {}

        if self._errors and raise_exception:
            raise ValidationError(self.errors)

        return not bool(self._errors)

    async def acreate(self, validated_data):
        """Async variant of create. Subclasses must implement it."""
        msg = "`acreate()` must be implemented."
        raise NotImplementedError(msg)

    async def aupdate(self, instance, validated_data):
        """Async variant of update. Subclasses must implement it."""
        msg = "`aupdate()` must be implemented."
        raise NotImplementedError(msg)

    async def asave(self, **kwargs):
        """Async variant of save that awaits acreate or aupdate, falling back to the sync create or update when the async variant is not overridden."""
        assert hasattr(self, "_errors"), (
            "You must call `.ais_valid()` (or `.is_valid()`) before calling `.asave()`."
        )
        assert not self.errors, (
            "You cannot call `.asave()` on a serializer with invalid data."
        )
        assert "commit" not in kwargs, (
            "'commit' is not a valid keyword argument to the 'asave()' method."
        )
        assert not hasattr(self, "_data"), (
            "You cannot call `.asave()` after accessing `serializer.data`."
        )

        validated_data = {**self.validated_data, **kwargs}
        if self.instance is not None:
            self.instance = await maybe_await(
                self.aupdate(self.instance, validated_data)
                if type(self).aupdate is not AsyncSerializerMixin.aupdate
                else self.update(self.instance, validated_data)
            )
            assert self.instance is not None, (
                "`aupdate()` did not return an object instance."
            )
        else:
            self.instance = await maybe_await(
                self.acreate(validated_data)
                if type(self).acreate is not AsyncSerializerMixin.acreate
                else self.create(validated_data)
            )
            assert self.instance is not None, (
                "`acreate()` did not return an object instance."
            )

        return self.instance

    async def ato_representation(self, instance):
        """Async variant of to_representation that awaits an async override when present. Nested async serializers are not auto-awaited."""
        return await maybe_await(self.to_representation(instance))


class TypedValidatedDataMixin:
    """Override DRF's validated_data property to return a ValidatedData wrapper recursively built from the validated tree. Typed as Self so IDE autocomplete resolves to the field annotations declared on the class."""

    @property
    def validated_data(self) -> "Self":
        if not hasattr(self, "_validated_data"):
            msg = (
                "You must call `.is_valid()` before "
                "accessing `.validated_data`."
            )
            raise AssertionError(msg)
        vd = self._validated_data
        if not isinstance(vd, ValidatedData):
            vd = transform_validated_data(vd)
            self._validated_data = vd
        return cast("Self", vd)


class Serializer(
    TypedValidatedDataMixin,
    AsyncSerializerMixin,
    drf_serializers.Serializer,
    metaclass=SerializerMetaClass,
):
    """A DRF Serializer driven by Python type annotations.

        class UserSer(Serializer):
            name: str
            age: int
            email: Email
            role: Literal["admin", "user"]
            tags: list[str]
            bio: str | None

    Adds annotation-driven field declaration and an async surface (ais_valid, asave, and friends) on top of DRF's Serializer.
    """


@dataclass_transform(field_specifiers=(Field,), eq_default=False)
class ModelSerializerMetaClass(SerializerMetaClass):
    """Metaclass that auto-includes annotated names into Meta.fields so the user does not have to list them twice."""

    def __new__(cls, name, bases, attrs):
        klass = super().__new__(cls, name, bases, attrs)
        cls._merge_annotations_into_meta_fields(klass)
        return klass

    @classmethod
    def _merge_annotations_into_meta_fields(cls, klass):
        annotated_names = list(getattr(klass, "__annotations__", {}).keys())
        if not annotated_names:
            return
        meta = klass.__dict__.get("Meta")
        if meta is None:
            return
        fields = getattr(meta, "fields", None)
        if fields is None or fields == drf_serializers.ALL_FIELDS:
            return
        if not isinstance(fields, (list, tuple)):
            return
        existing = list(fields)
        added = False
        for n in annotated_names:
            if n not in existing:
                existing.append(n)
                added = True
        if not added:
            return
        meta.fields = tuple(existing) if isinstance(fields, tuple) else list(existing)


class AsyncModelSerializerMixin:
    """Default async create and update for ModelSerializer subclasses. Mirrors DRF's sync ModelSerializer.create and ModelSerializer.update logic with the async ORM (acreate, asave, aset)."""

    async def acreate(self, validated_data):
        raise_errors_on_nested_writes("create", self, validated_data)
        ModelClass = self.Meta.model
        info = model_meta.get_field_info(ModelClass)
        many_to_many = {}
        for field_name, relation_info in info.relations.items():
            if relation_info.to_many and (field_name in validated_data):
                many_to_many[field_name] = validated_data.pop(field_name)
        instance = await ModelClass._default_manager.acreate(**validated_data)
        for field_name, value in many_to_many.items():
            await getattr(instance, field_name).aset(value)
        return instance

    async def aupdate(self, instance, validated_data):
        raise_errors_on_nested_writes("update", self, validated_data)
        info = model_meta.get_field_info(instance)
        m2m_fields = []
        for attr, value in validated_data.items():
            if attr in info.relations and info.relations[attr].to_many:
                m2m_fields.append((attr, value))
            else:
                setattr(instance, attr, value)
        await instance.asave()
        for attr, value in m2m_fields:
            await getattr(instance, attr).aset(value)
        return instance


class ModelSerializer(
    TypedValidatedDataMixin,
    AsyncModelSerializerMixin,
    AsyncSerializerMixin,
    drf_serializers.ModelSerializer,
    metaclass=ModelSerializerMetaClass,
):
    """A DRF ModelSerializer driven by both Meta.model and type annotations.

        class UserSer(ModelSerializer):
            extra: str = Field(write_only=True)

            class Meta:
                model = User
                fields = ["id", "username"]

    """


class HyperlinkedModelSerializer(
    TypedValidatedDataMixin,
    AsyncModelSerializerMixin,
    AsyncSerializerMixin,
    drf_serializers.HyperlinkedModelSerializer,
    metaclass=ModelSerializerMetaClass,
):
    """A ModelSerializer that renders related fields and the identity field as hyperlinks instead of primary keys. Adds annotation-driven fields and the async serializer surface."""


class InlineSerializer:
    """Factory that builds a Serializer or ModelSerializer class on the fly.

        Ser = InlineSerializer(
            name="UserSer",
            fields={"name": str, "age": int, "email": Email},
        )
        ModelSer = InlineSerializer(
            name="UserSer",
            model=User,
            model_fields=["id", "username"],
            fields={"extra": str},
        )

    Returns a ModelSerializer subclass when model is given, otherwise a Serializer subclass.
    """

    def __new__(
        cls,
        name: str | None = None,
        fields: dict[str, Union[drf_fields.Field, type]] | None = None,
        extra_kwargs: dict[str, dict] | None = None,
        read_only_fields: list[str] | tuple[str, ...] | None = None,
        write_only_fields: list[str] | tuple[str, ...] | None = None,
        model: type[Model] | None = None,
        model_fields: list[str] | tuple[str, ...] | str | None = None,
    ):
        if not (model or fields):
            msg = "Either `model` or `fields` must be provided."
            raise ValueError(msg)

        attrs: dict[str, Any] = {}
        if isinstance(fields, dict):
            for field_name, field in fields.items():
                if isinstance(field, drf_fields.Field):
                    attrs[field_name] = field
                else:
                    attrs[field_name] = get_field_from_type(
                        field, field_name=field_name
                    )

        if model:
            class_name = name or f"{model.__name__}Serializer"
            meta_attrs: dict[str, Any] = {"model": model}
            meta_attrs["fields"] = (
                list(model_fields)
                if model_fields is not None
                else (
                    list(fields.keys())
                    if isinstance(fields, dict)
                    else "__all__"
                )
            )
            combined_extra = {k: dict(v) for k, v in (extra_kwargs or {}).items()}
            for n in read_only_fields or []:
                combined_extra.setdefault(n, {})["read_only"] = True
            for n in write_only_fields or []:
                combined_extra.setdefault(n, {})["write_only"] = True
            if combined_extra:
                meta_attrs["extra_kwargs"] = combined_extra
            attrs["Meta"] = type("Meta", (), meta_attrs)
            klass = type(class_name, (ModelSerializer,), attrs)
            return cast(type[ModelSerializer], klass)

        class_name = name or "_Serializer"
        klass = type(class_name, (Serializer,), attrs)
        return cast(type[Serializer], klass)
