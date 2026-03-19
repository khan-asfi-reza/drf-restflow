import hashlib
from collections.abc import Callable

from restflow.settings import restflow_settings


def hash_string(value: str) -> str:
    """Return the hex digest of value using the configured cache-key hash algorithm."""
    algorithm = restflow_settings.CACHE_SETTINGS.KEY_HASH_ALGORITHM
    # User defined hashing algorithm
    if isinstance(algorithm, Callable):
        return algorithm(value)
    return hashlib.new(algorithm, value.encode("utf-8")).hexdigest()
