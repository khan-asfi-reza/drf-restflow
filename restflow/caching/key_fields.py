import datetime
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from django.db import models
from django.http import QueryDict
from rest_framework import serializers

from restflow.caching.constants import MISSING_VALUE
from restflow.caching.hashing import hash_string


class CacheKeyField(ABC):
    """
    Base class for the pieces that go into a cache key.

    Each subclass pulls a piece of data out of a function call and
    turns it into a stable string.
    """

    def __init__(
        self,
        partition=False,
        hash_value=False,
        *_args,
        sort_lists: bool = True,
        **_kwargs,
    ):
        self.partition = partition
        self.hash_value = hash_value
        self.sort_lists = sort_lists

    @abstractmethod
    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:
        """Return a name-to-value payload extracted from the call."""
        raise NotImplementedError

    @staticmethod
    def _resolve_attr_path(obj, path):
        """Walk a dotted path on obj, returning the missing sentinel when a segment is absent."""
        if not path:
            return obj
        parts = path.split(".")
        current = obj

        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # Value or attribute does not exist.
                # So, return MISSING_VALUE
                return MISSING_VALUE

        return current

    def normalize(self, data):
        """Normalize cache key components for consistent cache key generation."""
        # Dictionary must be sorted, to ensure a deterministic cache key.
        # To opt in list / tuple sorting,  `sort_list` must be used.
        # Typically unsorted lists and sorted lists, carry different meaning.
        # For example: Queue[1, 2, 3] and Queue[3, 2, 1] are not same thing.
        # If a sorted list and unsorted list both carrys the same meaning,
        # sort_list can be used to normalize the list.
        if isinstance(data, dict):
            return {
                k: self.normalize(v) for k, v in sorted(data.items())
            }
        if isinstance(data, (list, tuple)):
            canonicalized = [self.normalize(item) for item in data]
            return sorted(canonicalized) if self.sort_lists else canonicalized
        if data is None:
            return "null"
        if isinstance(data, (datetime.date, datetime.datetime)):
            # Date type objects converted to iso format for consistency
            return data.isoformat()
        return str(data)

    def stringify(self, value):
        """Turn value into the string the cache key uses, hashing the result when hash_value is set."""
        # Before stringification every item is normalized for consistency.
        if isinstance(value, dict):
            # Dictionary items are joined by double pipe `||`,
            # and key-value pairs are joined by colon `:`.
            # For example: {"a": 1, "b": 2} -> "a:1||b:2"
            canonical = self.normalize(
                {k: self.stringify(v) for k, v in value.items()}
            )
            string = "||".join(f"{k}:{v}" for k, v in canonical.items())

        elif isinstance(value, (list, tuple)):
            # List items are joined by comma `,`
            # For example: [1, 2, 3] -> "1,2,3"
            canonical = self.normalize([self.stringify(v) for v in value])
            string = ",".join(canonical)

        else:
            string = self.normalize(value)

        return hash_string(string) if self.hash_value else string

    def get_cache_key_part(self, func, args, kwargs):
        """Return the string this field contributes to the cache key for the given call."""
        return self.stringify(self.get_key_payload(func, args, kwargs))

    def extract_request_object(
        self,
        func,
        args,
        kwargs,
        request_arg="request",
        normalize=False,
        view_self_request_fallback: bool = True,
    ):
        """Find the request object on the call, falling back to the DRF viewset convention when enabled."""
        if request_arg in kwargs:
            # Finding request through function keyword arguments.
            obj = kwargs[request_arg]
            return self._normalize_request(obj) if normalize else obj

        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        if request_arg in param_names:
            # Find request argument through function positional arguments.
            request_index = param_names.index(request_arg)
            if request_index < len(args):
                obj = args[request_index]
                return self._normalize_request(obj) if normalize else obj

        # For view classes, self.request is available as an attribute.
        # Use it as fallback.
        if (
            view_self_request_fallback
            and args
            and hasattr(args[0], "request")
        ):
            obj = args[0].request
            return self._normalize_request(obj) if normalize else obj

        return None

    @staticmethod
    def _normalize_request(obj):
        """Return a DRF-style request object."""
        if obj is None:
            return None
        if hasattr(obj, "query_params"):
            return obj
        if hasattr(obj, "request") and hasattr(obj.request, "query_params"):
            return obj.request
        return obj


