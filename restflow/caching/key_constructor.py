import copy
import inspect
from collections.abc import Callable
from functools import cached_property
from typing import Any, ParamSpec, TypeVar, cast

from restflow.caching.hashing import hash_string
from restflow.caching.key_fields import ArgsKeyField, CacheKeyField
from restflow.helpers import getattr_multi_source, sort_dict
from restflow.settings import restflow_settings

P = ParamSpec("P")
T = TypeVar("T")


class _Default:
    pass


Default = _Default()


_TYPE_FRIENDLY: dict[type, str] = {
    int: "an integer",
    str: "a string",
    bool: "a boolean",
}


def ensure_type(name: str, value: Any, expected: type) -> None:
    # Ensure if the type of the value is the expected one,
    # Raise TypeError with proper message.
    # Loud error since it is config issue.
    if not isinstance(value, expected):
        msg = f"{name} must be {_TYPE_FRIENDLY[expected]}"
        raise TypeError(msg)


def get_meta_config(
    options: list[Any],
    key: str,
    default=None,
    skip_settings: bool = False,
):
    """Look up a Meta option, with an optional fallback to RESTFLOW_SETTINGS."""
    sentinel = default if skip_settings else Default
    val = getattr_multi_source(options, key, sentinel)

    if val is not Default:
        return val

    return getattr(restflow_settings.CACHE_SETTINGS, key.upper(), default)


class KeyConstructorConfig:
    """
    Resolved Meta options for a KeyConstructor subclass.

    Holds the values pulled from a constructor's nested Meta class.
    Values that fall back to Django settings are resolved on first
    access so a subclass can be defined before Django is configured.
    """

    def __init__(self, options: list[Any]):
        self._options = options

        self.version = get_meta_config(
            options, "version", default=1, skip_settings=True
        )
        self.namespace = get_meta_config(
            options, "namespace", "", skip_settings=True
        )
        self.key_identifier = get_meta_config(
            options, "key_identifier", default="", skip_settings=True
        )

        self.version = (
            int(self.version)
            if isinstance(self.version, str) and self.version.isdigit()
            else self.version
        )

        ensure_type("version", self.version, int)
        ensure_type("namespace", self.namespace, str)
        ensure_type("key_identifier", self.key_identifier, str)

    @cached_property
    def max_key_suffix_length(self) -> int:
        val = get_meta_config(self._options, "max_key_suffix_length", 250)
        ensure_type("max_key_suffix_length", val, int)
        return val

    @cached_property
    def hash_suffix_on_overflow(self) -> bool:
        val = get_meta_config(self._options, "hash_suffix_on_overflow", False)
        ensure_type("hash_suffix_on_overflow", val, bool)
        return val


class KeyConstructorMetaClass(type):
    """Metaclass that collects declared CacheKeyField attributes and the nested Meta class onto the new class."""

    @classmethod
    def _get_declared_key_constructors(cls, bases, attrs):
        fields = [
            (key_constructor, attrs.pop(key_constructor))
            for key_constructor, obj in list(attrs.items())
            if isinstance(obj, CacheKeyField)
        ]

        known = set(attrs)

        def visit(name):
            known.add(name)
            return name

        base_fields = [
            (visit(name), f)
            for base in bases
            if hasattr(base, "_declared_key_constructors")
            for name, f in base._declared_key_constructors.items()
            if name not in known
        ]

        return dict(base_fields + fields)

    def __new__(cls, name, bases, attrs):
        _options = [attrs.get("Meta")] + [
            getattr(base, "_meta", None) for base in bases
        ]
        meta_config = KeyConstructorConfig(options=_options)
        attrs.pop("Meta", None)
        attrs["_meta"] = meta_config
        attrs["_declared_key_constructors"] = (
            cls._get_declared_key_constructors(bases, attrs)
        )
        return super().__new__(cls, name, bases, attrs)


