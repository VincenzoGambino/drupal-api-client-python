"""Tests for Cache protocol and InMemoryCache."""

from drupal_api_client import ApiClient, InMemoryCache


class TestInMemoryCache:
    def test_round_trip(self) -> None:
        cache = InMemoryCache()
        cache.set("key1", {"data": "value"})
        assert cache.get("key1") == {"data": "value"}

    def test_get_missing_key_returns_default(self) -> None:
        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_get_with_custom_default(self) -> None:
        cache = InMemoryCache()
        assert cache.get("missing", "fallback") == "fallback"


class TestDelete:
    def test_delete_existing_key(self) -> None:
        cache = InMemoryCache()
        cache.set("key1", {"data": "value"})
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_missing_key_no_error(self) -> None:
        cache = InMemoryCache()
        cache.delete("nonexistent")  # Should not raise


class TestGetCachedResponse:
    def test_no_cache_returns_none(self) -> None:
        with ApiClient("https://example.com") as client:
            assert client.get_cached_response("any-key") is None

    def test_missing_key_returns_none(self) -> None:
        cache = InMemoryCache()
        with ApiClient("https://example.com", cache=cache) as client:
            assert client.get_cached_response("missing") is None

    def test_cached_value_returned(self) -> None:
        cache = InMemoryCache()
        cache.set("hit", {"data": "cached"})
        with ApiClient("https://example.com", cache=cache) as client:
            assert client.get_cached_response("hit") == {"data": "cached"}
