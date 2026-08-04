"""Resolve a front-end path to a resource via the Decoupled Router.

Requires the ``decoupled_router`` module on the Drupal site.

Run:
    python examples/get_resource_by_path.py [/some/path]
"""

from __future__ import annotations

import sys

from _shared import base_url

from drupal_api_client import JsonApiClient, ResourceNotFoundError


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/recipes/deep-mediterranean-atlantic-food"

    with JsonApiClient(base_url()) as client:
        try:
            resource = client.get_resource_by_path(path)
        except ResourceNotFoundError as exc:
            # Python divergence (D3): unresolved paths raise rather than
            # returning the router's "unresolved" payload.
            print(f"Could not resolve {path!r}: {exc}")
            return

        data = resource.get("data", {})
        attributes = data.get("attributes", {})
        print(f"Resolved {path!r} ->")
        print(f"  type:  {data.get('type')}")
        print(f"  id:    {data.get('id')}")
        print(f"  title: {attributes.get('title', '<untitled>')}")


if __name__ == "__main__":
    main()
