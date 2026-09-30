"""AsyncApiClient — async base HTTP client for Drupal APIs.

Mirrors :class:`~drupal_api_client.client.ApiClient` on top of
``httpx.AsyncClient``. Pure helpers (auth header assembly is re-implemented as
async only because of the OAuth token fetch; everything non-I/O is inherited).
"""

from __future__ import annotations

import base64
import logging
import time
from types import TracebackType
from typing import Any

import httpx

from drupal_api_client.auth import (
    BasicAuth,
    CustomAuth,
    OAuthAuth,
    OAuthTokenResponse,
)
from drupal_api_client.client import ApiClient
from drupal_api_client.errors import AuthenticationError

logger = logging.getLogger(__name__)


class AsyncApiClient(ApiClient):
    """Async base class for all async API clients.

    Inherits the pure/sync helpers from :class:`ApiClient`
    (``get_cached_response``, cache handling) and overrides every I/O path
    with ``async`` variants. Use as an async context manager::

        async with AsyncApiClient("https://example.com") as client:
            response = await client.fetch(url)
    """

    _http_client: httpx.AsyncClient  # type: ignore[assignment]

    def _make_http_client(  # type: ignore[override]
        self, timeout: float | httpx.Timeout
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    # -- lifecycle: async only ------------------------------------------

    def __enter__(self) -> Any:  # pragma: no cover - guard
        raise TypeError("Use 'async with' (async context manager) for AsyncApiClient")

    def __exit__(self, *exc: object) -> None:  # pragma: no cover - guard
        raise TypeError("Use 'async with' (async context manager) for AsyncApiClient")

    def close(self) -> None:  # pragma: no cover - guard
        raise TypeError("Use 'await aclose()' to close an AsyncApiClient")

    async def __aenter__(self) -> AsyncApiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP client if this instance owns it."""
        if self._owns_client:
            await self._http_client.aclose()

    # -- I/O ------------------------------------------------------------

    async def fetch(  # type: ignore[override]
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        json: Any = None,
        content: bytes | str | None = None,
        disable_authentication: bool = False,
        raise_for_status: bool = False,
    ) -> httpx.Response:
        """Send an HTTP request and return the response."""
        if json is not None and content is not None:
            raise ValueError("json and content are mutually exclusive")

        if disable_authentication:
            logger.debug("Disabling authentication for request to %s", url)
            merged_headers = dict(headers) if headers else {}
        else:
            merged_headers = await self.add_authorization_header(headers)

        response = await self._http_client.request(
            method,
            url,
            headers=merged_headers,
            json=json,
            content=content,
        )

        if self._should_retry_with_new_token(response, disable_authentication):
            logger.debug("Got 401 for %s. Fetching a new OAuth token and retrying.", url)
            self._oauth_token_response = None
            response = await self._http_client.request(
                method,
                url,
                headers=await self.add_authorization_header(headers),
                json=json,
                content=content,
            )

        if raise_for_status:
            response.raise_for_status()

        return response

    async def add_authorization_header(  # type: ignore[override]
        self,
        headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return a **new** dict with the Authorization header injected."""
        result = dict(headers) if headers else {}

        if self.authentication is None:
            return result

        match self.authentication:
            case BasicAuth(username=username, password=password):
                encoded = base64.b64encode(
                    f"{username}:{password}".encode()
                ).decode()
                result["Authorization"] = f"Basic {encoded}"

            case OAuthAuth() as oauth:
                token = self._oauth_token_response
                if token is None or not self._is_oauth_token_fresh(token, oauth):
                    logger.debug(
                        "OAuth token is missing or expired. Fetching a new one."
                    )
                    token = await self._get_access_token(oauth)
                result["Authorization"] = f"{token.token_type} {token.access_token}"

            case CustomAuth(value=value):
                result["Authorization"] = value

        return result

    async def _get_access_token(  # type: ignore[override]
        self, credentials: OAuthAuth
    ) -> OAuthTokenResponse:
        """Fetch an OAuth token from ``{base_url}oauth/token`` (async)."""
        token_body = self._build_token_request_body(credentials)
        api_url = f"{self.base_url}oauth/token"
        response = await self._http_client.post(
            api_url,
            data=token_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.is_success:
            json_data = response.json()
            token = OAuthTokenResponse(
                access_token=json_data["access_token"],
                valid_until=time.time() + json_data["expires_in"],
                token_type=json_data["token_type"],
            )
            self._oauth_token_response = token
            return token

        raise AuthenticationError(
            "Could not authenticate with the provided credentials."
        )
