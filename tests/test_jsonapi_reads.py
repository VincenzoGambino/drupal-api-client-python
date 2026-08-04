"""Tests for JsonApiClient read operations (step 3b)."""

import copy
from typing import ClassVar
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from drupal_api_client import (
    InMemoryCache,
    JsonApiClient,
    RawJsonApiResponse,
    ResourceNotFoundError,
)

COLLECTION_URL = "https://example.com/jsonapi/node/article"
RESOURCE_URL = "https://example.com/jsonapi/node/article/abc-123"
VIEW_URL = "https://example.com/jsonapi/views/recipes/page_1"
INDEX_URL = "https://example.com/jsonapi"
ROUTER_URL = "https://example.com/router/translate-path"

COLLECTION_BODY: dict = {
    "data": [
        {
            "type": "node--article",
            "id": "abc-123",
            "attributes": {"title": "Hello world"},
        }
    ],
    "links": {"self": {"href": COLLECTION_URL}},
}

RESOURCE_BODY: dict = {
    "data": {
        "type": "node--article",
        "id": "abc-123",
        "attributes": {"title": "Hello world"},
    },
    "links": {"self": {"href": RESOURCE_URL}},
}

VIEW_BODY: dict = {
    "data": [
        {
            "type": "node--recipe",
            "id": "def-456",
            "attributes": {"title": "Pasta"},
        }
    ],
    "links": {"self": {"href": VIEW_URL}},
}

INDEX_BODY: dict = {
    "jsonapi": {"version": "1.0", "meta": {}},
    "data": [],
    "meta": {},
    "links": {
        "node--article": {"href": "https://example.com/jsonapi/node/article"},
        "node--page": {"href": "https://example.com/jsonapi/node/page"},
    },
}

RESOLVED_ROUTER_BODY: dict = {
    "resolved": "https://example.com/about-us",
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
    },
}

# `details` is a string in the real Decoupled Router 404 body - see
# tests/fixtures/unresolved-article.json.
UNRESOLVED_ROUTER_BODY: dict = {
    "message": "Unable to resolve path /nonexistent.",
    "details": "None of the available methods were able to find a match for this path.",
}


# -- get_collection ---------------------------------------------------------


