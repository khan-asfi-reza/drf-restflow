from asgiref.sync import sync_to_async
from rest_framework import throttling as drf_throttle


def throttler_allow_request(throttle, request, view):
    """Async-compat allow_request dispatcher. Prefers aallow_request when present."""
    aallow = getattr(throttle, "aallow_request", None)
    if aallow is not None:
        return aallow(request, view)
    return throttle.allow_request(request, view)

class BaseThrottle(drf_throttle.BaseThrottle):
    """
    All throttle classes should extend BaseThrottle.
    Adds an async aallow_request hook that defaults to running the sync allow_request in a thread.
    """

    async def aallow_request(self, request, view):
        """Returns True if the request should be allowed, False otherwise."""
        return await sync_to_async(
            self.allow_request, thread_sensitive=True
        )(request, view)


class SimpleRateThrottle(BaseThrottle, drf_throttle.SimpleRateThrottle):
    """
    A simple cache implementation of a rate limit throttle.
    Adds an async surface that uses Django's async cache so rate limiting does not block the event loop.
    """

    async def aallow_request(self, request, view):
        """Returns True if the request rate is below the configured limit, False otherwise."""
        if self.rate is None:
            return True
        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = await self.cache.aget(self.key, [])
        self.now = self.timer()

        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return await self.athrottle_success()

    async def athrottle_success(self):
        """Records the successful request in the cache and returns True."""
        self.history.insert(0, self.now)
        await self.cache.aset(self.key, self.history, self.duration)
        return True


class AnonRateThrottle(SimpleRateThrottle, drf_throttle.AnonRateThrottle):
    """
    Limits the rate of API calls that may be made by an anonymous user.
    Inherits SimpleRateThrottle's async cache path.
    """


class UserRateThrottle(SimpleRateThrottle, drf_throttle.UserRateThrottle):
    """
    Limits the rate of API calls that may be made by a given user.
    Inherits SimpleRateThrottle's async cache path.
    """


class ScopedRateThrottle(SimpleRateThrottle, drf_throttle.ScopedRateThrottle):
    """
    Limits the rate of API calls by different amounts for various parts of the API.
    Inherits SimpleRateThrottle's async cache path.
    """
