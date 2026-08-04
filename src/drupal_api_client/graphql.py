"""GraphqlClient — Drupal GraphQL integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.client import ApiClient
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


class GraphqlClient(ApiClient):
    """Client for a Drupal GraphQL endpoint.

    Extends :class:`ApiClient` to provide :meth:`query`, which POSTs a
    GraphQL query and returns the parsed JSON response. Authentication,
    injected HTTP client, and logging are inherited from the base class.
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
        self.api_prefix = api_prefix or "graphql"

    def query(
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
        disable_authentication: bool = False,
        raise_for_status: bool = False,
    ) -> dict[str, Any]:
        """Execute a GraphQL query and return the parsed JSON body.

        Parameters
        ----------
        query:
            The GraphQL query string.
        variables:
            Optional GraphQL variables. When ``None`` the request body is
            ``{"query": ...}`` — byte-identical to the JS client. When
            provided, a ``"variables"`` key is added (a Python enhancement
            over the JS client, which does not support variables).
        disable_authentication:
            Bypass auth header injection for this request.
        raise_for_status:
            If ``True``, raise ``httpx.HTTPStatusError`` on 4xx/5xx.

        Notes
        -----
        A GraphQL server returns HTTP 200 with an ``errors`` array for
        query-level errors. Like the JS client, this method does not
        inspect ``errors`` — it returns the raw parsed body, leaving error
        handling to the caller.
        """
        url = urljoin(self.base_url, self.api_prefix or "graphql")
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        logger.debug("Executing GraphQL query at %s", url)
        response = self.fetch(
            url,
            method="POST",
            json=payload,
            disable_authentication=disable_authentication,
            raise_for_status=raise_for_status,
        )
        return response.json()
