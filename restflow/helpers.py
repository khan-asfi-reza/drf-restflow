import inspect
from types import UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    NewType,
    Union,
    get_args,
    get_origin,
)

from asgiref.sync import async_to_sync

Email = NewType("Email", str)
IPAddress = NewType("IPAddress", str)
BlankableString = NewType("BlankableString", str)


RESERVED_SERIALIZER_ATTRS = frozenset(
    {
        "data",
        "errors",
        "validated_data",
        "instance",
        "initial_data",
        "fields",
        "context",
    }
)


def sort_dict(d: dict) -> dict:
    """Return a new dict with the same items as d, ordered by key."""
    return dict(sorted(d.items()))


def getattr_multi_source(obj_set: list[Any], attr_name: str, default=None) -> Any:
    """Return attr_name from the first object in obj_set that defines it. Returns default when none do."""
    if not obj_set:
        obj_set = []

    if not isinstance(obj_set, (list, tuple)):
        obj_set = [obj_set]
    for obj in obj_set:
        if not obj:
            continue
        value = getattr(obj, attr_name, default)
        if value is not default:
            return value
    return default


async def maybe_await(value):
    """Await value when awaitable. Return it as-is otherwise."""
    if inspect.isawaitable(value):
        return await value
    return value


def require_sync(value, async_alternative):
    """Return value when not awaitable, otherwise close the coroutine and raise TypeError pointing at async_alternative."""
    if inspect.isawaitable(value):
        close = getattr(value, "close", None)
        if close is not None:
            close()
        msg = (
            f"async user callable detected, use {async_alternative} "
            f"for async support."
        )
        raise TypeError(msg)
    return value


def run_sync(value):
    """Return value when not awaitable, otherwise drive the coroutine to completion via async_to_sync and return its result."""
    if inspect.isawaitable(value):
        async def _wrapper():
            return await value
        return async_to_sync(_wrapper)()
    return value


def resolve_field_from_type(
    data_type,
    *,
    type_map: dict[type, type],
    field_name: str | None = None,
    list_field_class: type | None = None,
    list_field_hook=None,
    choice_field_class: type | None = None,
    nested_predicate=None,
    nested_factory=None,
    error_message: str | None = None,
    allow_null_on_optional: bool = False,
    **field_kwargs,
):
    """Resolve a Python type annotation to a field instance, dispatching nested, Optional, list, and Literal forms."""
    if nested_predicate and nested_predicate(data_type):
        return nested_factory(data_type, field_kwargs)

    origin = get_origin(data_type)

    if origin is Annotated:
        # Resolves nested annotation.
        # It is hoped that, this will not cause, recursion depth error,
        # as it is not humanly possible to write infite nested annotations.
        return resolve_field_from_type(
            get_args(data_type)[0],
            type_map=type_map,
            field_name=field_name,
            list_field_class=list_field_class,
            list_field_hook=list_field_hook,
            choice_field_class=choice_field_class,
            nested_predicate=nested_predicate,
            nested_factory=nested_factory,
            error_message=error_message,
            allow_null_on_optional=allow_null_on_optional,
            **field_kwargs,
        )

    if origin is Literal:
        # Literal is usually paired with choices Literal["SUCCESS", "FAILURE", "PENDING", ...]
        # which is nothing but limited set of values.
        if choice_field_class is None:
            msg = f"{error_message or 'unsupported type'}, not {data_type}"
            raise AssertionError(msg)
        args = get_args(data_type)
        field_kwargs["choices"] = tuple(zip(args, args, strict=False))
        return choice_field_class(**field_kwargs)

    if origin is Union or origin is UnionType:
        # UnionType or Type | None Cases
        # Modern python (3.10+) uses | operator for unions.
        union_args = get_args(data_type)
        valid_types = [arg for arg in union_args if arg is not type(None)]
        if not valid_types:  # pragma: no cover
            # python collapses Union[None] to NoneType.
            # Don't know why anyone would do Union[None]
            msg = f"{error_message or 'unsupported type'}, not {data_type}"
            raise AssertionError(msg)
        if len(valid_types) > 1:
            msg = (
                f"{error_message or 'unsupported type'}: union with multiple non-None members "
                f"is ambiguous, got {data_type}. Pick a single type or use a custom field."
            )
            raise AssertionError(msg)
        if type(None) not in union_args:  # pragma: no cover
            return resolve_field_from_type(
                valid_types[0],
                type_map=type_map,
                field_name=field_name,
                list_field_class=list_field_class,
                list_field_hook=list_field_hook,
                choice_field_class=choice_field_class,
                nested_predicate=nested_predicate,
                nested_factory=nested_factory,
                error_message=error_message,
                allow_null_on_optional=allow_null_on_optional,
                **field_kwargs,
            )
        if allow_null_on_optional:
            field_kwargs.setdefault("allow_null", True)
            field_kwargs.setdefault("required", False)
        return resolve_field_from_type(
            valid_types[0],
            type_map=type_map,
            field_name=field_name,
            list_field_class=list_field_class,
            list_field_hook=list_field_hook,
            choice_field_class=choice_field_class,
            nested_predicate=nested_predicate,
            nested_factory=nested_factory,
            error_message=error_message,
            allow_null_on_optional=allow_null_on_optional,
            **field_kwargs,
        )

    if origin is list or data_type is list:
        # For array / list type fields
        if list_field_class is None:
            msg = f"{error_message or 'unsupported list type'}, not {data_type}"
            raise AssertionError(msg)
        args = get_args(data_type)
        inner = args[0] if args else str
        if nested_predicate and nested_predicate(inner):
            return nested_factory(inner, {**field_kwargs, "many": True})
        child = resolve_field_from_type(
            inner,
            type_map=type_map,
            list_field_class=list_field_class,
            list_field_hook=list_field_hook,
            choice_field_class=choice_field_class,
            nested_predicate=nested_predicate,
            nested_factory=nested_factory,
            error_message=error_message,
            allow_null_on_optional=allow_null_on_optional,
        )
        field_kwargs["child"] = child
        if list_field_hook is not None:
            list_field_hook(field_kwargs, field_name, inner)
        return list_field_class(**field_kwargs)

    field_class = type_map.get(data_type)
    if not field_class:
        msg = f"{error_message or 'unsupported type'}, not {data_type}"
        raise AssertionError(msg)
    return field_class(**field_kwargs)
