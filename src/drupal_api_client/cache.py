"""Cache protocol and default implementation for drupal-api-client."""

from typing import Any, Protocol


class Cache(Protocol):
    """Protocol for cache implementations.

    Implementers can use any backing store (dict, Redis, shelve, etc.)
    as long as they provide ``get``, ``set``, and ``delete`` with these
    signatures.
    """

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...


class InMemoryCache:
    """Simple dict-backed cache. Suitable for testing and single-process use."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        """Remove a key. No-op if the key is not present."""
        self._store.pop(key, None)
