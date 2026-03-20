"""
Simple in-memory caching utilities.
"""

import functools
import time
from threading import Lock


class TTLCache:
    def __init__(self):
        self._cache = {}
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
        return None

    def set(self, key, value, ttl_seconds=60):
        with self._lock:
            self._cache[key] = (value, time.time() + ttl_seconds)

    def clear(self):
        with self._lock:
            self._cache.clear()


# Global singleton cache instance
cache = TTLCache()


from typing import Any, Callable, TypeVar, ParamSpec


F = TypeVar("F", bound=Callable[..., Any])
P = ParamSpec("P")


def cacheable(ttl_seconds: int = 300) -> Callable[[F], F]:
    """
    Decorator to cache function results in memory for a given TTL.

    Designed for pure functions that return JSON-serializable data.
    """

    def decorator(func: F) -> F:
        cache: dict[tuple[Any, ...], tuple[float, Any]] = {}

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs):
            key: tuple[Any, ...]
            try:
                key = (args, frozenset(kwargs.items()))
            except TypeError:
                # Unhashable arguments; skip caching
                return func(*args, **kwargs)

            now = time.time()
            if key in cache:
                ts, value = cache[key]
                if now - ts <= ttl_seconds:
                    return value

            value = func(*args, **kwargs)
            cache[key] = (now, value)
            return value

        return wrapper  # type: ignore[return-value]

    return decorator

