# drupal-api-client

A Python client for [Drupal](https://www.drupal.org/) APIs — a port of [`@drupal-api-client/api-client`](https://github.com/drupal-api-client/drupal-api-client) (JavaScript).

[![CI](https://github.com/VincenzoGambino/drupal-api-client-python/actions/workflows/ci.yml/badge.svg)](https://github.com/VincenzoGambino/drupal-api-client-python/actions)
[![PyPI](https://img.shields.io/pypi/v/drupal-api-client.svg)](https://pypi.org/project/drupal-api-client/)

## What's included

- **`ApiClient`** — base HTTP client with auth, caching, logging, and serializer hooks.
- **`DecoupledRouterClient`** — resolves Drupal path aliases via the [Decoupled Router](https://www.drupal.org/project/decoupled_router) module.
- **`JsonApiClient`** — full CRUD over Drupal's [JSON:API](https://www.drupal.org/docs/core-modules-and-themes/core-modules/jsonapi-module) module.

## Installation

```bash
pip install drupal-api-client
```

For building query strings, install the companion package:

```bash
pip install drupal-jsonapi-params
```

## Quick start

### Reading a collection

```python
from drupal_api_client import JsonApiClient

with JsonApiClient("https://example.com") as client:
    articles = client.get_collection("node--article")
    for article in articles["data"]:
        print(article["attributes"]["title"])
```

### Reading with filters (using `drupal-jsonapi-params`)

```python
from drupal_api_client import JsonApiClient
from drupal_jsonapi_params import DrupalJsonApiParams, FilterOperator

params = (
    DrupalJsonApiParams()
    .add_filter("status", "1")
    .add_filter("title", "Hello", FilterOperator.CONTAINS)
    .add_include(["field_image"])
    .add_page_limit(10)
)

with JsonApiClient("https://example.com") as client:
    articles = client.get_collection("node--article", query_string=params)
```

### Resolving a path alias

```python
from drupal_api_client import JsonApiClient

with JsonApiClient("https://example.com") as client:
    article = client.get_resource_by_path("/about-us")
    print(article["data"]["attributes"]["title"])
```

### Authenticated writes

```python
from drupal_api_client import JsonApiClient, BasicAuth

auth = BasicAuth(username="admin", password="secret")
with JsonApiClient("https://example.com", authentication=auth) as client:
    new_article = client.create_resource(
        "node--article",
        {
            "data": {
                "type": "node--article",
                "attributes": {"title": "New article", "body": {"value": "..."}},
            }
        },
    )

    client.update_resource(
        "node--article",
        new_article["data"]["id"],
        {"data": {"type": "node--article", "id": new_article["data"]["id"], "attributes": {"title": "Updated"}}},
    )

    client.delete_resource("node--article", new_article["data"]["id"])
```

## Authentication

Three auth types are supported:

```python
from drupal_api_client import BasicAuth, OAuthAuth, CustomAuth

# HTTP Basic
BasicAuth(username="admin", password="secret")

# OAuth2 (client_credentials or password grant)
OAuthAuth(client_id="...", client_secret="...")
OAuthAuth(client_id="...", client_secret="...", grant_type="password",
          username="...", password="...")

# Custom (passed verbatim into the Authorization header)
CustomAuth(value="Bearer my-token-here")
```

## Caching

Pass any object implementing the `Cache` protocol (`get`, `set`, `delete`):

```python
from drupal_api_client import JsonApiClient, InMemoryCache

with JsonApiClient("https://example.com", cache=InMemoryCache()) as client:
    client.get_resource("node--article", "abc-123")  # HTTP call
    client.get_resource("node--article", "abc-123")  # cache hit, no HTTP
```

Write methods invalidate the canonical cached entries for the affected resource. Cache entries with locales or query strings are not auto-invalidated — pass `disable_cache=True` to bypass them, or implement a custom cache with prefix-based invalidation.

## Discriminated unions

`get_resource_by_path` raises `ResourceNotFoundError` when the path can't be resolved. For lower-level access, `DecoupledRouterClient.translate_path` returns a discriminated union:

```python
from drupal_api_client import DecoupledRouterClient, ResolvedPath, UnresolvedPath

with DecoupledRouterClient("https://example.com") as router:
    result = router.translate_path("/about-us")
    match result:
        case ResolvedPath(entity=entity, label=label):
            print(f"Found {label}: {entity['uuid']}")
        case UnresolvedPath(message=msg):
            print(f"Not found: {msg}")
```

## What's not in v0.2.0

- **GraphQL client** — coming in v0.3.0.
- **Async support** — sync only for now. Use `asyncio.to_thread()` to call from async code.
- **Built-in JSON:API document parser** — responses are returned as parsed dicts. Use [`jsonapi-client`](https://pypi.org/project/jsonapi-client/) or write your own parser if you need flattened resources with resolved relationships.

## Logging

Configure standard Python logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("drupal_api_client").setLevel(logging.DEBUG)
```

## Compatibility

- Python 3.10+
- Drupal 9.x, 10.x, 11.x with the JSON:API module enabled
- Optional Drupal modules: Decoupled Router (for path resolution), JSON:API Views (for `get_view`)

## License

ISC. See `LICENSE`. Original JavaScript implementation is MIT-licensed by the Drupal API Client contributors; see `NOTICE`.

## Contributing

Issues and pull requests welcome at [github.com/VincenzoGambino/drupal-api-client-python](https://github.com/VincenzoGambino/drupal-api-client-python).
