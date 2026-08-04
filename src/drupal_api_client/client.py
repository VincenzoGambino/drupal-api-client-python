"""ApiClient — base HTTP client for Drupal APIs."""

from __future__ import annotations

import base64
import logging
import time
from types import TracebackType
from typing import Any

import httpx

from drupal_api_client.auth import (
    Authentication,
    BasicAuth,
    CustomAuth,
    OAuthAuth,
    OAuthTokenResponse,
)
from drupal_api_client.cache import Cache
from drupal_api_client.errors import AuthenticationError, ConfigurationError
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


class ApiClient:
    """Base class providing common functionality for all API clients."""

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
        if not base_url:
            raise ConfigurationError("base_url is required")

        self.base_url: str = base_url if base_url.endswith("/") else f"{base_url}/"
        self.api_prefix: str | None = api_prefix
        self.authentication: Authentication | None = authentication
        self.cache: Cache | None = cache
        self.serializer: Serializer | None = serializer
        self.default_locale: str | None = default_locale

        if http_client is not None:
            self._http_client = http_client
            self._owns_client = False
        else:
            self._http_client = self._make_http_client(timeout)
            self._owns_client = True

        self._oauth_token_response: OAuthTokenResponse | None = None

    def _make_http_client(
        self, timeout: float | httpx.Timeout
    ) -> httpx.Client:
        """Create the HTTP client used when none is injected.

        Overridden by :class:`AsyncApiClient` to return an
        ``httpx.AsyncClient`` instead.
        """
        return httpx.Client(timeout=timeout)

    # -- context manager ------------------------------------------------

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            self._http_client.close()

    # -- public API -----------------------------------------------------

    def fetch(
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
        """Send an HTTP request and return the response.

        Transport errors (``httpx.HTTPError`` and subclasses) propagate as-is.
        """
        if json is not None and content is not None:
            raise ValueError("json and content are mutually exclusive")

        if disable_authentication:
            logger.debug("Disabling authentication for request to %s", url)
            merged_headers = dict(headers) if headers else {}
        else:
            merged_headers = self.add_authorization_header(headers)

        response = self._http_client.request(
            method,
            url,
            headers=merged_headers,
            json=json,
            content=content,
        )

        if raise_for_status:
            response.raise_for_status()

        return response

    def add_authorization_header(
        self,
        headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return a **new** dict with the Authorization header injected.

        The *headers* argument is not mutated.  If no authentication is
        configured the returned dict is a copy of *headers* (or an empty
        dict when *headers* is ``None``).
        """
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
                now = time.time()

                if (
                    token is None
                    or not token.access_token
                    or not token.token_type
                    or token.valid_until - 10 < now
                ):
                    logger.debug(
                        "OAuth token is missing or expired. Fetching a new one."
                    )
                    token = self._get_access_token(oauth)

                result["Authorization"] = (
                    f"{token.token_type} {token.access_token}"
                )

            case CustomAuth(value=value):
                result["Authorization"] = value

        return result

    def get_cached_response(self, cache_key: str) -> Any | None:
        """Retrieve a cached response.

        Returns ``None`` when no cache is configured or the key is absent.
        """
        if self.cache is None:
            return None
        logger.debug("Checking cache for key %s", cache_key)
        cached = self.cache.get(cache_key)
        if cached is None:
            logger.debug("No cached response found for key %s", cache_key)
            return None
        logger.debug("Found cached response for key %s", cache_key)
        return cached

    # -- protected / internal -------------------------------------------

    def _get_access_token(self, credentials: OAuthAuth) -> OAuthTokenResponse:
        """Fetch an OAuth token from ``{base_url}oauth/token``.

        This method bypasses :meth:`add_authorization_header` to avoid
        infinite recursion.
        """
        if not credentials.client_id or not credentials.client_secret:
            raise AuthenticationError(
                "client_id or client_secret is missing "
                "on the authentication option."
            )

        if credentials.grant_type == "password":
            if not credentials.username or not credentials.password:
                raise AuthenticationError(
                    "username or password is missing "
                    "on the authentication option."
                )
            token_body = {
                "grant_type": "password",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "username": credentials.username,
                "password": credentials.password,
            }
        else:
            token_body = {
                "grant_type": "client_credentials",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
            }

        api_url = f"{self.base_url}oauth/token"

        response = self._http_client.post(
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
