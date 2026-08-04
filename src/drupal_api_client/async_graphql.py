"""AsyncGraphqlClient — async Drupal GraphQL integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from drupal_api_client.async_client import AsyncApiClient
from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.graphql import GraphqlClient
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


class AsyncGraphqlClient(AsyncApiClient, GraphqlClient):
    """Async client for a Drupal GraphQL endpoint."""

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
        self.api_prefix = api_prefix or "graphql"

    async def query(  # type: ignore[override]
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
        disable_authentication: bool = False,
        raise_for_status: bool = False,
    ) -> dict[str, Any]:
        """Execute a GraphQL query and return the parsed JSON body (async)."""
        url = urljoin(self.base_url, self.api_prefix or "graphql")
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        logger.debug("Executing GraphQL query at %s", url)
        response = await self.fetch(
            url,
            method="POST",
            json=payload,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )
        return response.json()
