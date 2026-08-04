"""AsyncDecoupledRouterClient — async Decoupled Router integration.

Subclasses :class:`AsyncApiClient` (async I/O + lifecycle) and
:class:`DecoupledRouterClient` (pure ``create_url``/``create_cache_key`` and the
``_parse_response`` helper), overriding only :meth:`translate_path` as async.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from drupal_api_client.async_client import AsyncApiClient
from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.decoupled_router import (
    DecoupledRouterClient,
    DecoupledRouterResponse,
    RawDecoupledRouterResponse,
    _parse_response,
)
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


class AsyncDecoupledRouterClient(AsyncApiClient, DecoupledRouterClient):
    """Async client for Drupal's Decoupled Router module."""

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
    ) -> None:
        # Call the async base __init__ (not DecoupledRouterClient.__init__,
        # which would build a sync httpx.Client); then set the router default.
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
        self.api_prefix = api_prefix or "router/translate-path"

    async def translate_path(  # type: ignore[override]
        self,
        path: str,
        *,
        locale: str | None = None,
        raw_response: bool = False,
        disable_cache: bool = False,
        disable_authentication: bool = False,
        cache_key: str | None = None,
        raise_for_status: bool = False,
    ) -> DecoupledRouterResponse | RawDecoupledRouterResponse:
        """Translate a path alias to Drupal entity information (async)."""
        locale_segment = locale or self.default_locale
        # Pure helpers reused from the sync class.
        api_url = self.create_url(path=path, locale_segment=locale_segment)
        resolved_cache_key = self.create_cache_key(
            path=path, locale_segment=locale_segment, cache_key=cache_key
        )

        if not raw_response and not disable_cache:
            cached = self.get_cached_response(resolved_cache_key)
            if cached is not None:
                return _parse_response(cached)

        logger.debug("Fetching endpoint %s", api_url)
        response = await self.fetch(
            api_url, disable_authentication=disable_authentication
        )

        if raise_for_status:
            response.raise_for_status()

        json_data: dict[str, Any] = response.json()

        if (
            self.cache is not None
            and not disable_cache
            and response.status_code < 400
        ):
            self.cache.set(resolved_cache_key, json_data)

        if raw_response:
            return RawDecoupledRouterResponse(response=response, json=json_data)
        return _parse_response(json_data)
