"""Tests for JsonApiClient foundations (step 3a)."""

import hashlib
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from drupal_api_client import (
    BasicAuth,
    InMemoryCache,
    JsonApiClient,
    PassthroughSerializer,
    RawJsonApiResponse,
)
from drupal_api_client.decoupled_router import DecoupledRouterClient


# -- constructor ------------------------------------------------------------


class TestConstructor:
    def test_default_api_prefix(self) -> None:
        with JsonApiClient("https://example.com") as client:
            assert client.api_prefix == "jsonapi"

    def test_custom_api_prefix(self) -> None:
        with JsonApiClient("https://example.com", api_prefix="custom-api") as client:
            assert client.api_prefix == "custom-api"

    def test_router_is_decoupled_router_client(self) -> None:
        with JsonApiClient("https://example.com") as client:
            assert isinstance(client.router, DecoupledRouterClient)

    def test_router_gets_decoupled_router_api_prefix(self) -> None:
        with JsonApiClient(
            "https://example.com",
            decoupled_router_api_prefix="custom-router",
        ) as client:
            assert client.router.api_prefix == "custom-router"

    def test_router_default_api_prefix(self) -> None:
        with JsonApiClient("https://example.com") as client:
            assert client.router.api_prefix == "router/translate-path"

    def test_auth_forwarded_to_router(self) -> None:
        auth = BasicAuth(username="u", password="p")
        with JsonApiClient("https://example.com", authentication=auth) as client:
            assert client.router.authentication is auth

    def test_cache_forwarded_to_router(self) -> None:
        cache = InMemoryCache()
        with JsonApiClient("https://example.com", cache=cache) as client:
            assert client.router.cache is cache

    def test_serializer_forwarded_to_router(self) -> None:
        serializer = PassthroughSerializer()
        with JsonApiClient(
            "https://example.com", serializer=serializer
        ) as client:
            assert client.router.serializer is serializer

    def test_index_lookup_defaults_false(self) -> None:
        with JsonApiClient("https://example.com") as client:
            assert client.index_lookup is False

    def test_index_cache_starts_none(self) -> None:
        with JsonApiClient("https://example.com") as client:
            assert client._index_cache is None

    def test_close_closes_both_clients(self) -> None:
        client = JsonApiClient("https://example.com")
        assert client._owns_client is True
        assert client.router._owns_client is True
        client.close()
        assert client._http_client.is_closed
        assert client.router._http_client.is_closed

    def test_context_manager_closes_both_clients(self) -> None:
        with JsonApiClient("https://example.com") as client:
            inner_http = client._http_client
            router_http = client.router._http_client
        assert inner_http.is_closed
        assert router_http.is_closed


# -- _get_entity_type_and_bundle -------------------------------------------


class TestEntityTypeAndBundle:
    def test_node_article(self) -> None:
        assert JsonApiClient._get_entity_type_and_bundle("node--article") == (
            "node",
            "article",
        )

    def test_taxonomy_term_tags(self) -> None:
        assert JsonApiClient._get_entity_type_and_bundle(
            "taxonomy_term--tags"
        ) == ("taxonomy_term", "tags")

    def test_no_separator_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid resource type"):
            JsonApiClient._get_entity_type_and_bundle("node")

    def test_empty_bundle_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid resource type"):
            JsonApiClient._get_entity_type_and_bundle("node--")

    def test_empty_entity_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid resource type"):
            JsonApiClient._get_entity_type_and_bundle("--article")


# -- create_url -------------------------------------------------------------


