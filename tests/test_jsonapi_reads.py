"""Tests for JsonApiClient read operations (step 3b)."""

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
    },
}

UNRESOLVED_ROUTER_BODY: dict = {
    "resolved": False,
    "message": "Unable to resolve path /nonexistent.",
    "details": {},
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
    def test_raises_on_unresolved(self) -> None:
        respx.get(ROUTER_URL, params={"path": "/nonexistent"}).mock(
            return_value=httpx.Response(404, json=UNRESOLVED_ROUTER_BODY)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(ResourceNotFoundError, match="could not be resolved"):
                client.get_resource_by_path("/nonexistent")

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
