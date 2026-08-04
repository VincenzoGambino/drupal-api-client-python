"""Tests for GraphqlClient."""

from __future__ import annotations

import json as json_module

import httpx
import pytest
import respx

from drupal_api_client import BasicAuth, GraphqlClient

BASE_URL = "https://example.com"
GRAPHQL_URL = "https://example.com/graphql"

ARTICLES_QUERY = """query GetArticles {
  nodeArticles(first: 10) { nodes { title } }
}"""


class TestConstructor:
    def test_default_api_prefix(self) -> None:
        with GraphqlClient(BASE_URL) as client:
            assert client.api_prefix == "graphql"

    def test_custom_api_prefix(self) -> None:
        with GraphqlClient(BASE_URL, api_prefix="custom-graphql") as client:
            assert client.api_prefix == "custom-graphql"


class TestQuery:
    @respx.mock
    def test_query_returns_parsed_body(self, fixture) -> None:
        body = fixture("get-articles.json")
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GraphqlClient(BASE_URL) as client:
            result = client.query(ARTICLES_QUERY)
        assert result == body
        assert result["data"]["nodeArticles"]["nodes"][0]["title"]

    @respx.mock
    def test_query_posts_query_envelope(self) -> None:
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        with GraphqlClient(BASE_URL) as client:
            client.query(ARTICLES_QUERY)
        request = route.calls.last.request
        assert request.method == "POST"
        sent = json_module.loads(request.content)
        # Byte-identical to JS: body is exactly {"query": ...} with no variables.
        assert sent == {"query": ARTICLES_QUERY}

    @respx.mock
    def test_query_includes_variables_when_provided(self) -> None:
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        with GraphqlClient(BASE_URL) as client:
            client.query(ARTICLES_QUERY, variables={"first": 5})
        sent = json_module.loads(route.calls.last.request.content)
        assert sent == {"query": ARTICLES_QUERY, "variables": {"first": 5}}

    @respx.mock
    def test_query_applies_authentication(self) -> None:
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        with GraphqlClient(
            BASE_URL, authentication=BasicAuth(username="u", password="p")
        ) as client:
            client.query(ARTICLES_QUERY)
        assert route.calls.last.request.headers["Authorization"].startswith("Basic ")

    @respx.mock
    def test_query_disable_authentication(self) -> None:
        route = respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        with GraphqlClient(
            BASE_URL, authentication=BasicAuth(username="u", password="p")
        ) as client:
            client.query(ARTICLES_QUERY, disable_authentication=True)
        assert "Authorization" not in route.calls.last.request.headers

    @respx.mock
    def test_query_raises_for_status_on_error(self) -> None:
        respx.post(GRAPHQL_URL).mock(
            return_value=httpx.Response(500, json={"errors": []})
        )
        with GraphqlClient(BASE_URL) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.query(ARTICLES_QUERY, raise_for_status=True)

    @respx.mock
    def test_query_returns_errors_body_without_inspecting(self) -> None:
        # GraphQL query-level errors come back as HTTP 200 with an `errors`
        # array; like JS, we return it raw rather than raising.
        body = {"data": None, "errors": [{"message": "boom"}]}
        respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=body))
        with GraphqlClient(BASE_URL) as client:
            result = client.query(ARTICLES_QUERY)
        assert result == body