class TestCreateUrl:
    def test_collection_url(self) -> None:
        with JsonApiClient("https://example.com") as client:
            url = client.create_url(entity_type_id="node", bundle_id="article")
            assert url == "https://example.com/jsonapi/node/article"

    def test_single_resource_url(self) -> None:
        with JsonApiClient("https://example.com") as client:
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
                resource_id="abc-123",
            )
            assert url == "https://example.com/jsonapi/node/article/abc-123"

    def test_with_locale(self) -> None:
        with JsonApiClient("https://example.com") as client:
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
                locale_segment="es",
            )
            assert url == "https://example.com/es/jsonapi/node/article"

    def test_with_query_string(self) -> None:
        with JsonApiClient("https://example.com") as client:
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
                query_string="filter[title]=Hello",
            )
            assert (
                url
                == "https://example.com/jsonapi/node/article?filter[title]=Hello"
            )

    def test_with_drupal_jsonapi_params_stub(self) -> None:
        class StubParams:
            def get_query_string(self) -> str:
                return "filter[status]=1&sort=title"

        with JsonApiClient("https://example.com") as client:
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
                query_string=StubParams(),
            )
            assert (
                url
                == "https://example.com/jsonapi/node/article?filter[status]=1&sort=title"
            )

    def test_with_index_lookup_and_cached_endpoint(self) -> None:
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client._index_cache = {
                "node--article": {
                    "href": "https://example.com/jsonapi/node/article",
                },
            }
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
                resource_id="abc-123",
                query_string="fields[node--article]=title",
            )
            assert (
                url
                == "https://example.com/jsonapi/node/article/abc-123?fields[node--article]=title"
            )

    def test_index_lookup_fallback_when_cache_is_none(self) -> None:
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            # _index_cache is None by default — should fall through
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
            )
            assert url == "https://example.com/jsonapi/node/article"

    def test_index_lookup_fallback_when_type_not_in_cache(self) -> None:
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client._index_cache = {
                "node--page": {
                    "href": "https://example.com/jsonapi/node/page",
                },
            }
            url = client.create_url(
                entity_type_id="node",
                bundle_id="article",
            )
            assert url == "https://example.com/jsonapi/node/article"


# -- create_cache_key -------------------------------------------------------


class TestCreateCacheKey:
    def test_verbatim_cache_key(self) -> None:
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            cache_key="custom-key",
        )
        assert key == "custom-key"

    def test_simple_entity_bundle(self) -> None:
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
        )
        assert key == "node--article"

    def test_with_resource_id(self) -> None:
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            resource_id="abc-123",
        )
        assert key == "node--article--abc-123"

    def test_with_locale(self) -> None:
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            locale_segment="en",
        )
        assert key == "en--node--article"

    def test_with_query_string_sha256(self) -> None:
        qs = "filter[title]=Hello"
        expected_hash = hashlib.sha256(qs.encode()).hexdigest()
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            query_string=qs,
        )
        assert key == f"node--article--{expected_hash}"

    def test_full_key(self) -> None:
        qs = "filter[status]=1"
        expected_hash = hashlib.sha256(qs.encode()).hexdigest()
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            resource_id="abc-123",
            locale_segment="es",
            query_string=qs,
        )
        assert key == f"es--node--article--abc-123--{expected_hash}"

    def test_with_drupal_jsonapi_params_stub(self) -> None:
        class StubParams:
            def get_query_string(self) -> str:
                return "filter[status]=1&sort=title"

        qs_str = "filter[status]=1&sort=title"
        expected_hash = hashlib.sha256(qs_str.encode()).hexdigest()
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="article",
            query_string=StubParams(),
        )
        assert key == f"node--article--{expected_hash}"


# -- _process_api_response -------------------------------------------------


class TestProcessApiResponse:
    @respx.mock
    def test_passthrough_returns_dict(self) -> None:
        body = {"data": [{"id": "1", "type": "node--article"}]}
        respx.get("https://example.com/jsonapi/node/article").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient("https://example.com") as client:
            response = client.fetch("https://example.com/jsonapi/node/article")
            result = client._process_api_response(response)
            assert result == body

    @respx.mock
    def test_custom_serializer_called(self) -> None:
        body = {"data": [{"id": "1", "type": "node--article"}]}
        respx.get("https://example.com/jsonapi/node/article").mock(
            return_value=httpx.Response(200, json=body)
        )
        serializer = MagicMock()
        serializer.deserialize.return_value = {"transformed": True}
        with JsonApiClient(
            "https://example.com", serializer=serializer
        ) as client:
            response = client.fetch("https://example.com/jsonapi/node/article")
            result = client._process_api_response(response)
            serializer.deserialize.assert_called_once_with(body)
            assert result == {"transformed": True}


# -- RawJsonApiResponse dataclass ------------------------------------------


class TestRawJsonApiResponse:
    def test_frozen(self) -> None:
        resp = RawJsonApiResponse(
            response=httpx.Response(200),
            json={"data": []},
        )
        with pytest.raises(AttributeError):
            resp.json = {}  # type: ignore[misc]
