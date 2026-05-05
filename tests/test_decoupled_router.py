"""Tests for DecoupledRouterClient."""

import httpx
import pytest
import respx

from drupal_api_client import (
    BasicAuth,
    DecoupledRouterClient,
    InMemoryCache,
    RawDecoupledRouterResponse,
    ResolvedPath,
    UnresolvedPath,
)


RESOLVED_BODY: dict = {
    "resolved": True,
    "isHomePath": False,
    "entity": {
        "canonical": "https://example.com/node/1",
        "type": "node",
        "bundle": "article",
        "id": "1",
        "uuid": "abc-123",
    },
    "label": "Hello world",
    "jsonapi": {
        "individual": "https://example.com/jsonapi/node/article/abc-123",
        "resourceName": "node--article",
        "pathPrefix": "jsonapi",
        "basePath": "/jsonapi",
        "entryPoint": "https://example.com/jsonapi",
    },
}

UNRESOLVED_BODY: dict = {
    "resolved": False,
    "message": "Unable to resolve path /nonexistent.",
    "details": {
        "info": "None of the available routers were able to handle this request.",
    },
}

TRANSLATE_URL = "https://example.com/router/translate-path"


# -- translate_path ---------------------------------------------------------


class TestTranslatePathHappyPath:
    @respx.mock
    def test_returns_resolved_path(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        with DecoupledRouterClient("https://example.com") as client:
            result = client.translate_path("/about-us")
            assert isinstance(result, ResolvedPath)
            assert result.resolved is True
            assert result.is_home_path is False
            assert result.entity["uuid"] == "abc-123"
            assert result.entity["bundle"] == "article"
            assert result.label == "Hello world"
            assert result.jsonapi is not None
            assert result.jsonapi["resourceName"] == "node--article"


class TestTranslatePathRawResponse:
    @respx.mock
    def test_returns_raw_response(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        with DecoupledRouterClient("https://example.com") as client:
            result = client.translate_path("/about-us", raw_response=True)
            assert isinstance(result, RawDecoupledRouterResponse)
            assert result.response.status_code == 200
            assert result.json["resolved"] is True
            assert result.json["entity"]["uuid"] == "abc-123"


class TestTranslatePathLocale:
    @respx.mock
    def test_url_contains_locale(self) -> None:
        respx.get(
            "https://example.com/es/router/translate-path",
            params={"path": "/sobre-nosotros"},
        ).mock(return_value=httpx.Response(200, json=RESOLVED_BODY))
        with DecoupledRouterClient("https://example.com") as client:
            result = client.translate_path("/sobre-nosotros", locale="es")
            assert isinstance(result, ResolvedPath)


class TestTranslatePath404:
    @respx.mock
    def test_does_not_raise_returns_unresolved(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_BODY)
        )
        with DecoupledRouterClient("https://example.com") as client:
            result = client.translate_path("/nonexistent")
            assert isinstance(result, UnresolvedPath)
            assert result.resolved is False
            assert result.message == "Unable to resolve path /nonexistent."

    @respx.mock
    def test_raise_for_status_raises_on_404(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_BODY)
        )
        with DecoupledRouterClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.translate_path("/nonexistent", raise_for_status=True)


