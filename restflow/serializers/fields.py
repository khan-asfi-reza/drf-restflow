import datetime
import decimal
import inspect
import uuid
from typing import TYPE_CHECKING, Any

from rest_framework import fields as drf_fields
from rest_framework.serializers import BaseSerializer

from restflow.helpers import (
    BlankableString,
    Email,
    IPAddress,
    resolve_field_from_type,
)

SERIALIZER_TYPE_ASSERTION_ERROR = "annotation must be a supported type"

if TYPE_CHECKING:

    def Field(**kwargs: Any) -> Any:
        """Sentinel field that carries DRF kwargs to an annotated field while letting the annotation pick the final field class.

        Example::

            class Ser(Serializer):
                email: Email = Field(write_only=True)
        """

else:

    class Field:
        """Sentinel field that carries DRF kwargs to an annotated field while letting the annotation pick the final field class.

        Example::

            class Ser(Serializer):
                email: Email = Field(write_only=True)
        """

        def __init__(self, **kwargs):
            """Capture the kwargs so the metaclass can clone them onto the annotation-resolved field."""
            self.field_kwargs = dict(kwargs)

        def clone(self, _type=None, field_name=None, **inner_kwargs):
            """Return a real field for the given type annotation, merging the captured kwargs with inner_kwargs."""
            kwargs = {**self.field_kwargs, **inner_kwargs}
            if _type is not None:
                return get_field_from_type(_type, field_name=field_name, **kwargs)
            return self.__class__(**kwargs)


def is_serializer_subclass(t) -> bool:
    return inspect.isclass(t) and issubclass(t, BaseSerializer)

def build_nested_serializer(t, kwargs: dict):
    return t(**kwargs)


class DecimalField(drf_fields.DecimalField):
    """DRF DecimalField with restflow defaults for max_digits and decimal_places."""

    def __init__(self, *, max_digits: int = 20, decimal_places: int = 6, **kwargs):
        super().__init__(max_digits=max_digits, decimal_places=decimal_places, **kwargs)

class BlankableCharField(drf_fields.CharField):
    def __init__(self, **kwargs):
        super().__init__(allow_blank=True, **kwargs)




SerializerFieldMap: dict[type, type[drf_fields.Field]] = {
    int: drf_fields.IntegerField,
    float: drf_fields.FloatField,
    str: drf_fields.CharField,
    bool: drf_fields.BooleanField,
    bytes: drf_fields.CharField,
    datetime.datetime: drf_fields.DateTimeField,
    datetime.date: drf_fields.DateField,
    datetime.time: drf_fields.TimeField,
    datetime.timedelta: drf_fields.DurationField,
    decimal.Decimal: DecimalField,
    uuid.UUID: drf_fields.UUIDField,
    Email: drf_fields.EmailField,
    IPAddress: drf_fields.IPAddressField,
    dict: drf_fields.DictField,
    Any: drf_fields.JSONField,
    BlankableString: BlankableCharField,
}


def get_field_from_type(data_type, field_name: str | None = None, **field_kwargs):
    """Resolve a Python type annotation to a DRF serializer Field, handling nested Serializers, Optional, Literal, and list[T]."""
    return resolve_field_from_type(
        data_type,
        type_map=SerializerFieldMap,
        field_name=field_name,
        list_field_class=drf_fields.ListField,
        choice_field_class=drf_fields.ChoiceField,
        nested_predicate=is_serializer_subclass,
        nested_factory=build_nested_serializer,
        error_message=SERIALIZER_TYPE_ASSERTION_ERROR,
        allow_null_on_optional=True,
        **field_kwargs,
    )