class ConstantKeyField(CacheKeyField):
    """
    Cache-key field that contributes a fixed key-value pair on every call.

    Example:
        ::

            class UserKey(KeyConstructor):
                env = ConstantKeyField("env", "production")
                user = ArgsKeyField("user_id", partition=True)
    """

    def __init__(
        self,
        key: str,
        value: Any,
        *args,
        partition=False,
        hash_value=False,
        sort_lists: bool = False,
        **kwargs,
    ):
        super().__init__(
            *args,
            partition=partition,
            hash_value=hash_value,
            sort_lists=sort_lists,
            **kwargs,
        )
        self.key = key
        self.value = value

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:  # noqa: ARG002
        return {self.key: str(self.value)}


class RequestValueKeyField(CacheKeyField):
    """
    Cache-key field that reads a value off the request object.

    Example:
        ::

            class UserKey(KeyConstructor):
                user = RequestValueKeyField("user.id", partition=True)
    """

    def __init__(
        self,
        path: str,
        request_arg: str = "request",
        *args,
        partition=False,
        hash_value=False,
        sort_lists: bool = False,
        view_self_request_fallback: bool = True,
        **kwargs,
    ):
        super().__init__(
            *args,
            partition=partition,
            hash_value=hash_value,
            sort_lists=sort_lists,
            **kwargs,
        )
        self.path = path
        self.request_arg = request_arg
        self.view_self_request_fallback = view_self_request_fallback

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:
        request = self.extract_request_object(
            func,
            args,
            kwargs,
            self.request_arg,
            view_self_request_fallback=self.view_self_request_fallback,
        )
        if not request:
            return {}

        value = self._resolve_attr_path(request, self.path)
        return {self.path.replace(".", "_"): str(value)}


class QueryParamsKeyField(CacheKeyField):
    """
    Cache-key field that captures values from the request's query string.

    Example:
        ::

            class ListUsersKey(KeyConstructor):
                filters = QueryParamsKeyField(["status", "role"])
    """

    def __init__(
        self,
        params: str | list[str] = "*",
        request_arg: str = "request",
        *args,
        partition=False,
        hash_value=False,
        sort_lists: bool = False,
        view_self_request_fallback: bool = True,
        **kwargs,
    ):
        super().__init__(
            *args,
            partition=partition,
            hash_value=hash_value,
            sort_lists=sort_lists,
            **kwargs,
        )
        self.request_arg = request_arg
        self.params = params
        self.view_self_request_fallback = view_self_request_fallback

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:
        request = self.extract_request_object(
            func,
            args,
            kwargs,
            self.request_arg,
            normalize=True,
            view_self_request_fallback=self.view_self_request_fallback,
        )
        if not request or not hasattr(request, "query_params"):
            return {}

        query_params = request.query_params
        result = {}

        is_query_dict = isinstance(query_params, QueryDict)
        # Grab all query params if params is set to "*"
        expected_query_params = (
            self.params
            if isinstance(self.params, (list, tuple))
            else [self.params]
            if self.params != "*"
            else []
        )

        if is_query_dict:
            # QueryDict can have multiple values for the same key
            iterable = query_params.lists()
        else:
            iterable = query_params.items()

        for key, val in iterable:
            if key in expected_query_params or self.params == "*":
                if is_query_dict:
                    values = list(val)
                    # QueryDict for each key value is encapsulated in a list type object.
                    # Either get the only available value or get sorted list.
                    # Query params value list, order does not matter, so it is sorted.
                    if len(values) == 1:
                        result[key] = values[0]
                    else:
                        result[key] = sorted(values)
                else:
                    result[key] = val

        return result


