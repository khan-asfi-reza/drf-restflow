from datetime import date, datetime, time
from decimal import Decimal
from json import dumps as json_dumps
from typing import Any
from uuid import UUID


def normalize_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, ValidatedData):
        return dict(obj)
    msg = f"Object of type {type(obj).__name__} is not JSON serializable"
    raise TypeError(msg)


class ValidatedData(dict):
    """A dict subclass returned by Serializer.validated_data that adds attribute access and JSON helpers.

    Reads:
        vd.name, vd["name"], vd.get("name"), **vd, dict(vd) all return the same value.

    Writes:
        vd.name = value and vd["name"] = value are equivalent and write through to the underlying dict.

    Restflow adds attribute access plus a configurable to_json so payloads with Decimal, datetime, date, time, and UUID render without a custom encoder.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __reduce__(self):
        return (ValidatedData, (dict(self),))

    def __repr__(self) -> str:
        return f"ValidatedData({dict.__repr__(self)})"

    def __json__(self) -> dict:
        """Return a plain dict view for codec interop with libraries that look up __json__."""
        return dict(self)

    def to_json(self, **opts: Any) -> str:
        """Render this validated payload as a JSON string. All keyword arguments are forwarded to json.dumps. A user default is composed with the restflow fallback for Decimal, date, datetime, time, and UUID."""
        user_default = opts.pop("default", None)
        if user_default is None:
            opts["default"] = normalize_default
        else:
            def _chained(obj: Any) -> Any:
                try:
                    return user_default(obj)
                except TypeError:
                    return normalize_default(obj)

            opts["default"] = _chained
        return json_dumps(self, **opts)


def transform_validated_data(value: Any, _seen: set[int] | None = None) -> Any:
    """Recursively convert dicts to ValidatedData and walk lists, leaving everything else untouched."""
    if isinstance(value, ValidatedData):
        return value
    if isinstance(value, dict):
        if _seen is None:
            _seen = set()
        ident = id(value)
        if ident in _seen:
            return value
        _seen.add(ident)
        return ValidatedData({k: transform_validated_data(v, _seen) for k, v in value.items()})
    if isinstance(value, list):
        if _seen is None:
            _seen = set()
        ident = id(value)
        if ident in _seen:
            return value
        _seen.add(ident)
        return [transform_validated_data(v, _seen) for v in value]
    return value
