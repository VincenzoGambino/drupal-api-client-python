"""Tests for JsonApiClient write operations (step 3c)."""

import httpx
import pytest
import respx

from drupal_api_client import (
    InMemoryCache,
    JsonApiClient,
    RawJsonApiResponse,
)

COLLECTION_URL = "https://example.com/jsonapi/node/article"
RESOURCE_URL = "https://example.com/jsonapi/node/article/abc-123"

CREATE_BODY: dict = {
    "data": {
        "type": "node--article",
        "attributes": {"title": "New Article"},
    }
}

CREATED_RESPONSE: dict = {
    "data": {
        "type": "node--article",
        "id": "new-uuid",
        "attributes": {"title": "New Article"},
    }
}

UPDATE_BODY: dict = {
    "data": {
        "type": "node--article",
        "id": "abc-123",
        "attributes": {"title": "Updated Article"},
    }
}

UPDATED_RESPONSE: dict = {
    "data": {
        "type": "node--article",
        "id": "abc-123",
        "attributes": {"title": "Updated Article"},
    }
}

ERROR_RESPONSE: dict = {
    "errors": [{"detail": "Title required", "status": "422"}]
}

INDEX_URL = "https://example.com/jsonapi"
CUSTOM_COLLECTION_URL = "https://example.com/custom-endpoint/node/article"
CUSTOM_RESOURCE_URL = "https://example.com/custom-endpoint/node/article/abc-123"

INDEX_BODY: dict = {
    "jsonapi": {"version": "1.0", "meta": {}},
    "data": [],
    "meta": {},
    "links": {
        "node--article": {"href": CUSTOM_COLLECTION_URL},
    },
}


# -- create_resource --------------------------------------------------------


