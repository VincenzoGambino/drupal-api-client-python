"""Tests for DefaultSerializer (schema-less JSON:API flattening)."""

from __future__ import annotations

import json

import httpx
import respx

from drupal_api_client import (
    DefaultSerializer,
    JsonApiClient,
    Resource,
    ResourceCollection,
)


class TestPassthroughFallback:
    def test_none_passthrough(self) -> None:
        assert DefaultSerializer().deserialize(None) is None

    def test_non_dict_passthrough(self) -> None:
        assert DefaultSerializer().deserialize(42) == 42

    def test_no_data_key_passthrough(self) -> None:
        body = {"jsonapi": {"version": "1.0"}}
        assert DefaultSerializer().deserialize(body) == body

    def test_null_data_returns_none(self) -> None:
        assert DefaultSerializer().deserialize({"data": None}) is None

    def test_accepts_json_string_body(self) -> None:
        body = json.dumps(
            {"data": {"type": "node--article", "id": "1", "attributes": {"title": "T"}}}
        )
        result = DefaultSerializer().deserialize(body)
        assert result["title"] == "T"

    def test_invalid_json_string_passthrough(self) -> None:
        assert DefaultSerializer().deserialize("not json {") == "not json {"


class TestSingleResource:
    def test_flattens_type_id_and_attributes(self) -> None:
        body = {
            "data": {
                "type": "node--article",
                "id": "abc",
                "attributes": {"title": "Hello", "status": True},
            }
        }
        result = DefaultSerializer().deserialize(body)
        assert isinstance(result, Resource)
        assert result["type"] == "node--article"
        assert result["id"] == "abc"
        assert result["title"] == "Hello"
        assert result["status"] is True
        # No `attributes` wrapper survives.
        assert "attributes" not in result


class TestMetaAndLinks:
    def test_get_meta_and_get_links(self) -> None:
        body = {
            "data": {"type": "node--article", "id": "1", "attributes": {}},
            "meta": {"count": 5},
            "links": {"self": {"href": "https://x/self"}},
        }
        result = DefaultSerializer().deserialize(body)
        assert result.get_meta() == {"count": 5}
        assert result.get_links() == {"self": {"href": "https://x/self"}}

    def test_absent_meta_links_are_none(self) -> None:
        result = DefaultSerializer().deserialize(
            {"data": {"type": "n--a", "id": "1", "attributes": {}}}
        )
        assert result.get_meta() is None
        assert result.get_links() is None

    def test_meta_links_not_in_data_keys(self) -> None:
        body = {
            "data": {"type": "n--a", "id": "1", "attributes": {"title": "T"}},
            "meta": {"count": 1},
            "links": {"self": "x"},
        }
        result = DefaultSerializer().deserialize(body)
        # Accessors must not leak into the data (mirrors JS non-enumerable).
        assert set(result.keys()) == {"type", "id", "title"}
        assert dict(result) == {"type": "n--a", "id": "1", "title": "T"}


class TestCollection:
    def test_flattens_list_with_accessors(self) -> None:
        body = {
            "data": [
                {"type": "n--a", "id": "1", "attributes": {"title": "One"}},
                {"type": "n--a", "id": "2", "attributes": {"title": "Two"}},
            ],
            "meta": {"count": 2},
        }
        result = DefaultSerializer().deserialize(body)
        assert isinstance(result, ResourceCollection)
        assert [r["title"] for r in result] == ["One", "Two"]
        assert result.get_meta() == {"count": 2}


class TestRelationships:
    def test_inlines_single_relationship_from_included(self) -> None:
        body = {
            "data": {
                "type": "node--article",
                "id": "1",
                "attributes": {"title": "Post"},
                "relationships": {
                    "author": {"data": {"type": "user--user", "id": "u1"}}
                },
            },
            "included": [
                {"type": "user--user", "id": "u1", "attributes": {"name": "Ada"}}
            ],
        }
        result = DefaultSerializer().deserialize(body)
        assert result["author"]["name"] == "Ada"
        assert result["author"]["type"] == "user--user"

    def test_inlines_to_many_relationship(self) -> None:
        body = {
            "data": {
                "type": "node--article",
                "id": "1",
                "attributes": {},
                "relationships": {
                    "tags": {
                        "data": [
                            {"type": "taxonomy_term--tags", "id": "t1"},
                            {"type": "taxonomy_term--tags", "id": "t2"},
                        ]
                    }
                },
            },
            "included": [
                {"type": "taxonomy_term--tags", "id": "t1", "attributes": {"name": "a"}},
                {"type": "taxonomy_term--tags", "id": "t2", "attributes": {"name": "b"}},
            ],
        }
        result = DefaultSerializer().deserialize(body)
        assert [t["name"] for t in result["tags"]] == ["a", "b"]

    def test_null_relationship_is_none(self) -> None:
        body = {
            "data": {
                "type": "n--a",
                "id": "1",
                "attributes": {},
                "relationships": {"author": {"data": None}},
            }
        }
        result = DefaultSerializer().deserialize(body)
        assert result["author"] is None

    def test_unresolved_relationship_falls_back_to_identifier(self) -> None:
        body = {
            "data": {
                "type": "n--a",
                "id": "1",
                "attributes": {},
                "relationships": {
                    "author": {"data": {"type": "user--user", "id": "u1"}}
                },
            }
            # no `included` — u1 cannot be resolved
        }
        result = DefaultSerializer().deserialize(body)
        assert result["author"] == {"type": "user--user", "id": "u1"}

    def test_relationship_without_data_is_skipped(self) -> None:
        body = {
            "data": {
                "type": "n--a",
                "id": "1",
                "attributes": {},
                "relationships": {"author": {"links": {"related": "x"}}},
            }
        }
        result = DefaultSerializer().deserialize(body)
        assert "author" not in result

    def test_circular_relationship_resolves_without_recursion(self) -> None:
        # a -> b and b -> a; must resolve to shared objects, not hang.
        body = {
            "data": {
                "type": "n--a",
                "id": "a",
                "attributes": {},
                "relationships": {"buddy": {"data": {"type": "n--a", "id": "b"}}},
            },
            "included": [
                {
                    "type": "n--a",
                    "id": "b",
                    "attributes": {},
                    "relationships": {
                        "buddy": {"data": {"type": "n--a", "id": "a"}}
                    },
                }
            ],
        }
        result = DefaultSerializer().deserialize(body)
        assert result["buddy"]["id"] == "b"
        assert result["buddy"]["buddy"] is result  # cycle points back to a


class TestClientIntegration:
    @respx.mock
    def test_client_uses_default_serializer(self, fixture) -> None:
        body = fixture("node-recipe-en-single-resource.json")
        uuid = body["data"]["id"]
        respx.get(f"https://example.com/jsonapi/node/recipe/{uuid}").mock(
            return_value=httpx.Response(200, json=body)
        )
        with JsonApiClient(
            "https://example.com", serializer=DefaultSerializer()
        ) as client:
            result = client.get_resource("node--recipe", uuid)
        # Flattened: attributes hoisted, no `data`/`attributes` wrappers.
        assert isinstance(result, Resource)
        assert result["id"] == uuid
        assert result["type"] == "node--recipe"
        assert "title" in result
        assert "attributes" not in result
