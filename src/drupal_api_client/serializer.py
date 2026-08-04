"""Serializer protocol and implementations for drupal-api-client.

Provides:

- :class:`Serializer` — the structural protocol the client depends on.
- :class:`PassthroughSerializer` — returns the raw JSON:API body unchanged.
- :class:`DefaultSerializer` — a schema-less JSON:API flattener that mirrors
  the JS client's ``DefaultSerializer`` (built on ``jsona``): resources are
  denormalized into flat objects with ``type``/``id`` and hoisted attributes,
  relationships are inlined from ``included``, and the document's top-level
  ``meta``/``links`` are exposed via ``get_meta()``/``get_links()``.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
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


class _MetaLinksMixin:
    """Adds non-data ``get_meta()``/``get_links()`` accessors.

    The values are stored as instance attributes (``_meta``/``_links``), not
    as data — so they never appear in ``keys()``/iteration, mirroring the JS
    serializer's non-enumerable ``getMeta``/``getLinks``.
    """

    _meta: Any = None
    _links: Any = None

    def get_meta(self) -> Any:
        """Return the document's top-level ``meta`` (or ``None``)."""
        return self._meta

    def get_links(self) -> Any:
        """Return the document's top-level ``links`` (or ``None``)."""
        return self._links


class Resource(_MetaLinksMixin, dict):
    """A flattened JSON:API resource.

    A plain ``dict`` of ``type``, ``id`` and hoisted attributes (plus inlined
    relationships), with :meth:`get_meta`/:meth:`get_links` accessors that are
    not part of the data.
    """


class ResourceCollection(_MetaLinksMixin, list):
    """A flattened JSON:API collection: a ``list`` of :class:`Resource`,
    with document-level :meth:`get_meta`/:meth:`get_links` accessors."""


class DefaultSerializer:
    """Schema-less JSON:API deserializer (parity with the JS DefaultSerializer).

    Falls back to passthrough for anything that is not a JSON:API document
    (``None``, non-objects, or objects without a ``data`` member).
    """

    def deserialize(
        self, body: Any, options: dict[str, Any] | None = None
    ) -> Any:
        # Accept a raw JSON string body (the JS serializer does too).
        if isinstance(body, (str, bytes, bytearray)):
            try:
                body = json.loads(body)
            except (ValueError, TypeError):
                return body

        # Passthrough for non-JSON:API input.
        if not isinstance(body, dict) or "data" not in body:
            return body

        data = body["data"]
        meta = body.get("meta")
        links = body.get("links")

        # Build a registry of every resource (top-level data + included),
        # keyed by (type, id). Two passes: create flattened shells, then
        # resolve relationships against the registry so shared/circular
        # references resolve to the same object without infinite recursion.
        registry: dict[tuple[Any, Any], tuple[Resource, dict[str, Any]]] = {}
        raw_resources: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_resources.extend(r for r in data if isinstance(r, dict))
        elif isinstance(data, dict):
            raw_resources.append(data)
        raw_resources.extend(
            r for r in (body.get("included") or []) if isinstance(r, dict)
        )

        for raw in raw_resources:
            shell = Resource()
            shell["type"] = raw.get("type")
            shell["id"] = raw.get("id")
            for attr_name, attr_value in (raw.get("attributes") or {}).items():
                shell[attr_name] = attr_value
            registry[(raw.get("type"), raw.get("id"))] = (shell, raw)

        for shell, raw in registry.values():
            for rel_name, rel in (raw.get("relationships") or {}).items():
                if not isinstance(rel, dict) or "data" not in rel:
                    continue
                shell[rel_name] = self._resolve_linkage(rel["data"], registry)

        # Assemble the top-level return value.
        if isinstance(data, list):
            result: Any = ResourceCollection(
                registry[(r.get("type"), r.get("id"))][0]
                for r in data
                if isinstance(r, dict)
            )
        elif isinstance(data, dict):
            result = registry[(data.get("type"), data.get("id"))][0]
        else:
            # e.g. `data: null` — nothing to flatten.
            return data

        result._meta = meta
        result._links = links
        return result

    @staticmethod
    def _resolve_linkage(
        linkage: Any,
        registry: dict[tuple[Any, Any], tuple[Resource, dict[str, Any]]],
    ) -> Any:
        """Resolve a relationship's ``data`` linkage to flattened resource(s).

        Falls back to the raw ``{"type", "id"}`` identifier when the linked
        resource is not present in ``included``.
        """
        if linkage is None:
            return None
        if isinstance(linkage, list):
            return [
                DefaultSerializer._resolve_one(item, registry) for item in linkage
            ]
        return DefaultSerializer._resolve_one(linkage, registry)

    @staticmethod
    def _resolve_one(
        identifier: Any,
        registry: dict[tuple[Any, Any], tuple[Resource, dict[str, Any]]],
    ) -> Any:
        if not isinstance(identifier, dict):
            return identifier
        key = (identifier.get("type"), identifier.get("id"))
        entry = registry.get(key)
        if entry is not None:
            return entry[0]
        # Not included — keep the resource identifier as-is.
        return {"type": identifier.get("type"), "id": identifier.get("id")}

    def serialize(self, data: Any) -> Any:  # pragma: no cover - not implemented
        raise NotImplementedError(
            "DefaultSerializer does not implement serialize(); "
            "build JSON:API request bodies directly."
        )
