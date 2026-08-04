"""Tests for the async clients (AsyncApiClient and the three subclasses).

respx intercepts httpx.AsyncClient transparently, so these mirror the sync
tests. asyncio_mode = "auto" (pyproject) lets async test functions run without
per-test markers.
"""

from __future__ import annotations

import json as json_module

import httpx
import pytest
import respx

from drupal_api_client import (
    AsyncApiClient,
    AsyncDecoupledRouterClient,
    AsyncGraphqlClient,
    AsyncJsonApiClient,
    BasicAuth,
    DefaultSerializer,
    InMemoryCache,
    RawJsonApiResponse,
    Resource,
    ResolvedPath,
    ResourceNotFoundError,
    UnresolvedPath,
)

BASE_URL = "https://example.com"


# -- AsyncApiClient base ----------------------------------------------------


class TestAsyncApiClientBase:
    async def test_async_context_manager_closes_client(self) -> None:
        async with AsyncApiClient(BASE_URL) as client:
            assert isinstance(client._http_client, httpx.AsyncClient)
            inner = client._http_client
        assert inner.is_closed

    def test_sync_context_manager_rejected(self) -> None:
        client = AsyncApiClient(BASE_URL)
        with pytest.raises(TypeError):
            with client:
                pass

    @respx.mock
    async def test_fetch_applies_basic_auth(self) -> None:
        route = respx.get(f"{BASE_URL}/x").mock(
            return_value=httpx.Response(200, json={})
        )
        async with AsyncApiClient(
            BASE_URL, authentication=BasicAuth(username="u", password="p")
        ) as client:
            await client.fetch(f"{BASE_URL}/x")
        assert route.calls.last.request.headers["Authorization"].startswith("Basic ")

    @respx.mock
    async def test_fetch_disable_auth(self) -> None:
        route = respx.get(f"{BASE_URL}/x").mock(
            return_value=httpx.Response(200, json={})
        )
        async with AsyncApiClient(
            BASE_URL, authentication=BasicAuth(username="u", password="p")
        ) as client:
            await client.fetch(f"{BASE_URL}/x", disable_authentication=True)
        assert "Authorization" not in route.calls.last.request.headers

    @respx.mock
    async def test_oauth_token_fetched_and_reused(self) -> None:
        from drupal_api_client import OAuthAuth

        token_route = respx.post(f"{BASE_URL}/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "abc",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )
        respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))
        async with AsyncApiClient(
            BASE_URL,
            authentication=OAuthAuth(client_id="id", client_secret="secret"),
        ) as client:
            headers1 = await client.add_authorization_header()
            headers2 = await client.add_authorization_header()
        assert headers1["Authorization"] == "Bearer abc"
        assert headers2["Authorization"] == "Bearer abc"
        # Token fetched once, then reused.
        assert token_route.call_count == 1


# -- AsyncJsonApiClient reads ----------------------------------------------


class TestAsyncJsonApiReads:
    async def test_default_api_prefix_and_router_type(self) -> None:
        async with AsyncJsonApiClient(BASE_URL) as client:
            assert client.api_prefix == "jsonapi"
            assert isinstance(client.router, AsyncDecoupledRouterClient)

    @respx.mock
    async def test_get_collection_passthrough_identity(self, fixture) -> None:
        body = fixture("node-recipe.json")
        respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncJsonApiClient(BASE_URL) as client:
            result = await client.get_collection("node--recipe")
        assert result == body

    @respx.mock
    async def test_get_collection_uses_cache(self, fixture) -> None:
        body = fixture("node-recipe.json")
        route = respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncJsonApiClient(BASE_URL, cache=InMemoryCache()) as client:
            await client.get_collection("node--recipe")
            await client.get_collection("node--recipe")
        # Second read served from cache — only one HTTP call.
        assert route.call_count == 1

    @respx.mock
    async def test_get_resource_with_default_serializer(self, fixture) -> None:
        body = fixture("node-recipe-en-single-resource.json")
        uuid = body["data"]["id"]
        respx.get(f"{BASE_URL}/jsonapi/node/recipe/{uuid}").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncJsonApiClient(
            BASE_URL, serializer=DefaultSerializer()
        ) as client:
            result = await client.get_resource("node--recipe", uuid)
        assert isinstance(result, Resource)
        assert result["id"] == uuid
        assert "attributes" not in result

    @respx.mock
    async def test_get_view_raw_response(self, fixture) -> None:
        body = fixture("views-article-page-1--default.json")
        respx.get(f"{BASE_URL}/jsonapi/views/articles/page_1").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncJsonApiClient(BASE_URL) as client:
            result = await client.get_view("articles", "page_1", raw_response=True)
        assert isinstance(result, RawJsonApiResponse)
        assert result.json == body


