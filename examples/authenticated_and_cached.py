"""Authenticated requests with an injected cache and a custom logger.

Demonstrates:
  - HTTP Basic authentication
  - an injected InMemoryCache (the second identical read is served from cache)
  - a custom logger

Run:
    python examples/authenticated_and_cached.py
"""

from __future__ import annotations

import logging

from _shared import base_url, credentials

from drupal_api_client import BasicAuth, InMemoryCache, JsonApiClient


def main() -> None:
    username, password = credentials()

    # A custom logger — the client logs through the stdlib logging module
    # (logger name "drupal_api_client").
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    cache = InMemoryCache()

    with JsonApiClient(
        base_url(),
        authentication=BasicAuth(username=username, password=password),
        cache=cache,
    ) as client:
        # First read hits the network and populates the cache.
        first = client.get_collection("node--recipe")
        print(f"First read: {len(first.get('data', []))} item(s) (from network)")

        # Second identical read is served from the injected cache.
        second = client.get_collection("node--recipe")
        print(f"Second read: {len(second.get('data', []))} item(s) (from cache)")

        # Bypass the cache for a request when you need fresh data.
        fresh = client.get_collection("node--recipe", disable_cache=True)
        print(f"Fresh read: {len(fresh.get('data', []))} item(s) (cache bypassed)")


if __name__ == "__main__":
    main()
