"""Async reads with AsyncJsonApiClient.

Every client has an async counterpart on httpx.AsyncClient, used via
``async with`` / ``await``.

Run:
    python examples/async_reads.py
"""

from __future__ import annotations

import asyncio

from _shared import base_url

from drupal_api_client import AsyncJsonApiClient, ResourceNotFoundError


async def main() -> None:
    async with AsyncJsonApiClient(base_url()) as client:
        collection = await client.get_collection("node--recipe")
        items = collection.get("data", [])
        print(f"Fetched {len(items)} recipe(s):")
        for item in items:
            print(f"  - {item.get('attributes', {}).get('title', '<untitled>')}")

        try:
            resource = await client.get_resource_by_path(
                "/recipes/deep-mediterranean-atlantic-food"
            )
            print("\nResolved by path:", resource["data"]["attributes"]["title"])
        except ResourceNotFoundError as exc:
            print("\nPath did not resolve:", exc)


if __name__ == "__main__":
    asyncio.run(main())
