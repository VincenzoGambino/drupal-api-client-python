"""AsyncJsonApiClient — async JSON:API integration for Drupal.

Subclasses :class:`AsyncApiClient` (async I/O + lifecycle) and
:class:`JsonApiClient` (all pure helpers: ``create_url``, ``create_cache_key``,
``_get_entity_type_and_bundle``, view helpers, ``_process_api_response``,
``_invalidate_cache``). Only the I/O-bearing methods are overridden as ``async``.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

import httpx

from drupal_api_client.async_client import AsyncApiClient
from drupal_api_client.async_decoupled_router import AsyncDecoupledRouterClient
from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.decoupled_router import ResolvedPath, UnresolvedPath
from drupal_api_client.errors import ResourceNotFoundError
from drupal_api_client.jsonapi import (
    JsonApiClient,
    RawJsonApiResponse,
    _resource_type_from_router,
)
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


class AsyncJsonApiClient(AsyncApiClient, JsonApiClient):
    """Async client for Drupal's JSON:API."""

    router: AsyncDecoupledRouterClient  # type: ignore[assignment]

    def __init__(
        self,
        base_url: str,
        *,
        api_prefix: str | None = None,
        authentication: Authentication | None = None,
        cache: Cache | None = None,
        serializer: Serializer | None = None,
        default_locale: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float | httpx.Timeout = 30.0,
        index_lookup: bool = False,
        decoupled_router_api_prefix: str | None = None,
    ) -> None:
        AsyncApiClient.__init__(
            self,
            base_url,
            api_prefix=api_prefix,
            authentication=authentication,
            cache=cache,
            serializer=serializer,
            default_locale=default_locale,
            http_client=http_client,  # type: ignore[arg-type]  # AsyncClient stored generically
            timeout=timeout,
        )
        self.api_prefix = api_prefix or "jsonapi"
        self.index_lookup = index_lookup
        self.decoupled_router_api_prefix = decoupled_router_api_prefix
        self._index_cache = {}

        self.router = AsyncDecoupledRouterClient(
            base_url,
            api_prefix=decoupled_router_api_prefix,
            authentication=authentication,
            cache=cache,
            serializer=serializer,
            default_locale=default_locale,
            http_client=http_client,
            timeout=timeout,
        )

    # -- lifecycle ------------------------------------------------------

    async def __aenter__(self) -> AsyncJsonApiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close both the owned async client and the router's client."""
        await AsyncApiClient.aclose(self)
        await self.router.aclose()

    # -- index ----------------------------------------------------------

    async def _fetch_index(  # type: ignore[override]
        self, locale_segment: str | None = None
    ) -> None:
        """Fetch and cache the JSON:API index for *locale_segment* (async).

        Mirrors :meth:`JsonApiClient._fetch_index`: reads from and writes to
        the injected cache under ``{locale/}{api_prefix}`` (the JS key), with
        :attr:`_index_cache` as an in-instance memo.
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
        response = await self.fetch(index_url)
        response.raise_for_status()
        body = response.json()
        if self.cache is not None and response.status_code < 400:
            self.cache.set(cache_key, body)
        self._index_cache[locale_segment] = body.get("links", {})

    # -- shared read flow -----------------------------------------------

    async def _execute_read(  # type: ignore[override]
        self,
        *,
        url: str,
        cache_key: str,
        raw_response: bool,
        disable_cache: bool,
        disable_authentication: bool,
        raise_for_status: bool,
    ) -> dict[str, Any] | RawJsonApiResponse:
        if not raw_response and not disable_cache:
            cached = self.get_cached_response(cache_key)
            if cached is not None:
                return cached

        logger.debug("Fetching %s", url)
        response = await self.fetch(
            url, disable_authentication=disable_authentication
        )
        if raise_for_status:
            response.raise_for_status()

        parsed = self._process_api_response(response)

        if (
            not raw_response
            and not disable_cache
            and self.cache is not None
            and response.status_code < 400
        ):
            self.cache.set(cache_key, parsed)

        if raw_response:
            return RawJsonApiResponse(response=response, json=parsed)
        return parsed

    # -- reads ----------------------------------------------------------

    async def get_collection(  # type: ignore[override]
        self,
        resource_type: str,
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a collection of resources of a given type (async)."""
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
            await self._fetch_index(locale_segment=locale_segment)
        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )
        return await self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    async def get_resource(  # type: ignore[override]
        self,
        resource_type: str,
        resource_id: str,
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a single resource by type and UUID (async)."""
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
            await self._fetch_index(locale_segment=locale_segment)
        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )
        return await self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    async def get_view(  # type: ignore[override]
        self,
        view_id: str,
        display_id: str,
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Retrieve a view display via JSON:API Views (async)."""
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
        return await self._execute_read(
            url=url,
            cache_key=resolved_cache_key,
            raw_response=raw_response,
            disable_cache=disable_cache,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )

    async def get_resource_by_path(  # type: ignore[override]
        self,
        path: str,
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Resolve a path alias then fetch the underlying resource (async)."""
        try:
            router_response = await self.router.translate_path(
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

        uuid = router_response.entity["uuid"]
        resource_type = _resource_type_from_router(router_response)

        return await self.get_resource(
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

    # -- writes ---------------------------------------------------------

    async def create_resource(  # type: ignore[override]
        self,
        resource_type: str,
        body: dict[str, Any],
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Create a new resource via POST (async)."""
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale
        if self.index_lookup:
            await self._fetch_index(locale_segment=locale_segment)
        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )
        logger.debug("Creating resource at %s", url)
        response = await self.fetch(
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

    async def update_resource(  # type: ignore[override]
        self,
        resource_type: str,
        resource_id: str,
        body: dict[str, Any],
        *,
        locale: str | None = None,
        query_string: Any = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> dict[str, Any] | RawJsonApiResponse:
        """Update an existing resource via PATCH (async)."""
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale
        if self.index_lookup:
            await self._fetch_index(locale_segment=locale_segment)
        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
            query_string=query_string,
        )
        logger.debug("Updating resource at %s", url)
        response = await self.fetch(
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

    async def delete_resource(  # type: ignore[override]
        self,
        resource_type: str,
        resource_id: str,
        *,
        locale: str | None = None,
        raw_response: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = True,
    ) -> RawJsonApiResponse | None:
        """Delete a resource (async)."""
        entity_type_id, bundle_id = self._get_entity_type_and_bundle(resource_type)
        locale_segment = locale or self.default_locale
        if self.index_lookup:
            await self._fetch_index(locale_segment=locale_segment)
        url = self.create_url(
            entity_type_id=entity_type_id,
            bundle_id=bundle_id,
            resource_id=resource_id,
            locale_segment=locale_segment,
        )
        logger.debug("Deleting resource at %s", url)
        response = await self.fetch(
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
