"""DecoupledRouterClient — Drupal Decoupled Router integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from drupal_api_client.auth import Authentication
from drupal_api_client.cache import Cache
from drupal_api_client.client import ApiClient
from drupal_api_client.serializer import Serializer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedPath:
    """Resolved entity info from Drupal's Decoupled Router."""

    resolved: bool
    is_home_path: bool
    entity: dict[str, Any]
    label: str | None
    jsonapi: dict[str, Any] | None
    meta: dict[str, Any] | None


@dataclass(frozen=True)
class UnresolvedPath:
    """Unresolved path response from Drupal's Decoupled Router."""

    resolved: bool
    message: str | None
    details: dict[str, Any] | None


DecoupledRouterResponse = ResolvedPath | UnresolvedPath


@dataclass(frozen=True)
class RawDecoupledRouterResponse:
    """Raw response when caller passes ``raw_response=True``."""

    response: httpx.Response
    json: dict[str, Any]


def _parse_response(json_data: dict[str, Any]) -> DecoupledRouterResponse:
    """Parse a Decoupled Router JSON body into the appropriate dataclass.

    Uses the presence of the ``entity`` key to distinguish resolved from
    unresolved paths — mirrors the JS ``isResolved`` type predicate.
    """
    if "entity" in json_data:
        return ResolvedPath(
            resolved=json_data.get("resolved", True),
            # camelCase mapping: isHomePath → is_home_path
            is_home_path=json_data.get("isHomePath", False),
            entity=json_data["entity"],
            label=json_data.get("label"),
            jsonapi=json_data.get("jsonapi"),
            meta=json_data.get("meta"),
        )
    return UnresolvedPath(
        resolved=json_data.get("resolved", False),
        message=json_data.get("message"),
        details=json_data.get("details"),
    )


class DecoupledRouterClient(ApiClient):
    """Client for Drupal's Decoupled Router module.

    Extends :class:`ApiClient` to provide :meth:`translate_path`, which
    resolves a path alias to Drupal entity info.
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
        self.api_prefix = api_prefix or "router/translate-path"

    def translate_path(
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
        """Translate a path alias to Drupal entity information.

        Parameters
        ----------
        path:
            The path to translate (e.g. ``"/about-us"``).
        locale:
            Override locale for this request.  Falls back to
            :attr:`default_locale` when ``None``.
        raw_response:
            If ``True``, return a :class:`RawDecoupledRouterResponse`
            containing both the ``httpx.Response`` and parsed JSON.
        disable_cache:
            Skip both cache reads and writes for this request.
        disable_authentication:
            Bypass auth header injection for this request.
        cache_key:
            Explicit cache key.  When provided, overrides the
            auto-generated key derived from *locale* and *path*.
        raise_for_status:
            If ``True``, raise ``httpx.HTTPStatusError`` on 4xx/5xx.
        """
        locale_segment = locale or self.default_locale
        api_url = self.create_url(path=path, locale_segment=locale_segment)
        resolved_cache_key = self.create_cache_key(
            path=path,
            locale_segment=locale_segment,
            cache_key=cache_key,
        )

        # Check cache (skip for raw mode and when cache disabled)
        if not raw_response and not disable_cache:
            cached = self.get_cached_response(resolved_cache_key)
            if cached is not None:
                return _parse_response(cached)

        logger.debug("Fetching endpoint %s", api_url)
        response = self.fetch(
            api_url,
            disable_authentication=disable_authentication,
        )

        if raise_for_status:
            response.raise_for_status()

        json_data = response.json()

        # Cache parsed JSON for successful responses only (status < 400)
        if (
            self.cache is not None
            and not disable_cache
            and response.status_code < 400
        ):
            self.cache.set(resolved_cache_key, json_data)

        if raw_response:
            return RawDecoupledRouterResponse(response=response, json=json_data)

        return _parse_response(json_data)

    def create_url(
        self,
        *,
        path: str,
        locale_segment: str | None = None,
    ) -> str:
        """Build the translate-path URL.

        Shape: ``{base_url}{locale_segment/}{api_prefix}?path={path}``
        """
        api_prefix = self.api_prefix or "router/translate-path"
        prefix = (
            f"{locale_segment}/{api_prefix}"
            if locale_segment
            else api_prefix
        )
        url = urljoin(self.base_url, prefix)
        return f"{url}?{urlencode({'path': path})}"

    @staticmethod
    def create_cache_key(
        *,
        path: str | None = None,
        locale_segment: str | None = None,
        cache_key: str | None = None,
    ) -> str:
        """Generate a cache key.

        If *cache_key* is provided it is returned verbatim.  Otherwise
        the key is derived from *locale_segment* and *path*.

        Raises :class:`ValueError` if both *path* and *cache_key* are
        ``None``.
        """
        if cache_key is not None:
            return cache_key

        if path is None:
            raise ValueError(
                "The path or cache_key option is required to generate a cache key."
            )

        return f"{locale_segment}--{path}" if locale_segment else path