class ArgsKeyField(CacheKeyField):
    """
    Cache-key field that captures function arguments by name.

    Example:
        ::

            class UserKey(KeyConstructor):
                user = ArgsKeyField("user_id", partition=True)
                lang = ArgsKeyField("lang")
    """

    def __init__(
        self,
        arguments: str | list[str] = "*",
        path: str | None = None,
        normalizer: Callable[[Any], Any] | None = None,
        *args,
        partition=False,
        hash_value=False,
        sort_lists: bool = False,
        **kwargs,
    ):
        super().__init__(
            *args,
            partition=partition,
            hash_value=hash_value,
            sort_lists=sort_lists,
            **kwargs,
        )
        self.arguments = arguments
        self.path = path
        self.normalizer = normalizer

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        result = {}
        # Grab all args if arguments is set to "*".
        # Or Grab the desired arugments only.
        # Does not fail if argument is not available.
        expected_args = (
            self.arguments
            if isinstance(self.arguments, (list, tuple))
            else [self.arguments]
            if self.arguments != "*"
            else []
        )

        for name, value in bound_args.arguments.items():
            if name in expected_args or self.arguments == "*":
                resolved = self._resolve_attr_path(value, self.path)
                if self.normalizer is not None:
                    with suppress(Exception):
                        # Custom normalizer, in case of a class or a value, that cannot be directly converted to string.
                        resolved = self.normalizer(resolved)
                result[name] = resolved

        return result


class DrfSerializerKeyField(CacheKeyField):
    """
    Cache-key field that fingerprints a DRF serializer's shape.

    Walks declared fields (including nested and list serializers) and
    records their classes and modules. Adding or removing a field
    invalidates the cache automatically. The payload is always hashed.

    Example:
        ::

            class ListUsersKey(KeyConstructor):
                shape = DrfSerializerKeyField(UserSerializer)
    """

    def __init__(self, serializer_class):
        # Serializer payloads can be large, so always hash the result.
        super().__init__(partition=False, hash_value=True, sort_lists=True)
        self.serializer_class = serializer_class

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:  # noqa: ARG002
        if not self.serializer_class:
            return {}
        serializer_structure = self._get_serializer_structure(
            self.serializer_class
        )
        return {"serializer_structure": serializer_structure}

    def _get_serializer_structure(self, serializer_class):
        try:
            temp_instance = serializer_class()
        except Exception as exc:
            msg = f"Failed to initialize serializer class: {serializer_class}"
            raise ValueError(msg) from exc

        structure = {
            "name": str(serializer_class.__name__),
            "module": str(serializer_class.__module__),
            "fields": {},
        }

        fields = temp_instance.get_fields()

        for field_name, field_instance in sorted(fields.items()):
            field_info = self._get_field_info(field_instance)
            structure["fields"][field_name] = field_info

        return structure

    def _get_field_info(self, field_instance):
        field_info = {
            "type": field_instance.__class__.__name__,
            "module": field_instance.__class__.__module__,
            "properties": {},
        }
        if isinstance(field_instance, serializers.Serializer):
            field_info["nested_serializer"] = self._get_serializer_structure(
                field_instance.__class__
            )
        elif isinstance(field_instance, serializers.ListSerializer) and (
            hasattr(field_instance, "child")
            and isinstance(field_instance.child, serializers.Serializer)
        ):
            field_info["list_child_serializer"] = (
                self._get_serializer_structure(field_instance.child.__class__)
            )

        return field_info


class DjangoModelKeyField(CacheKeyField):
    """
    Cache-key field that fingerprints a Django model's schema.

    Records the model's name, module, and concrete fields. Migrations
    that change the schema invalidate the cache automatically. The
    payload is always hashed.

    Example:
        ::

            class UserKey(KeyConstructor):
                shape = DjangoModelKeyField(User)
    """

    def __init__(self, model_class):
        super().__init__(partition=False, hash_value=True, sort_lists=True)
        self.model_class = model_class

    def get_key_payload(self, func, args, kwargs) -> dict[str, Any]:  # noqa: ARG002
        if not self.model_class:
            return {}

        structure = self._get_model_structure()
        return {"model_structure": structure}

    def _get_model_structure(self):
        if not inspect.isclass(self.model_class):
            msg = f"Invalid model class: {self.model_class}"
            raise ValueError(msg)

        fields_info: dict[str, dict[str, str]] = {}
        for f in self.model_class._meta.get_fields():
            if isinstance(f, models.Field):
                fields_info[f.name] = {
                    "type": f.__class__.__name__,
                }

        return {
            "name": str(self.model_class.__name__),
            "module": str(self.model_class.__module__),
            "fields": {k: fields_info[k] for k in sorted(fields_info.keys())},
        }