class TestTranslatePathDisableAuthentication:
    @respx.mock
    def test_disable_authentication_bypasses_auth(self) -> None:
        route = respx.get(TRANSLATE_URL, params={"path": "/x"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        with DecoupledRouterClient(
            "https://example.com",
            authentication=BasicAuth(username="admin", password="secret"),
        ) as client:
            client.translate_path("/x", disable_authentication=True)
            request = route.calls[0].request
            assert "authorization" not in request.headers


# -- cache ------------------------------------------------------------------


class TestTranslatePathCache:
    @respx.mock
    def test_cache_hit_skips_http(self) -> None:
        route = respx.get(TRANSLATE_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        cache = InMemoryCache()
        with DecoupledRouterClient("https://example.com", cache=cache) as client:
            client.translate_path("/about-us")
            assert route.call_count == 1
            # Second call should hit cache — no additional HTTP request.
            result = client.translate_path("/about-us")
            assert route.call_count == 1
            assert isinstance(result, ResolvedPath)

    @respx.mock
    def test_cache_miss_writes(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        cache = InMemoryCache()
        with DecoupledRouterClient("https://example.com", cache=cache) as client:
            client.translate_path("/about-us")
            assert cache.get("/about-us") is not None

    @respx.mock
    def test_disable_cache_bypasses_cache(self) -> None:
        route = respx.get(TRANSLATE_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_BODY)
        )
        cache = InMemoryCache()
        with DecoupledRouterClient("https://example.com", cache=cache) as client:
            client.translate_path("/about-us", disable_cache=True)
            # No cache write.
            assert cache.get("/about-us") is None
            # Second call also hits HTTP.
            client.translate_path("/about-us", disable_cache=True)
            assert route.call_count == 2

    @respx.mock
    def test_does_not_cache_4xx(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_BODY)
        )
        cache = InMemoryCache()
        with DecoupledRouterClient("https://example.com", cache=cache) as client:
            client.translate_path("/nonexistent")
            assert cache.get("/nonexistent") is None


# -- create_url -------------------------------------------------------------


class TestCreateUrl:
    def test_without_locale(self) -> None:
        with DecoupledRouterClient("https://example.com") as client:
            url = client.create_url(path="/about-us")
            assert (
                url
                == "https://example.com/router/translate-path?path=%2Fabout-us"
            )

    def test_with_locale(self) -> None:
        with DecoupledRouterClient("https://example.com") as client:
            url = client.create_url(path="/about-us", locale_segment="es")
            assert (
                url
                == "https://example.com/es/router/translate-path?path=%2Fabout-us"
            )

    def test_url_encodes_special_characters(self) -> None:
        with DecoupledRouterClient("https://example.com") as client:
            url = client.create_url(path="/about us & more")
            assert "path=%2Fabout+us+%26+more" in url


# -- create_cache_key -------------------------------------------------------


class TestCreateCacheKey:
    def test_returns_cache_key_verbatim(self) -> None:
        key = DecoupledRouterClient.create_cache_key(cache_key="custom-key")
        assert key == "custom-key"

    def test_returns_path_when_no_locale(self) -> None:
        key = DecoupledRouterClient.create_cache_key(path="/about-us")
        assert key == "/about-us"

    def test_returns_locale_path_with_locale(self) -> None:
        key = DecoupledRouterClient.create_cache_key(
            path="/about-us", locale_segment="es"
        )
        assert key == "es--/about-us"

    def test_raises_when_no_path_or_cache_key(self) -> None:
        with pytest.raises(ValueError, match="path or cache_key"):
            DecoupledRouterClient.create_cache_key()


# -- discriminated union ----------------------------------------------------


class TestDiscriminatedUnion:
    def test_resolved_path_construction(self) -> None:
        path = ResolvedPath(
            resolved=True,
            is_home_path=False,
            entity={"uuid": "abc-123", "type": "node"},
            label="Test",
            jsonapi=None,
            meta=None,
        )
        assert path.resolved is True
        assert path.entity["uuid"] == "abc-123"

    @respx.mock
    def test_unresolved_path_from_404(self) -> None:
        respx.get(TRANSLATE_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_BODY)
        )
        with DecoupledRouterClient("https://example.com") as client:
            result = client.translate_path("/nonexistent")
            assert isinstance(result, UnresolvedPath)
            assert result.resolved is False
            assert result.message is not None

    def test_match_case_dispatch(self) -> None:
        resolved: ResolvedPath | UnresolvedPath = ResolvedPath(
            resolved=True,
            is_home_path=False,
            entity={"uuid": "abc-123"},
            label="Test",
            jsonapi=None,
            meta=None,
        )
        unresolved: ResolvedPath | UnresolvedPath = UnresolvedPath(
            resolved=False,
            message="Not found",
            details=None,
        )

        results = []
        for response in (resolved, unresolved):
            match response:
                case ResolvedPath():
                    results.append("resolved")
                case UnresolvedPath():
                    results.append("unresolved")

        assert results == ["resolved", "unresolved"]
