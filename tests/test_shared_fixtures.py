"""Parity tests against the shared JS golden fixtures.

Each test feeds a byte-identical JS golden payload (``tests/fixtures/``, copied
from the JS source-of-truth corpus) as the mocked server response and asserts the
Python client handles it the same way the JS client is documented to. This is the
cross-language equivalence net: if a real Drupal response shape (captured once in
the JS fixtures) breaks the Python client, it fails here.

See ``tests/fixtures/README.md`` for provenance.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from drupal_api_client import (
    JsonApiClient,
    RawJsonApiResponse,
    ResolvedPath,
    ResourceNotFoundError,
    UnresolvedPath,
)

BASE_URL = "https://example.com"


# -- reads: passthrough returns the golden payload unchanged ----------------


class TestReadPassthroughIdentity:
    @respx.mock
    def test_collection_passthrough_identity(self, fixture) -> None:
        body = fixture("node-recipe.json")
        respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_collection("node--recipe")
        # Passthrough serializer must return the golden document verbatim.
        assert result == body
        assert isinstance(result["data"], list)

    @respx.mock
    def test_single_resource_passthrough_identity(self, fixture) -> None:
        body = fixture("node-recipe-en-single-resource.json")
        uuid = body["data"]["id"]
        respx.get(f"{BASE_URL}/jsonapi/node/recipe/{uuid}").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_resource("node--recipe", uuid)
        assert result == body
        assert isinstance(result["data"], dict)

    @respx.mock
    def test_view_passthrough_identity(self, fixture) -> None:
        body = fixture("views-article-page-1--default.json")
        respx.get(f"{BASE_URL}/jsonapi/views/articles/page_1").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_view("articles", "page_1")
        assert result == body


# -- router: resolved / unresolved classification --------------------------


class TestRouterClassification:
    @respx.mock
    def test_resolved_recipe_is_resolved_and_resolved_is_a_url_string(
        self, fixture
    ) -> None:
        # Guards the parity trap: `resolved` is the canonical URL string,
        # not a boolean (see the 0.3.0 "Fixed (breaking)" notes in
        # CHANGELOG.md).
        body = fixture("resolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.router.translate_path("/recipes/deep-mediterranean")
        assert isinstance(result, ResolvedPath)
        assert isinstance(result.resolved, str)
        assert result.resolved.startswith("http")
        assert result.entity["uuid"] == body["entity"]["uuid"]

    @respx.mock
    def test_unresolved_recipe_is_unresolved(self, fixture) -> None:
        body = fixture("unresolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(404, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.router.translate_path("/nope")
        assert isinstance(result, UnresolvedPath)


# -- get_resource_by_path: end-to-end resolve + fetch ----------------------


class TestGetResourceByPath:
    @respx.mock
    def test_resolved_path_fetches_underlying_resource(self, fixture) -> None:
        resolved = fixture("resolved-recipe.json")
        resource = fixture("node-recipe-en-single-resource.json")
        uuid = resolved["entity"]["uuid"]  # node / recipe / <uuid>

        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(200, json=resolved)
        )
        respx.get(f"{BASE_URL}/jsonapi/node/recipe/{uuid}").mock(
            return_value=httpx.Response(200, json=resource)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_resource_by_path("/recipes/deep-mediterranean")
        assert result == resource

    @respx.mock
    def test_unresolved_path_raises_resource_not_found(self, fixture) -> None:
        # Documented Python divergence (D3): unresolved paths raise rather
        # than returning the payload.
        body = fixture("unresolved-recipe.json")
        respx.get(f"{BASE_URL}/router/translate-path").mock(
            return_value=httpx.Response(404, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            with pytest.raises(ResourceNotFoundError):
                client.get_resource_by_path("/nope")


# -- error body fixture ------------------------------------------------------


class TestErrorFixture:
    @respx.mock
    def test_404_body_raises_when_raise_for_status(self, fixture) -> None:
        body = fixture("404.json")
        respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(404, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.get_collection("node--recipe", raise_for_status=True)

    @respx.mock
    def test_404_body_returned_by_default(self, fixture) -> None:
        body = fixture("404.json")
        respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(404, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_collection("node--recipe")
        assert result == body


# -- raw response wrapper carries the golden payload ------------------------


class TestRawResponse:
    @respx.mock
    def test_raw_response_wraps_golden_payload(self, fixture) -> None:
        body = fixture("node-recipe.json")
        respx.get(f"{BASE_URL}/jsonapi/node/recipe").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(BASE_URL) as client:
            result = client.get_collection("node--recipe", raw_response=True)
        assert isinstance(result, RawJsonApiResponse)
        assert result.json == body
        assert result.response.status_code == 200
