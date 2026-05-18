import enum


class CacheStatus(str, enum.Enum):
    """
    How a cached call resolved.

    Carried in the response metadata so callers and monitoring can tell
    hits from misses.
    """

    HIT = "HIT"
    MISS = "MISS"
    STALE = "STALE"
    BYPASS = "BYPASS"
    REFRESH = "REFRESH"


CACHED_DATA_VALUE_KEY = "value"
CACHED_DATA_METADATA_KEY = "metadata"
METADATA_CACHED_AT_KEY = "cached_at"
METADATA_RESET_AT_KEY = "cache_reset_at"
METADATA_CACHE_STATUS = "cache_status"

#: Sentinel returned when a cache key has no entry. Use `is CACHE_MISSING`
#: to tell a real cache miss apart from a cached `None` value.
CACHE_MISSING = object()

# Used inside cache key payloads to distinguish "attribute missing" from
# "attribute resolved to None".
MISSING_VALUE = "__restflow:missing__"


