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

### Local development

Install this checkout in editable mode **from the repository root** so that
`import drupal_api_client` resolves to the code you're editing:

```bash
pip install -e .
```

> Heads-up: if you have more than one checkout of this project, an earlier
> `pip install -e` from a different directory will shadow this one — `import
> drupal_api_client` then loads the other copy even though `pytest` (which uses
> `pythonpath = ["src"]`) still runs against this tree. Re-run `pip install -e .`
> from the directory you intend to work in. Check with
> `python -c "import drupal_api_client, os; print(os.path.dirname(drupal_api_client.__file__))"`.

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
# Optional: request a scope, and refresh earlier than the 60s default margin
OAuthAuth(client_id="...", client_secret="...", scope="content_editor",
          token_refresh_margin=120.0)

# Custom (passed verbatim into the Authorization header)
CustomAuth(value="Bearer my-token-here")
```

With `OAuthAuth`, the token is cached and replaced once less than
`token_refresh_margin` seconds (default 60) remain. If a request still gets a
401, the client discards the cached token, fetches a new one and retries once;
a second 401 is handled like any other error response. Set `scope` when the
server requires one. Simple OAuth 6.1.x on Drupal 11 refuses a
`client_credentials` token request that names no scope.

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

## Testing against a live Drupal site

The default test suite (`pytest`) mocks HTTP via `respx` and needs no
running Drupal instance. A separate, opt-in module,
`tests/test_live_integration.py`, runs the same kinds of operations
against a real site instead — useful for catching cases where a mocked
fixture has drifted from what the real API actually returns:

```bash
DRUPAL_API_CLIENT_LIVE_BASE_URL=https://your-site.ddev.site pytest -m live
```

It's skipped automatically when the env var isn't set. It was developed
against a [ddev](https://ddev.com/)-hosted Drupal 11 site running the
Umami demo profile's content, with the `jsonapi` core module and the
`decoupled_router` contrib module enabled.

The live suite covers reads, path resolution, per-locale index lookup, the
`DefaultSerializer` (including relationship inlining), and the async clients.
**Write** tests (create/update/delete) additionally need credentials for a
user with article CRUD + editorial-transition permissions:

```bash
DRUPAL_API_CLIENT_LIVE_BASE_URL=https://your-site.ddev.site \
DRUPAL_API_CLIENT_LIVE_USERNAME=apitest \
DRUPAL_API_CLIENT_LIVE_PASSWORD=your-password \
    pytest -m live
```

They're skipped if the credential vars are absent. See the module docstring
in `tests/test_live_integration.py` for the exact `drush` commands to
provision such a user on a ddev Umami site.

## GraphQL

```python
from drupal_api_client import GraphqlClient

with GraphqlClient("https://drupal.example.com") as client:
    result = client.query("query { nodeArticles(first: 10) { nodes { title } } }")
```

## Async

Every client has an async counterpart on `httpx.AsyncClient`
(`AsyncApiClient`, `AsyncJsonApiClient`, `AsyncDecoupledRouterClient`,
`AsyncGraphqlClient`), used via `async with`:

```python
from drupal_api_client import AsyncJsonApiClient

async with AsyncJsonApiClient("https://drupal.example.com") as client:
    recipes = await client.get_collection("node--recipe")
    recipe = await client.get_resource_by_path("/recipes/my-recipe")
```

## Deserializing responses

By default responses are returned as parsed JSON:API dicts. Pass
`DefaultSerializer` to flatten resources (hoist attributes, inline
relationships from `included`) and expose `get_meta()`/`get_links()`:

```python
from drupal_api_client import DefaultSerializer, JsonApiClient

with JsonApiClient("https://drupal.example.com", serializer=DefaultSerializer()) as client:
    article = client.get_resource("node--article", "<uuid>")
    print(article["title"])          # attributes hoisted, no `attributes` wrapper
    print(article.get_meta())        # document-level meta
```

## Not yet included

- **`serialize()` direction** — `DefaultSerializer` deserializes only; build
  JSON:API request bodies directly.
- A structured, per-instance injectable logger object (Python uses stdlib
  `logging`; see below).

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
