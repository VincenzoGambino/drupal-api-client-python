"""Serializer protocol and default implementation for drupal-api-client."""

from typing import Any, Protocol


class Serializer(Protocol):
    """Protocol for serializer implementations.

    Both methods are required.  If your implementation only needs one
    direction, implement the other as a no-op that returns the input
    unchanged.
    """

    def deserialize(
        self, body: dict[str, Any], options: dict[str, Any] | None = None
    ) -> Any: ...

    def serialize(self, data: Any) -> Any: ...


class PassthroughSerializer:
    """Returns input as-is. Real JSON:API parsing belongs in JsonApiClient."""

    def deserialize(
        self, body: dict[str, Any], options: dict[str, Any] | None = None
    ) -> Any:
        return body

    def serialize(self, data: Any) -> Any:
        return data
