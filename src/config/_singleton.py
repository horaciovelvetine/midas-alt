"""Singleton metaclass used by MidasSettings and MidasConfigData.

A class using ``SingletonMeta`` returns the same instance every time it is
called. Tests can call ``cls._reset_for_tests()`` (provided by this metaclass)
to clear the cached instance between cases.
"""

from __future__ import annotations

from threading import RLock
from typing import Any


class SingletonMeta(type):
    """Metaclass that caches one instance per concrete class."""

    _instances: dict[type, Any] = {}
    _lock = RLock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Return the cached instance, creating it on first call."""
        with SingletonMeta._lock:
            instance = SingletonMeta._instances.get(cls)
            if instance is None:
                instance = super().__call__(*args, **kwargs)
                SingletonMeta._instances[cls] = instance
            return instance

    def _reset_for_tests(cls) -> None:
        """Drop the cached singleton (test helper)."""
        with SingletonMeta._lock:
            SingletonMeta._instances.pop(cls, None)
