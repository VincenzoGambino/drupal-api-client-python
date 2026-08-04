"""JsonApiClient — JSON:API integration for Drupal."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

import httpx

from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.client import ApiClient
from drupal_api_client.decoupled_router import (
    DecoupledRouterClient,
    ResolvedPath,
    UnresolvedPath,
)
from drupal_api_client.errors import ResourceNotFoundError
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawJsonApiResponse:
    """Raw response when caller passes ``raw_response=True``."""

    response: httpx.Response
    json: dict[str, Any]


def _resource_type_from_router(resolved: ResolvedPath) -> str:
    """Determine the JSON:API resource type for a resolved router response.

    Prefers the router's ``jsonapi.resourceName``, which is what the JS
    client reads.  That field reflects any resource-type rewriting done by
    ``jsonapi_extras``; the entity's ``type``/``bundle`` do not, so building
    the type from them requests the un-rewritten path and 404s on sites
    where a resource has been renamed.

    Falls back to ``{type}--{bundle}`` when the router omits ``resourceName``
    (older ``decoupled_router`` releases, or a hand-rolled router response).
    """
    resource_name = (resolved.jsonapi or {}).get("resourceName")
    if resource_name:
        return str(resource_name)
    return f"{resolved.entity['type']}--{resolved.entity['bundle']}"


class JsonApiClient(ApiClient):
    """Client for Drupal's JSON:API.

    Extends :class:`ApiClient` to provide JSON:API read operations
    (:meth:`get_collection`, :meth:`get_resource`, :meth:`get_view`,
    :meth:`get_resource_by_path`) plus URL/cache-key helpers and
    response processing foundations.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_prefix: str | None = None,
        authentication: Authentication | None = None,
        cache: Cache | None = None,
        serializer: Serializer | None = None,
        default_locale: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float | httpx.Timeout = 30.0,
        index_lookup: bool = False,
        decoupled_router_api_prefix: str | None = None,
    ) -> None:
        super().__init__(
            base_url,
            api_prefix=api_prefix,
            authentication=authentication,
            cache=cache,
            serializer=serializer,
            default_locale=default_locale,
            http_client=http_client,
            timeout=timeout,
        )
        self.api_prefix = api_prefix or "jsonapi"
        self.index_lookup: bool = index_lookup
        self.decoupled_router_api_prefix: str | None = decoupled_router_api_prefix
        # Keyed by locale segment (None for no locale) - the JSON:API
        # index can differ per locale, so each locale gets its own
        # fetch/cache entry. See _fetch_index().
        self._index_cache: dict[str | None, dict[str, Any]] = {}

        self.router = DecoupledRouterClient(
            base_url,
            api_prefix=decoupled_router_api_prefix,
            authentication=authentication,
            cache=cache,
            serializer=serializer,
            default_locale=default_locale,
            http_client=http_client,
            timeout=timeout,
        )

    # -- context manager / lifecycle ----------------------------------------

    def __enter__(self) -> JsonApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close both the owned HTTP client and the router's client."""
        super().close()
        self.router.close()

    # -- public helpers -----------------------------------------------------

    @staticmethod
    def _get_entity_type_and_bundle(resource_type: str) -> tuple[str, str]:
        """Parse ``'node--article'`` into ``('node', 'article')``.

        Raises :class:`ValueError` if the format is invalid.
        """
        parts = resource_type.split("--")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Invalid resource type format: {resource_type!r}. "
                "Expected 'entity_type--bundle' (e.g. 'node--article')."
            )
        return parts[0], parts[1]

    def create_url(
        self,
        *,
        entity_type_id: str,
        bundle_id: str,
        resource_id: str | None = None,
        locale_segment: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
    ) -> str:
        """Build a JSON:API endpoint URL.

        Shape::

            {base_url}{locale/}{api_prefix}/{entity_type}/{bundle}[/{resource_id}][?{qs}]
        """
        if query_string is not None and hasattr(query_string, "get_query_string"):
            query_string = query_string.get_query_string()

        # index_lookup: use cached endpoint URL when available, for this
        # locale specifically - the index can differ per locale.
        if self.index_lookup and locale_segment in self._index_cache:
            resource_type = f"{entity_type_id}--{bundle_id}"
            cached_link = self._index_cache[locale_segment].get(resource_type)
            if cached_link is not None:
                href = cached_link["href"] if isinstance(cached_link, dict) else cached_link
                url = href
                if resource_id:
                    url = f"{url}/{resource_id}"
                if query_string:
                    url = f"{url}?{query_string}"
                return url

        api_prefix = self.api_prefix or "jsonapi"
        segments = [api_prefix, entity_type_id, bundle_id]
        if locale_segment:
            segments = [locale_segment, *segments]
        if resource_id:
            segments.append(resource_id)
        path = "/".join(segments)
        url = urljoin(self.base_url, path)

        if query_string:
            url = f"{url}?{query_string}"
        return url

    @staticmethod
    def create_cache_key(
        *,
        entity_type_id: str,
        bundle_id: str,
        resource_id: str | None = None,
        locale_segment: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        cache_key: str | None = None,
    ) -> str:
        """Generate a cache key for a JSON:API request.

        Format: ``{locale--}entity_type--bundle[--resource_id][--sha256(qs)]``
        """
        if cache_key is not None:
            return cache_key

        if query_string is not None and hasattr(query_string, "get_query_string"):
            query_string = query_string.get_query_string()

        parts: list[str] = []
        if locale_segment:
            parts.append(locale_segment)
        parts.append(entity_type_id)
        parts.append(bundle_id)
        if resource_id:
            parts.append(resource_id)
        if query_string:
            hash_hex = hashlib.sha256(query_string.encode()).hexdigest()
            parts.append(hash_hex)
        return "--".join(parts)

    def _process_api_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse response body, applying configured serializer if present.

        Returns the parsed JSON dict (or whatever the serializer returns).
        """
        logger.debug("Processing API response with status %d", response.status_code)

        if response.status_code == 204:
            return {}

        json_data: dict[str, Any] = response.json()

        if self.serializer is not None:
            return self.serializer.deserialize(json_data)
        return json_data

    # -- read operations ----------------------------------------------------

    def _execute_read(
        self,
        *,
        url: str,
        cache_key: str,
        raw_response: bool,
        disable_cache: bool,
        disable_authentication: bool,
        raise_for_status: bool,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Shared read flow: cache check → fetch → process → cache write → return."""
        # 1. Cache read (skip if raw_response or disable_cache)
        if not raw_response and not disable_cache:
            cached = self.get_cached_response(cache_key)
            if cached is not None:
                return cached

        # 2. Fetch
        logger.debug("Fetching %s", url)
        response = self.fetch(url, disable_authentication=disable_authentication)

        # 3. Raise on error (opt-in)
        if raise_for_status:
            response.raise_for_status()

        # 4. Parse
        parsed = self._process_api_response(response)

        # 5. Cache write (skip if raw_response, disable_cache, or error status)
        if (
            not raw_response
            and not disable_cache
            and self.cache is not None
            and response.status_code < 400
        ):
            self.cache.set(cache_key, parsed)

        # 6. Return
        if raw_response:
            return RawJsonApiResponse(response=response, json=parsed)
        return parsed

    def get_collection(
        self,
        resource_type: str,
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a collection of resources of a given type."""
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale

        resolved_cache_key = self.create_cache_key(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            locale_segment=locale_segment,
            query_string=query_string,
            cache_key=cache_key,
        )

        if self.index_lookup:
            self._fetch_index(locale_segment=locale_segment)

        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )

        return self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    def get_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a single resource by type and UUID."""
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale

        resolved_cache_key = self.create_cache_key(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
            query_string=query_string,
            cache_key=cache_key,
        )

        if self.index_lookup:
            self._fetch_index(locale_segment=locale_segment)

        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )

        return self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    def get_view(
        self,
        view_id: str,
        display_id: str,
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a view display via JSON:API Views.

        Requires the ``jsonapi_views`` module on your Drupal site.

        .. note::

           ``index_lookup`` is ignored for views — views are not exposed
           in the JSON:API index.
        """
        locale_segment = locale or self.default_locale

        resolved_cache_key = self._create_view_cache_key(
            view_id=view_id,
            display_id=display_id,
            locale_segment=locale_segment,
            query_string=query_string,
            cache_key=cache_key,
        )

        url = self._create_view_url(
            view_id=view_id,
            display_id=display_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )

        return self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    def get_resource_by_path(
        self,
        path: str,
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Resolve a path alias then fetch the underlying resource.

        Uses :attr:`router` (``DecoupledRouterClient``) to translate
        *path* into entity info, then dispatches to :meth:`get_resource`.

        Raises :class:`ResourceNotFoundError` if the path cannot be
        resolved. When *raise_for_status* is ``True``, a router response
        that fails for a reason *other* than "not resolved" (e.g. a 5xx
        from a broken router endpoint) raises ``httpx.HTTPStatusError``
        instead of letting a possibly-non-JSON error body crash
        response.json() with an opaque ``JSONDecodeError``.
        """
        # 1. Resolve path → entity info via the router. Forward
        # raise_for_status so infra-level router failures (5xx, bad
        # gateway HTML bodies, etc.) surface as a clean
        # httpx.HTTPStatusError - but Decoupled Router's normal "not
        # resolved" signal is a 404 with a valid JSON body, so that case
        # is caught below and normalized to ResourceNotFoundError same
        # as when raise_for_status is False.
        try:
            router_response = self.router.translate_path(
                path,
                locale=locale,
                disable_authentication=disable_authentication,
                disable_cache=disable_cache,
                raise_for_status=raise_for_status,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                try:
                    message = exc.response.json().get("message")
                except ValueError:
                    message = None
                raise ResourceNotFoundError(
                    f"Path {path!r} could not be resolved: {message}"
                ) from exc
            raise

        if not isinstance(router_response, ResolvedPath):
            message = (
                router_response.message
                if isinstance(router_response, UnresolvedPath)
                else None
            )
            raise ResourceNotFoundError(
                f"Path {path!r} could not be resolved: {message}"
            )

        # 2. Extract resource type + UUID from the resolved entity
        uuid = router_response.entity["uuid"]
        resource_type = _resource_type_from_router(router_response)

        # 3. Dispatch to get_resource.
        # Note: the cache is keyed on the post-resolution get_resource
        # parameters (entity_type, bundle, uuid, query_string), so a
        # query_string passed here produces a different cache entry from
        # the same path with a different query string.
        return self.get_resource(
            resource_type,
            uuid,
            locale=locale,
            query_string=query_string,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            cache_key=cache_key,
            raise_for_status=raise_for_status,
        )

    # -- index lookup -------------------------------------------------------

    def _index_cache_key(self, locale_segment: str | None = None) -> str:
        """Cache key for the JSON:API index document.

        Matches the JS client exactly: ``{locale/}{api_prefix}`` — the same
        string JS uses both as the index cache key and as the URL path, so a
        cache shared with a JS client hits the same entry.
        """
        api_prefix = self.api_prefix or "jsonapi"
        return f"{locale_segment}/{api_prefix}" if locale_segment else api_prefix

    def _fetch_index(self, locale_segment: str | None = None) -> None:
        """Fetch the JSON:API index document for *locale_segment* and
        populate :attr:`_index_cache` for that locale.

        The index can differ per locale (different bundles/paths may be
        exposed per language), so each locale is fetched and cached
        independently - mirrors the JS implementation, which includes
        the locale segment in both the index URL and its cache key.

        When a cache is injected, the index document is read from and
        written to it under :meth:`_index_cache_key`, matching JS. That
        makes the index invalidatable and reusable across processes.
        :attr:`_index_cache` remains an in-instance memo so that a client
        with *no* injected cache still fetches the index only once (JS
        refetches it on every URL build in that situation).

        Idempotent per locale: returns immediately if that locale is
        already memoised.  Failure (401, 500, etc.) raises
        ``httpx.HTTPStatusError``.
        """
        if locale_segment in self._index_cache:
            return

        cache_key = self._index_cache_key(locale_segment)

        cached_index = self.get_cached_response(cache_key)
        if cached_index is not None:
            self._index_cache[locale_segment] = cached_index.get("links", {})
            return

        index_url = urljoin(self.base_url, cache_key)
        logger.debug("Fetching JSON:API index at %s", index_url)
        response = self.fetch(index_url)
        response.raise_for_status()
        body = response.json()
        if self.cache is not None and response.status_code < 400:
            self.cache.set(cache_key, body)
        self._index_cache[locale_segment] = body.get("links", {})

    # -- view helpers (private) ---------------------------------------------

    def _create_view_url(
        self,
        *,
        view_id: str,
        display_id: str,
        locale_segment: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
    ) -> str:
        """Build a JSON:API Views endpoint URL.

        Shape::

            {base_url}{locale/}{api_prefix}/views/{view_id}/{display_id}[?{qs}]
        """
        if query_string is not None and hasattr(query_string, "get_query_string"):
            query_string = query_string.get_query_string()

        api_prefix = self.api_prefix or "jsonapi"
        segments = [api_prefix, "views", view_id, display_id]
        if locale_segment:
            segments = [locale_segment, *segments]
        path = "/".join(segments)
        url = urljoin(self.base_url, path)

        if query_string:
            url = f"{url}?{query_string}"
        return url

    @staticmethod
    def _create_view_cache_key(
        *,
        view_id: str,
        display_id: str,
        locale_segment: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        cache_key: str | None = None,
    ) -> str:
        """Generate a cache key for a JSON:API Views request.

        Format: ``view--{locale--}{view_id}--{display_id}[--sha256(qs)]``
        """
        if cache_key is not None:
            return cache_key

        if query_string is not None and hasattr(query_string, "get_query_string"):
            query_string = query_string.get_query_string()

        parts: list[str] = ["view"]
        if locale_segment:
            parts.append(locale_segment)
        parts.append(view_id)
        parts.append(display_id)
        if query_string:
            hash_hex = hashlib.sha256(query_string.encode()).hexdigest()
            parts.append(hash_hex)
        return "--".join(parts)

    # -- write operations ---------------------------------------------------

    _JSONAPI_CONTENT_TYPE = "application/vnd.api+json"

    def create_resource(
        self,
        resource_type: str,
        body: dict[str, Any],
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Create a new resource.

        POSTs *body* (a JSON:API document with ``data``) to the collection
        endpoint.  Invalidates any cached canonical collection entry for
        *resource_type* on success, plus *cache_key* if given — pass the
        custom key you read the collection under, or it stays stale.

        When *raise_for_status* is ``False`` and the server returns ≥400,
        the parsed error response body is returned (typically
        ``{"errors": [...]}``).  Cache invalidation does **not** run in
        this case.
        """
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale

        if self.index_lookup:
            self._fetch_index(locale_segment=locale_segment)

        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )

        logger.debug("Creating resource at %s", url)
        response = self.fetch(
            url,
            method="POST",
            headers={"Content-Type": self._JSONAPI_CONTENT_TYPE},
            json=body,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

        parsed = self._process_api_response(response)

        if response.status_code < 400:
            self._invalidate_cache(
                resource_type=resource_type, cache_key=cache_key
            )

        if raw_response:
            return RawJsonApiResponse(response=response, json=parsed)
        return parsed

    def update_resource(
        self,
        resource_type: str,
        resource_id: str,
        body: dict[str, Any],
        *,
        locale: str | None = None,
        # Accepts str or any object with a get_query_string() method
        # (e.g., DrupalJsonApiParams).
        query_string: Any = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Update an existing resource via PATCH.

        Invalidates the cached canonical resource entry AND the cached
        canonical collection entry for *resource_type* on success, plus
        *cache_key* if given.

        When *raise_for_status* is ``False`` and the server returns ≥400,
        the parsed error response body is returned (typically
        ``{"errors": [...]}``).  Cache invalidation does **not** run in
        this case.
        """
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale

        if self.index_lookup:
            self._fetch_index(locale_segment=locale_segment)

        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )

        logger.debug("Updating resource at %s", url)
        response = self.fetch(
            url,
            method="PATCH",
            headers={"Content-Type": self._JSONAPI_CONTENT_TYPE},
            json=body,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

        parsed = self._process_api_response(response)

        if response.status_code < 400:
            self._invalidate_cache(
                resource_type=resource_type,
                resource_id=resource_id,
                cache_key=cache_key,
            )

        if raw_response:
            return RawJsonApiResponse(response=response, json=parsed)
        return parsed

    def delete_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        locale: str | None = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> None | RawJsonApiResponse:
        """Delete a resource.

        Invalidates the cached canonical resource entry AND the cached
        canonical collection entry on success, plus *cache_key* if given.

        Returns ``None`` by default (Drupal responds with 204).  When
        *raw_response* is ``True``, returns a :class:`RawJsonApiResponse`.

        When *raise_for_status* is ``False`` and the server returns ≥400,
        the method returns ``None`` (no cache invalidation runs).  Use
        *raw_response=True* to inspect the error body.
        """
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale

        if self.index_lookup:
            self._fetch_index(locale_segment=locale_segment)

        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
        )

        logger.debug("Deleting resource at %s", url)
        response = self.fetch(
            url,
            method="DELETE",
            headers={"Content-Type": self._JSONAPI_CONTENT_TYPE},
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

        if response.status_code < 400:
            self._invalidate_cache(
                resource_type=resource_type,
                resource_id=resource_id,
                cache_key=cache_key,
            )

        if raw_response:
            parsed = self._process_api_response(response)
            return RawJsonApiResponse(response=response, json=parsed)
        return None

    # -- cache invalidation (private) ---------------------------------------

    def _invalidate_cache(
        self,
        *,
        resource_type: str,
        resource_id: str | None = None,
        cache_key: str | None = None,
    ) -> None:
        """Drop canonical cache entries for a resource type and optionally a UUID.

        Called from write methods after a successful response.  No-op if
        ``self.cache is None``.

        When *cache_key* is given it is dropped **in addition to** the
        canonical keys, not instead of them: a custom key belongs to one
        caller, but other callers may have cached the same resource under
        the default key.

        Only the canonical keys (no locale, no query string) are dropped.
        Cached reads with locales or query strings remain stale until they
        expire or are refetched with ``disable_cache=True`` — pass the
        ``cache_key`` you read under to invalidate a specific entry.
        """
        if self.cache is None:
            return
        if cache_key is not None:
            self.cache.delete(cache_key)
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        collection_key = self.create_cache_key(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
        )
        self.cache.delete(collection_key)
        if resource_id is not None:
            resource_key = self.create_cache_key(
                entity_type_id=entity_type_id,
                bundle_id=bundle_id,
                resource_id=resource_id,
            )
            self.cache.delete(resource_key)
