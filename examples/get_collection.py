"""Fetch a collection of resources and print their titles.

Run:
    python examples/get_collection.py
"""

from __future__ import annotations

from _shared import base_url

from drupal_api_client import JsonApiClient


def main() -> None:
    with JsonApiClient(base_url()) as client:
        # Fetch a collection. Resource type is "entityType--bundle".
        collection = client.get_collection("node--recipe")

        items = collection.get("data", [])
        print(f"Fetched {len(items)} recipe(s):")
        for item in items:
            title = item.get("attributes", {}).get("title", "<untitled>")
            print(f"  - {title} ({item.get('id')})")

        # Need the underlying HTTP response too? Ask for the raw wrapper.
        raw = client.get_collection("node--recipe", raw_response=True)
        print(f"\nHTTP {raw.response.status_code}; {len(raw.json.get('data', []))} in raw payload")


if __name__ == "__main__":
    main()