class KeyConstructor(metaclass=KeyConstructorMetaClass):
    """
    Declarative cache-key generator.

    Subclass and declare CacheKeyField attributes to build a stable
    cache key for a function.

    Example:
        ::

            class UserKey(KeyConstructor):
                user = ArgsKeyField("user_id", partition=True)
                version = ConstantKeyField("v", "1")

                class Meta:
                    namespace = "myapp"
                    version = 1
    """

    def get_version(self) -> int:
        """Return the version declared on Meta, bumping it invalidates all keys for this constructor."""
        return int(self._get_from_meta("version", 1))

    def get_fields(self):
        """Return a fresh dict of the declared CacheKeyField attributes."""
        return copy.deepcopy(getattr(self, "_declared_key_constructors", {}))

    def _get_from_meta(self, attr, default: Any = None):
        return getattr(getattr(self, "_meta", None), attr, default)

    @cached_property
    def fields(self):
        """Return the declared CacheKeyField attributes for this instance."""
        return self.get_fields()

    @cached_property
    def has_only_partition_fields(self) -> bool:
        """Return True when every declared field is a partition field."""
        return all(field.partition for field in self.fields.values())

    @cached_property
    def namespace(self):
        """Return the namespace prefix written in front of every generated key."""
        namespace = self._get_from_meta("namespace")
        return f"{namespace}::" if namespace else ""

    @cached_property
    def key_identifier(self):
        """Return the per-function identifier override declared on Meta."""
        return self._get_from_meta("key_identifier", "")

    def build_partition(self, func, args, kwargs):
        """Build the partition portion of the cache key from fields declared with partition=True."""
        if args is None and kwargs is None:
            return ""

        scope_data = {}
        scopes_in_order = [
            (field, item)
            for field, item in self.fields.items()
            if item.partition
        ]

        for field_name, field in scopes_in_order:
            scope = field.get_cache_key_part(func, args, kwargs)
            scope_data[field_name] = scope

        scope_data = sort_dict(scope_data)

        string = ""
        for val in scope_data.values():
            string += f"{val}::"

        while string.endswith("::"):
            string = string.removesuffix("::")

        return string

    def build_key_prefix(self, func: Callable[P, T], args, kwargs):
        """Build the cache key prefix from namespace, function identifier, and partition."""
        scope = self.build_partition(func, args, kwargs)
        prefix = (
            self.key_identifier
            if self.key_identifier
            else self.get_function_identifier(func)
        )
        namespace = self.namespace
        cache_key = f"{namespace}{prefix}::"
        if scope:
            cache_key += f"{scope}::"
        return cache_key

    def build_key_suffix(self, func, args, kwargs):
        """Build the cache key suffix from non-partition fields, hashing it on overflow when configured."""
        max_key_suffix_length = self._get_from_meta(
            "max_key_suffix_length", 250
        )
        hash_suffix_on_overflow = self._get_from_meta(
            "hash_suffix_on_overflow", False
        )

        suffix = ""

        fields_in_order = [
            (field, item)
            for field, item in self.fields.items()
            if not item.partition
        ]

        field_values = {}

        for field_name, field in fields_in_order:
            field_data = field.get_cache_key_part(func, args, kwargs)
            field_values[field_name] = field_data

        field_values = sort_dict(field_values)

        for value in field_values.values():
            suffix += f"{value}::"

        while suffix.endswith("::"):
            suffix = suffix.removesuffix("::")

        should_hash = (
            len(suffix) > max_key_suffix_length and hash_suffix_on_overflow
        )
        return hash_string(suffix) if should_hash else suffix

    def generate_key(self, func: Callable[P, T], args, kwargs) -> str:
        """Build and return the full cache key for the given call."""
        prefix = self.build_key_prefix(func, args, kwargs)
        suffix = self.build_key_suffix(func, args, kwargs)
        cache_key = f"{prefix}{suffix}"
        return cache_key.removesuffix("::")

    @staticmethod
    def get_function_identifier(func: Callable[P, T]):
        """Return the function's full dotted path, including class name for bound methods."""
        owner = getattr(func, "__self__", None)
        if owner is not None:
            cls = owner if inspect.isclass(owner) else owner.__class__
            return f"{cls.__module__}.{cls.__name__}.{func.__name__}"
        module = getattr(func, "__module__", "")
        qualname = getattr(func, "__qualname__", "")
        if "." in qualname:
            return f"{module}.{qualname}"

        return f"{module}.{func.__name__}"


class InlineKeyConstructor:
    """
    Factory that builds a KeyConstructor subclass from a plain dict of fields.

    Useful for a one-off constructor on a single cache_result call
    without writing out a full subclass.

    Example:
        ::

            UserKey = InlineKeyConstructor(
                fields={"user": ArgsKeyField("user_id", partition=True)},
                namespace="myapp",
            )

            @cache_result(UserKey, ttl=60)
            def get_user(user_id: int): ...
    """

    _cache: dict[str, type[KeyConstructor]] = {}

    def __new__(
        cls,
        fields: dict[str, CacheKeyField],
        version="1",
        max_key_suffix_length=250,
        hash_suffix_on_overflow=False,
        namespace="",
        key_identifier="",
    ):
        sig = (
            tuple((name, id(f)) for name, f in sorted(fields.items())),
            version,
            namespace,
            key_identifier,
            hash_suffix_on_overflow,
            max_key_suffix_length,
        )

        cache_key = f"Inline_{hash(sig)}"

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        attrs = {
            **fields,
            "Meta": type(
                "Meta",
                (),
                {
                    "version": version,
                    "max_key_suffix_length": max_key_suffix_length,
                    "hash_suffix_on_overflow": hash_suffix_on_overflow,
                    "namespace": namespace,
                    "key_identifier": key_identifier,
                },
            ),
        }
        ctor_cls = cast(
            type[KeyConstructor],
            type(cache_key, (KeyConstructor,), attrs),
        )
        cls._cache[cache_key] = ctor_cls
        return ctor_cls


class DefaultKeyConstructor(KeyConstructor):
    """
    Built-in key constructor that captures every positional and keyword argument.

    Used by cache_result when no key_constructor is supplied.
    """

    arguments = ArgsKeyField("*")