# -- AsyncJsonApiClient path resolution + writes ---------------------------


class TestAsyncJsonApiPathAndWrites:
    @respx.mock
    async def test_get_resource_by_path_resolves(self, fixture) -> None:
        resolved = fixture("resolved-recipe.json")
        resource = fixture("node-recipe-en-single-resource.json")
        uuid = resolved["entity"]["uuid"]
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(200, json=resolved)
        )
        respx.get(f"{BASE_URL}/jsonapi/node/recipe/{uuid}").mock(
            return_value=httpx.Response(200, json=resource)
        )
        async with AsyncJsonApiClient(BASE_URL) as client:
            result = await client.get_resource_by_path("/recipes/deep-mediterranean")
        assert result == resource

    @respx.mock
    async def test_get_resource_by_path_unresolved_raises(self, fixture) -> None:
        body = fixture("unresolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(404, json=body)
        )
        async with AsyncJsonApiClient(BASE_URL) as client:
            with pytest.raises(ResourceNotFoundError):
                await client.get_resource_by_path("/nope")

    @respx.mock
    async def test_create_resource_invalidates_cache(self) -> None:
        collection_body = {"data": [{"type": "node--page", "id": "1"}]}
        respx.get(f"{BASE_URL}/jsonapi/node/page").mock(
            return_value=httpx.Response(200, json=collection_body)
        )
        respx.post(f"{BASE_URL}/jsonapi/node/page").mock(
            return_value=httpx.Response(201, json={"data": {"id": "new"}})
        )
        cache = InMemoryCache()
        async with AsyncJsonApiClient(BASE_URL, cache=cache) as client:
            await client.get_collection("node--page")  # populate cache
            assert cache.get("node--page") is not None
            await client.create_resource("node--page", {"data": {}})
            # Canonical collection key invalidated after successful create.
            assert cache.get("node--page") is None

    @respx.mock
    async def test_delete_resource_returns_none_on_204(self) -> None:
        respx.delete(f"{BASE_URL}/jsonapi/node/page/abc").mock(
            return_value=httpx.Response(204)
        )
        async with AsyncJsonApiClient(BASE_URL) as client:
            result = await client.delete_resource("node--page", "abc")
        assert result is None

    async def test_aclose_closes_both_clients(self) -> None:
        client = AsyncJsonApiClient(BASE_URL)
        inner = client._http_client
        router_inner = client.router._http_client
        await client.aclose()
        assert inner.is_closed
        assert router_inner.is_closed


# -- AsyncDecoupledRouterClient --------------------------------------------


class TestAsyncRouter:
    @respx.mock
    async def test_translate_path_resolved(self, fixture) -> None:
        body = fixture("resolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncDecoupledRouterClient(BASE_URL) as client:
            result = await client.translate_path("/recipes/x")
        assert isinstance(result, ResolvedPath)
        assert isinstance(result.resolved, str)

    @respx.mock
    async def test_translate_path_unresolved(self, fixture) -> None:
        body = fixture("unresolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(404, json=body)
        )
        async with AsyncDecoupledRouterClient(BASE_URL) as client:
            result = await client.translate_path("/nope")
        assert isinstance(result, UnresolvedPath)


# -- AsyncGraphqlClient -----------------------------------------------------


class TestAsyncGraphql:
    @respx.mock
    async def test_query_returns_body(self, fixture) -> None:
        body = fixture("get-articles.json")
        respx.post(f"{BASE_URL}/graphql").mock(
            return_value=httpx.Response(200, json=body)
        )
        async with AsyncGraphqlClient(BASE_URL) as client:
            result = await client.query("query { x }")
        assert result == body

    @respx.mock
    async def test_query_posts_envelope(self) -> None:
        route = respx.post(f"{BASE_URL}/graphql").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        async with AsyncGraphqlClient(BASE_URL) as client:
            await client.query("query { x }", variables={"a": 1})
        sent = json_module.loads(route.calls.last.request.content)
        assert sent == {"query": "query { x }", "variables": {"a": 1}}