class TestGetCollection:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_collection("node--article")
            assert result == COLLECTION_BODY

    @respx.mock
    def test_with_query_string(self) -> None:
        respx.get(
            COLLECTION_URL,
            params=None,
        ).mock(return_value=httpx.Response(200, json=COLLECTION_BODY))
        respx.get(url__regex=r".*filter.*").mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_collection(
                "node--article", query_string="filter[title]=Hello"
            )
            assert result == COLLECTION_BODY

    @respx.mock
    def test_with_query_string_stub_object(self) -> None:
        class StubParams:
            def get_query_string(self) -> str:
                return "filter[status]=1"

        respx.get(url__regex=r".*filter.*").mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_collection(
                "node--article", query_string=StubParams()
            )
            assert result == COLLECTION_BODY

    @respx.mock
    def test_with_locale(self) -> None:
        respx.get("https://example.com/es/jsonapi/node/article").mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_collection("node--article", locale="es")
            assert result == COLLECTION_BODY

    @respx.mock
    def test_cache_hit_skips_http(self) -> None:
        route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_collection("node--article")
            assert route.call_count == 1
            result = client.get_collection("node--article")
            assert route.call_count == 1
            assert result == COLLECTION_BODY

    @respx.mock
    def test_cache_miss_writes(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_collection("node--article")
            assert cache.get("node--article") is not None

    @respx.mock
    def test_disable_cache_bypasses(self) -> None:
        route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_collection("node--article", disable_cache=True)
            assert cache.get("node--article") is None
            client.get_collection("node--article", disable_cache=True)
            assert route.call_count == 2

    @respx.mock
    def test_4xx_not_cached(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(404, json={"errors": []})
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_collection("node--article")
            assert cache.get("node--article") is None

    @respx.mock
    def test_raw_response(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_collection("node--article", raw_response=True)
            assert isinstance(result, RawJsonApiResponse)
            assert result.response.status_code == 200
            assert result.json == COLLECTION_BODY

    @respx.mock
    def test_raw_response_does_not_write_cache(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_collection("node--article", raw_response=True)
            assert cache.get("node--article") is None

    @respx.mock
    def test_raise_for_status(self) -> None:
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(404, json={"errors": []})
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get_collection(
                    "node--article", raise_for_status=True
                )

    @respx.mock
    def test_disable_authentication(self) -> None:
        from drupal_api_client import BasicAuth

        route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com",
            authentication=BasicAuth(username="u", password="p"),
        ) as client:
            client.get_collection(
                "node--article", disable_authentication=True
            )
            request = route.calls[0].request
            assert "authorization" not in request.headers


# -- get_resource -----------------------------------------------------------


class TestGetResource:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_resource("node--article", "abc-123")
            assert result == RESOURCE_BODY

    @respx.mock
    def test_url_contains_uuid(self) -> None:
        route = respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            client.get_resource("node--article", "abc-123")
            assert "abc-123" in str(route.calls[0].request.url)

    @respx.mock
    def test_cache_key_includes_uuid(self) -> None:
        route = respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_resource("node--article", "abc-123")
            assert route.call_count == 1
            # Second call hits cache
            result = client.get_resource("node--article", "abc-123")
            assert route.call_count == 1
            assert result == RESOURCE_BODY

    @respx.mock
    def test_raw_response(self) -> None:
        respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_resource(
                "node--article", "abc-123", raw_response=True
            )
            assert isinstance(result, RawJsonApiResponse)

    @respx.mock
    def test_disable_cache(self) -> None:
        route = respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_resource(
                "node--article", "abc-123", disable_cache=True
            )
            client.get_resource(
                "node--article", "abc-123", disable_cache=True
            )
            assert route.call_count == 2

    @respx.mock
    def test_raise_for_status(self) -> None:
        respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(404, json={"errors": []})
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get_resource(
                    "node--article", "abc-123", raise_for_status=True
                )


# -- get_view ---------------------------------------------------------------


class TestGetView:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.get(VIEW_URL).mock(
            return_value=httpx.Response(200, json=VIEW_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_view("recipes", "page_1")
            assert result == VIEW_BODY

    @respx.mock
    def test_url_shape(self) -> None:
        route = respx.get(VIEW_URL).mock(
            return_value=httpx.Response(200, json=VIEW_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            client.get_view("recipes", "page_1")
            assert str(route.calls[0].request.url) == VIEW_URL

    @respx.mock
    def test_with_query_string(self) -> None:
        respx.get(url__regex=r".*/views/recipes/page_1\?.*").mock(
            return_value=httpx.Response(200, json=VIEW_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_view(
                "recipes", "page_1", query_string="page[limit]=5"
            )
            assert result == VIEW_BODY

    @respx.mock
    def test_with_locale(self) -> None:
        respx.get("https://example.com/es/jsonapi/views/recipes/page_1").mock(
            return_value=httpx.Response(200, json=VIEW_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_view("recipes", "page_1", locale="es")
            assert result == VIEW_BODY

    @respx.mock
    def test_cache_key_has_view_prefix(self) -> None:
        respx.get(VIEW_URL).mock(
            return_value=httpx.Response(200, json=VIEW_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.get_view("recipes", "page_1")
            assert cache.get("view--recipes--page_1") is not None


# -- get_resource_by_path ---------------------------------------------------


class TestGetResourceByPath:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_ROUTER_BODY)
        )
        respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_resource_by_path("/about-us")
            assert result == RESOURCE_BODY

    @respx.mock
    def test_honors_rewritten_jsonapi_resource_name(self) -> None:
        """Regression test: the resource type must come from the router's
        `jsonapi.resourceName`, not from entity type+bundle.

        `jsonapi_extras` can rename a resource - here `node--article` is
        exposed as `content--story`. Building the type from entity
        type+bundle would request /jsonapi/node/article/... and 404.
        The JS client reads `routingData.jsonapi.resourceName`; so do we.
        """
        rewritten = copy.deepcopy(RESOLVED_ROUTER_BODY)
        rewritten["jsonapi"]["resourceName"] = "content--story"

        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=rewritten)
        )
        rewritten_route = respx.get(
            "https://example.com/jsonapi/content/story/abc-123"
        ).mock(return_value=httpx.Response(200, json=RESOURCE_BODY))

        with JsonApiClient("https://example.com") as client:
            result = client.get_resource_by_path("/about-us")

        assert rewritten_route.called
        assert result == RESOURCE_BODY

    @respx.mock
    def test_falls_back_to_entity_type_and_bundle(self) -> None:
        """Routers that omit `jsonapi.resourceName` still resolve, via
        the entity's type/bundle."""
        without_jsonapi = copy.deepcopy(RESOLVED_ROUTER_BODY)
        del without_jsonapi["jsonapi"]

        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=without_jsonapi)
        )
        fallback_route = respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )

        with JsonApiClient("https://example.com") as client:
            result = client.get_resource_by_path("/about-us")

        assert fallback_route.called
        assert result == RESOURCE_BODY

    @respx.mock
    def test_raises_on_unresolved(self) -> None:
        respx.get(ROUTER_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_ROUTER_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(ResourceNotFoundError, match="could not be resolved"):
                client.get_resource_by_path("/nonexistent")

    @respx.mock
    def test_raises_resource_not_found_even_with_raise_for_status_true(
        self,
    ) -> None:
        """Regression test: forwarding raise_for_status to the router leg
        must not turn a normal "not resolved" 404 into an
        httpx.HTTPStatusError - Decoupled Router's 404 is its regular
        signal for "not found", not an infrastructure failure (see
        CHANGELOG).
        """
        respx.get(ROUTER_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_ROUTER_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(ResourceNotFoundError, match="could not be resolved"):
                client.get_resource_by_path(
                    "/nonexistent", raise_for_status=True
                )

    @respx.mock
    def test_raise_for_status_true_router_5xx_raises_cleanly(self) -> None:
        """Regression test for the bug: get_resource_by_path's
        raise_for_status previously never reached the router call, so a
        5xx with a non-JSON body (e.g. a broken gateway HTML page) would
        crash with an opaque JSONDecodeError instead of a clean
        httpx.HTTPStatusError.
        """
        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(
                500, content=b"<html>Bad Gateway</html>"
            )
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get_resource_by_path(
                    "/about-us", raise_for_status=True
                )

    @respx.mock
    def test_raise_for_status_false_router_5xx_does_not_raise_early(
        self,
    ) -> None:
        # With raise_for_status left at its default (False), behavior for
        # a router-side 5xx with a *valid* JSON body is unchanged: it's
        # parsed like any other non-resolved response.
        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(500, json=UNRESOLVED_ROUTER_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(ResourceNotFoundError):
                client.get_resource_by_path("/about-us")

    @respx.mock
    def test_forwards_options_to_get_resource(self) -> None:
        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_ROUTER_BODY)
        )
        respx.get(url__regex=r".*article/abc-123.*").mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_resource_by_path(
                "/about-us", query_string="fields[node--article]=title"
            )
            assert result == RESOURCE_BODY

    @respx.mock
    def test_raw_response(self) -> None:
        respx.get(ROUTER_URL, params={"path": "/about-us"}).mock(
            return_value=httpx.Response(200, json=RESOLVED_ROUTER_BODY)
        )
        respx.get(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=RESOURCE_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.get_resource_by_path("/about-us", raw_response=True)
            assert isinstance(result, RawJsonApiResponse)

    def test_uses_injected_http_client_for_router_lookup(self) -> None:
        """Regression test for the router silently building its own
        default httpx.Client instead of reusing the one passed to
        JsonApiClient (see CHANGELOG). Both the translate-path lookup
        (via client.router) and the follow-up resource fetch must go
        through the same injected MockTransport - not real transport.
        """
        requested_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            if "router/translate-path" in str(request.url):
                return httpx.Response(200, json=RESOLVED_ROUTER_BODY)
            return httpx.Response(200, json=RESOURCE_BODY)

        custom = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            with JsonApiClient(
                "https://example.com", http_client=custom
            ) as client:
                result = client.get_resource_by_path("/about-us")
        finally:
            custom.close()

        assert result == RESOURCE_BODY
        assert len(requested_urls) == 2
        assert any("router/translate-path" in url for url in requested_urls)
        assert any("article/abc-123" in url for url in requested_urls)


# -- index_lookup -----------------------------------------------------------


class TestIndexLookup:
    @respx.mock
    def test_no_index_fetch_when_disabled(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            client.get_collection("node--article")
            assert index_route.call_count == 0

    @respx.mock
    def test_first_read_fetches_index(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        resource_route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.get_collection("node--article")
            assert index_route.call_count == 1
            assert resource_route.call_count == 1

    @respx.mock
    def test_second_read_uses_cached_index(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        resource_route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.get_collection("node--article")
            client.get_collection("node--article")
            # Index fetched only once
            assert index_route.call_count == 1
            # Resource fetched twice (no response cache configured)
            assert resource_route.call_count == 2

    @respx.mock
    def test_index_failure_raises(self) -> None:
        respx.get(INDEX_URL).mock(
            return_value=httpx.Response(500, json={"error": "oops"})
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get_collection("node--article")


# -- index_lookup per locale -------------------------------------------------


class TestIndexLookupPerLocale:
    """Regression tests: the index cache is keyed per locale, since the
    JSON:API index can differ per language (see CHANGELOG)."""

    ES_INDEX_URL = "https://example.com/es/jsonapi"
    ES_CUSTOM_COLLECTION_URL = (
        "https://example.com/es/custom-endpoint/node/article"
    )
    ES_INDEX_BODY: ClassVar[dict] = {
        "jsonapi": {"version": "1.0", "meta": {}},
        "data": [],
        "meta": {},
        "links": {
            "node--article": {"href": ES_CUSTOM_COLLECTION_URL},
        },
    }

    @respx.mock
    def test_each_locale_fetches_its_own_index(self) -> None:
        default_index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        es_index_route = respx.get(self.ES_INDEX_URL).mock(
            return_value=httpx.Response(200, json=self.ES_INDEX_BODY)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        respx.get(self.ES_CUSTOM_COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            # Default (no locale) first.
            client.get_collection("node--article")
            # A different locale must NOT reuse the default locale's
            # cached index.
            client.get_collection("node--article", locale="es")

        assert default_index_route.call_count == 1
        assert es_index_route.call_count == 1

    @respx.mock
    def test_es_locale_uses_es_index_endpoint(self) -> None:
        respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        respx.get(self.ES_INDEX_URL).mock(
            return_value=httpx.Response(200, json=self.ES_INDEX_BODY)
        )
        es_custom_route = respx.get(self.ES_CUSTOM_COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        default_collection_route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.get_collection("node--article", locale="es")

        assert es_custom_route.call_count == 1
        assert default_collection_route.call_count == 0

    @respx.mock
    def test_second_read_same_locale_uses_cached_index(self) -> None:
        es_index_route = respx.get(self.ES_INDEX_URL).mock(
            return_value=httpx.Response(200, json=self.ES_INDEX_BODY)
        )
        respx.get(self.ES_CUSTOM_COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.get_collection("node--article", locale="es")
            client.get_collection("node--article", locale="es")

        assert es_index_route.call_count == 1


# -- _process_api_response 204 handling -------------------------------------


class TestProcessApiResponse204:
    def test_204_returns_empty_dict(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 204
        with JsonApiClient("https://example.com") as client:
            result = client._process_api_response(response)
            assert result == {}
            # .json() should NOT have been called
            response.json.assert_not_called()


# -- index_lookup: the index goes through the injected cache ----------------


class TestIndexUsesInjectedCache:
    """The JSON:API index must be stored in the user-supplied cache under the
    same key the JS client uses (`{locale/}{api_prefix}`), not only in a
    private per-instance dict. Otherwise it can never be invalidated and is
    refetched once per process even with a shared/persistent cache.
    """

    @respx.mock
    def test_index_is_written_to_injected_cache(self) -> None:
        respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient(
            "https://example.com", index_lookup=True, cache=cache
        ) as client:
            client.get_collection("node--article")

        # JS key for the default prefix and no locale is exactly "jsonapi".
        assert cache.get("jsonapi") == INDEX_BODY

    @respx.mock
    def test_index_is_read_from_injected_cache(self) -> None:
        """A warm cache means no index HTTP request at all - which is what
        makes the index reusable across processes."""
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        cache.set("jsonapi", INDEX_BODY)

        with JsonApiClient(
            "https://example.com", index_lookup=True, cache=cache
        ) as client:
            client.get_collection("node--article")

        assert index_route.call_count == 0

    @respx.mock
    def test_locale_index_uses_locale_scoped_key(self) -> None:
        # A real locale index returns locale-scoped hrefs; the client follows
        # them rather than rebuilding the URL itself.
        es_index = {
            **INDEX_BODY,
            "links": {
                "node--article": {
                    "href": "https://example.com/es/jsonapi/node/article"
                }
            },
        }
        respx.get("https://example.com/es/jsonapi").mock(
            return_value=httpx.Response(200, json=es_index)
        )
        respx.get("https://example.com/es/jsonapi/node/article").mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        cache = InMemoryCache()
        with JsonApiClient(
            "https://example.com", index_lookup=True, cache=cache
        ) as client:
            client.get_collection("node--article", locale="es")

        # Locale-scoped key, matching JS's `{locale}/{apiPrefix}`.
        assert cache.get("es/jsonapi") == es_index
        assert cache.get("jsonapi") is None

    @respx.mock
    def test_no_cache_injected_still_fetches_index_once(self) -> None:
        """With no cache the in-instance memo still applies, so we don't
        regress into JS's refetch-per-URL-build behavior."""
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json=COLLECTION_BODY)
        )
        with JsonApiClient("https://example.com", index_lookup=True) as client:
            client.get_collection("node--article", disable_cache=True)
            client.get_collection("node--article", disable_cache=True)

        assert index_route.call_count == 1
