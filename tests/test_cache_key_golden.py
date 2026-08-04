"""Cross-language golden test for cache-key query-string hashing.

The JS client hashes a request's query string with SHA-256 and hex-encodes it
into the cache key (``@aws-crypto/sha256-js`` + hex). The Python client uses
``hashlib.sha256(...).hexdigest()``. For the two clients to share a cache, these
must produce the **same** key for the same query string.

The other cache-key tests (``test_jsonapi_foundations.py::TestCreateCacheKey``)
assert against ``hashlib.sha256(qs.encode()).hexdigest()`` computed inline — that
proves internal consistency but is self-referential: it cannot catch a change to
the *encoding* or pre-processing, because the "expected" value tracks the code
under test.

This file pins the expected hex to **hard-coded literals**. Those literals are
the canonical SHA-256 hex of each input string and were cross-checked to be
identical under Node's ``crypto`` (the same algorithm the JS client uses) and
Python's ``hashlib``. If anyone changes how the query string is encoded before
hashing, these break — which is the point.
"""

from __future__ import annotations

import pytest

from drupal_api_client import JsonApiClient

# (query_string, canonical lowercase SHA-256 hex).
# Verified equal under Node `crypto.createHash('sha256')` and Python `hashlib`.
GOLDEN_QUERY_HASHES = [
    (
        "filter[title][value]=My recipe",
        "4db60b15a6f2fcd42723f3cde90761c030b9eb78e8dea1c73158c13ef06443dc",
    ),
    (
        "filter[status]=1&sort=title",
        "f4726deba418844a9bc0c9a28e36c4090f3269c1dd26aeaea143cf81042e65ff",
    ),
    (
        "page[limit]=10",
        "f950326c116a08b1c6ed87154d99cb939edd8d18b9f3a5571ce7bbca12cb95c6",
    ),
]


class TestCacheKeyQueryStringHashGolden:
    @pytest.mark.parametrize(("query_string", "expected_hex"), GOLDEN_QUERY_HASHES)
    def test_collection_key_matches_golden_hash(
        self, query_string: str, expected_hex: str
    ) -> None:
        key = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="recipe",
            query_string=query_string,
        )
        assert key == f"node--recipe--{expected_hex}"

    @pytest.mark.parametrize(("query_string", "expected_hex"), GOLDEN_QUERY_HASHES)
    def test_hash_suffix_is_stable_across_prefixes(
        self, query_string: str, expected_hex: str
    ) -> None:
        # The hashed suffix must be identical regardless of locale/resource
        # prefix — the hash depends only on the query string.
        with_locale = JsonApiClient.create_cache_key(
            entity_type_id="node",
            bundle_id="recipe",
            locale_segment="es",
            resource_id="abc-123",
            query_string=query_string,
        )
        assert with_locale == f"es--node--recipe--abc-123--{expected_hex}"
        assert with_locale.endswith(expected_hex)