class TestCreateResource:
    @respx.mock
    def test_posts_to_collection_url(self) -> None:
        route = respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.create_resource("node--article", CREATE_BODY)
            assert result == CREATED_RESPONSE
            assert route.call_count == 1

    @respx.mock
    def test_content_type_header(self) -> None:
        route = respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            client.create_resource("node--article", CREATE_BODY)
            request = route.calls[0].request
            assert request.headers["content-type"] == "application/vnd.api+json"

    @respx.mock
    def test_returns_parsed_response(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.create_resource("node--article", CREATE_BODY)
            assert result["data"]["id"] == "new-uuid"

    @respx.mock
    def test_raises_on_4xx_by_default(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(422, json=ERROR_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.create_resource("node--article", CREATE_BODY)

    @respx.mock
    def test_returns_error_body_when_raise_disabled(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(422, json=ERROR_RESPONSE)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        with JsonApiClient("https://example.com", cache=cache) as client:
            result = client.create_resource(
                "node--article", CREATE_BODY, raise_for_status=False
            )
            assert "errors" in result
            # Cache NOT invalidated on error
            assert cache.get("node--article") is not None

    @respx.mock
    def test_raw_response(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.create_resource(
                "node--article", CREATE_BODY, raw_response=True
            )
            assert isinstance(result, RawJsonApiResponse)
            assert result.response.status_code == 201
            assert result.json == CREATED_RESPONSE

    @respx.mock
    def test_cache_invalidation(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.create_resource("node--article", CREATE_BODY)
            assert cache.get("node--article") is None

    @respx.mock
    def test_disable_authentication(self) -> None:
        from drupal_api_client import BasicAuth

        route = respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient(
            "https://example.com",
            authentication=BasicAuth(username="u", password="p"),
        ) as client:
            client.create_resource(
                "node--article", CREATE_BODY, disable_authentication=True
            )
            request = route.calls[0].request
            assert "authorization" not in request.headers


# -- update_resource --------------------------------------------------------


class TestUpdateResource:
    @respx.mock
    def test_patches_to_resource_url(self) -> None:
        route = respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.update_resource(
                "node--article", "abc-123", UPDATE_BODY
            )
            assert result == UPDATED_RESPONSE
            assert route.call_count == 1

    @respx.mock
    def test_content_type_header(self) -> None:
        route = respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            client.update_resource("node--article", "abc-123", UPDATE_BODY)
            request = route.calls[0].request
            assert request.headers["content-type"] == "application/vnd.api+json"

    @respx.mock
    def test_returns_parsed_response(self) -> None:
        respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.update_resource(
                "node--article", "abc-123", UPDATE_BODY
            )
            assert result["data"]["attributes"]["title"] == "Updated Article"

    @respx.mock
    def test_cache_invalidation_both_keys(self) -> None:
        respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        cache.set("node--article--abc-123", {"data": {}})
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.update_resource("node--article", "abc-123", UPDATE_BODY)
            assert cache.get("node--article") is None
            assert cache.get("node--article--abc-123") is None

    @respx.mock
    def test_raises_on_4xx_by_default(self) -> None:
        respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(422, json=ERROR_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.update_resource(
                    "node--article", "abc-123", UPDATE_BODY
                )

    @respx.mock
    def test_returns_error_body_when_raise_disabled(self) -> None:
        respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(422, json=ERROR_RESPONSE)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        with JsonApiClient("https://example.com", cache=cache) as client:
            result = client.update_resource(
                "node--article", "abc-123", UPDATE_BODY, raise_for_status=False
            )
            assert "errors" in result
            assert cache.get("node--article") is not None

    @respx.mock
    def test_raw_response(self) -> None:
        respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.update_resource(
                "node--article", "abc-123", UPDATE_BODY, raw_response=True
            )
            assert isinstance(result, RawJsonApiResponse)
            assert result.json == UPDATED_RESPONSE


# -- delete_resource --------------------------------------------------------


class TestDeleteResource:
    @respx.mock
    def test_deletes_resource_url(self) -> None:
        route = respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.delete_resource("node--article", "abc-123")
            assert result is None
            assert route.call_count == 1

    @respx.mock
    def test_returns_none_by_default(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.delete_resource("node--article", "abc-123")
            assert result is None

    @respx.mock
    def test_raw_response_204(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.delete_resource(
                "node--article", "abc-123", raw_response=True
            )
            assert isinstance(result, RawJsonApiResponse)
            assert result.response.status_code == 204
            assert result.json == {}

    @respx.mock
    def test_raw_response_200_with_body(self) -> None:
        body = {"meta": {"message": "Deleted"}}
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient("https://example.com") as client:
            result = client.delete_resource(
                "node--article", "abc-123", raw_response=True
            )
            assert isinstance(result, RawJsonApiResponse)
            assert result.json == body

    @respx.mock
    def test_cache_invalidation_both_keys(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        cache.set("node--article--abc-123", {"data": {}})
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.delete_resource("node--article", "abc-123")
            assert cache.get("node--article") is None
            assert cache.get("node--article--abc-123") is None

    @respx.mock
    def test_raises_on_4xx_by_default(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(403, json=ERROR_RESPONSE)
        )
        with JsonApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.delete_resource("node--article", "abc-123")

    @respx.mock
    def test_no_cache_invalidation_on_error(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(403, json=ERROR_RESPONSE)
        )
        cache = InMemoryCache()
        cache.set("node--article", {"data": []})
        cache.set("node--article--abc-123", {"data": {}})
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.delete_resource(
                "node--article", "abc-123", raise_for_status=False
            )
            assert cache.get("node--article") is not None
            assert cache.get("node--article--abc-123") is not None


# -- index_lookup on writes --------------------------------------------------


class TestIndexLookupOnWrites:
    """Regression tests: write methods must honor index_lookup even when
    no prior read has warmed the index cache (see CHANGELOG)."""

    @respx.mock
    def test_create_resource_uses_index_endpoint(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        custom_route = respx.post(CUSTOM_COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        standard_route = respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json=CREATED_RESPONSE)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            # No prior get_collection()/get_resource() call.
            client.create_resource("node--article", CREATE_BODY)
        assert index_route.call_count == 1
        assert custom_route.call_count == 1
        assert standard_route.call_count == 0

    @respx.mock
    def test_update_resource_uses_index_endpoint(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        custom_route = respx.patch(CUSTOM_RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        standard_route = respx.patch(RESOURCE_URL).mock(
            return_value=httpx.Response(200, json=UPDATED_RESPONSE)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.update_resource("node--article", "abc-123", UPDATE_BODY)
        assert index_route.call_count == 1
        assert custom_route.call_count == 1
        assert standard_route.call_count == 0

    @respx.mock
    def test_delete_resource_uses_index_endpoint(self) -> None:
        index_route = respx.get(INDEX_URL).mock(
            return_value=httpx.Response(200, json=INDEX_BODY)
        )
        custom_route = respx.delete(CUSTOM_RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        standard_route = respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        with JsonApiClient(
            "https://example.com", index_lookup=True
        ) as client:
            client.delete_resource("node--article", "abc-123")
        assert index_route.call_count == 1
        assert custom_route.call_count == 1
        assert standard_route.call_count == 0


# -- _invalidate_cache ------------------------------------------------------


class TestCacheInvalidation:
    def test_no_op_when_no_cache(self) -> None:
        with JsonApiClient("https://example.com") as client:
            # Should not raise
            client._invalidate_cache(
                resource_type="node--article", resource_id="abc-123"
            )

    @respx.mock
    def test_only_canonical_key_dropped(self) -> None:
        respx.delete(RESOURCE_URL).mock(
            return_value=httpx.Response(204)
        )
        cache = InMemoryCache()
        # Canonical keys
        cache.set("node--article", {"data": []})
        cache.set("node--article--abc-123", {"data": {}})
        # Locale-keyed entry
        cache.set("es--node--article", {"data": []})
        with JsonApiClient("https://example.com", cache=cache) as client:
            client.delete_resource("node--article", "abc-123")
            # Canonical entries dropped
            assert cache.get("node--article") is None
            assert cache.get("node--article--abc-123") is None
            # Locale entry remains
            assert cache.get("es--node--article") is not None

    @respx.mock
    def test_custom_cache_key_is_invalidated(self) -> None:
        """A caller who read under a custom cache_key can invalidate it by
        passing that key to the write - otherwise the entry stays stale
        forever, because _invalidate_cache only computes canonical keys.
        """
        respx.delete(RESOURCE_URL).mock(return_value=httpx.Response(204))
        cache = InMemoryCache()
        cache.set("my-custom-articles", {"data": []})
        cache.set("node--article", {"data": []})

        with JsonApiClient("https://example.com", cache=cache) as client:
            client.delete_resource(
                "node--article", "abc-123", cache_key="my-custom-articles"
            )

        # The custom key is dropped...
        assert cache.get("my-custom-articles") is None
        # ...*in addition to* the canonical ones, not instead of them:
        # other callers may have cached under the default key.
        assert cache.get("node--article") is None

    @respx.mock
    def test_custom_cache_key_survives_when_not_passed(self) -> None:
        """Regression guard: without cache_key, a custom-keyed entry is
        untouched. This documents the footgun the option exists to fix.
        """
        respx.delete(RESOURCE_URL).mock(return_value=httpx.Response(204))
        cache = InMemoryCache()
        cache.set("my-custom-articles", {"data": []})

        with JsonApiClient("https://example.com", cache=cache) as client:
            client.delete_resource("node--article", "abc-123")

        assert cache.get("my-custom-articles") is not None

    @respx.mock
    def test_create_invalidates_custom_cache_key(self) -> None:
        respx.post(COLLECTION_URL).mock(
            return_value=httpx.Response(201, json={"data": {"id": "new"}})
        )
        cache = InMemoryCache()
        cache.set("my-custom-articles", {"data": []})

        with JsonApiClient("https://example.com", cache=cache) as client:
            client.create_resource(
                "node--article",
                {"data": {"type": "node--article"}},
                cache_key="my-custom-articles",
            )

        assert cache.get("my-custom-articles") is None
