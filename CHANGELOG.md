# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-09-30

### Added

- **`OAuthAuth(scope=...)`**: optional, defaults to `None`. When set, it
  is sent as the `scope` field of the `oauth/token` request. When `None` the
  token request body is exactly what it was in 0.3.0, with no `scope` field.
  Simple OAuth 6.1.x on Drupal 11 grants `client_credentials` tokens only
  the consumer's scopes and refuses a request that names none, so callers
  need a way to ask for one explicitly.
- **`OAuthAuth(token_refresh_margin=...)`**: defaults to `60.0` seconds. A
  cached token is replaced once less than this margin remains before it
  expires.
- **One retry on 401 with a fresh token.** When an OAuth-authenticated
  request gets a 401, the client discards the cached token, fetches a new
  one and retries the request once. If the retry also gets a 401, it is
  handled as before: raised as `httpx.HTTPStatusError` when
  `raise_for_status` is set, returned otherwise. Requests made with
  `disable_authentication=True`, and clients using `BasicAuth` or
  `CustomAuth`, are never retried.

### Changed

- The token refresh margin is now 60 seconds by default, where it used to be
  a fixed 10 seconds. Tokens are replaced earlier, so a request is less
  likely to leave with a token that expires on its way to the server.

All three changes apply to the sync and async clients alike, because they
live in `ApiClient` / `AsyncApiClient`. They are Python-only supersets of the
JS client, which still uses a fixed 10-second margin, has no retry and sends
no scope. `AuthenticationError` behaves as before: refused or missing
credentials still raise it, including when the token fetch for a 401 retry is
refused.

## [0.3.0] - 2026-08-04

Supersedes the `0.3.0` and `0.4.0` entries that previously appeared here: both
described work that was written but never committed, tagged, or published. PyPI
went straight from 0.2.0 to this release, so their contents are merged below and
every version listed in this file now corresponds to an actual release.

### Added

- **GraphQL client** (`GraphqlClient`) — POSTs a query to the `graphql`
  endpoint and returns the parsed body. Byte-identical `{"query": ...}`
  envelope to the JS client, plus an optional `variables=` (superset).
- **Deserializing serializer** (`DefaultSerializer`) — a schema-less,
  zero-dependency JSON:API flattener: hoists attributes, inlines
  relationships from `included` (to-many, nulls, unresolved-linkage
  fallback, circular references), and exposes `get_meta()`/`get_links()`
  via `Resource`/`ResourceCollection`. Closes the parity gap with the JS
  `DefaultSerializer` (which uses `jsona`).
- **Async clients** — `AsyncApiClient`, `AsyncJsonApiClient`,
  `AsyncDecoupledRouterClient`, `AsyncGraphqlClient` on `httpx.AsyncClient`,
  used via `async with`. Reuse the sync pure helpers (URL/cache-key building,
  serializer, response processing) and override only I/O paths.
- **`cache_key` on write methods** — `create_resource()`, `update_resource()`
  and `delete_resource()` now accept `cache_key=`, invalidated *in addition
  to* the canonical collection/resource keys. Without it, a caller who read
  under a custom cache key had no way to invalidate that entry on write, so it
  stayed stale indefinitely. The JS client accepts `cacheKey` on all three.
- **Shared golden test fixtures** — the JS client's fixture JSON is copied
  verbatim into `tests/fixtures/` and loaded via `conftest.py`, so both
  clients are exercised against byte-identical payloads.
- **Cross-language cache-key golden test** (`test_cache_key_golden.py`) —
  pins the query-string SHA-256 hex to literals verified equal under Node
  `crypto` and Python `hashlib`.
- **Examples** (`examples/`) — runnable `get_collection`,
  `get_resource_by_path`, `authenticated_and_cached`, `async_reads`, and
  `graphql_query` scripts.
- **Live OAuth coverage** (`TestLiveOAuth`) — exercises the
  `client_credentials` grant against a real Simple OAuth 6.x install:
  token-response shape, `Bearer` header, token reuse across requests, and a
  full create → update → delete lifecycle authenticated purely by OAuth.
  This matters because `_get_access_token` subscripts `access_token`,
  `expires_in` and `token_type` without a guard — a server naming them
  differently would `KeyError` in production while every mocked test stayed
  green. Gated on `DRUPAL_API_CLIENT_LIVE_CLIENT_ID` /
  `DRUPAL_API_CLIENT_LIVE_CLIENT_SECRET`; see the module docstring for the
  full ddev setup. Note that Simple OAuth 6.x **removed the `password`
  grant**, so that path remains mock-only against a 6.x target.
- `tests/test_live_integration.py` — an opt-in test module that runs the
  same operations against a real Drupal site instead of mocked HTTP.
  Skipped by default; enable with
  `DRUPAL_API_CLIENT_LIVE_BASE_URL=<url> pytest -m live`. Developed
  against `drupal-headless` (ddev) running the Umami demo content with
  `jsonapi` + `decoupled_router` enabled.

### Fixed (breaking)

- `ResolvedPath.resolved` was typed `bool` but the real Decoupled Router
  API — and the JS client's own `ResolvedPath.resolved: string` — returns
  the **canonical resolved URL as a string**, not a boolean. Every
  existing test was masked by a synthetic `"resolved": True` fixture that
  didn't match reality; caught by testing against a live Drupal site.
  `ResolvedPath.resolved` is now typed `str`.
- `UnresolvedPath.resolved` (a synthetic field with no real-API
  equivalent — the actual 404 response body has no `resolved` key at
  all) has been removed, matching the JS client's `UnResolvedPath` shape
  (`message`, `details` only). Use `isinstance(result, UnresolvedPath)`
  instead of checking `.resolved`.
- `UnresolvedPath.details` is typed `str | None`, not
  `dict[str, Any] | None`. Drupal's Decoupled Router returns a human-readable
  explanation string, and the JS client types it `string`. The wrong
  annotation survived because the hand-written test body used a dict while the
  real fixture (`tests/fixtures/unresolved-article.json`) is a string; both
  hand-written bodies have been corrected to match the fixture.

### Fixed

- **`get_resource_by_path` now reads the router's `jsonapi.resourceName`**
  instead of composing the resource type from the entity's `type` and
  `bundle`. `jsonapi_extras` can rename a resource — e.g. expose
  `node--article` as `content--story` — and the composed type ignored the
  rename, requesting the un-rewritten path and 404ing. This matches the JS
  client, which reads `routingData.jsonapi.resourceName`. Falls back to
  `{type}--{bundle}` when a router omits `resourceName`. Applies to both the
  sync and async clients.
- **The JSON:API index is now stored in the injected cache**, under the same
  key the JS client uses (`{locale/}{api_prefix}`, e.g. `jsonapi` or
  `es/jsonapi`). It previously lived only in a private per-instance dict, so
  it could never be invalidated and was refetched once per client instance
  even when a shared or persistent cache was supplied. The private memo is
  retained for clients with no injected cache, so the index is still fetched
  only once in that case.
- `JsonApiClient` no longer silently ignores an injected `http_client` for
  the internal `DecoupledRouterClient` (`self.router`). Previously, a
  custom/mocked `httpx.Client` passed to `JsonApiClient(...)` was only
  used for direct JSON:API requests; `get_resource_by_path()` — which
  delegates to `self.router.translate_path()` — would silently fall back
  to a separate, default-configured `httpx.Client`, ignoring any custom
  timeout, proxy, TLS config, or test mock transport. `self.router` now
  shares the same `http_client` instance as the rest of `JsonApiClient`.
- `JsonApiClient.create_resource()`, `update_resource()`, and
  `delete_resource()` now honor `index_lookup=True` even when no prior
  read (`get_collection`/`get_resource`) has warmed the index cache.
  Previously, only the read methods called `_fetch_index()`; the write
  methods relied on `create_url()`, which only *uses* the cached index if
  already populated and never fetches it. A write issued as the first
  operation on a fresh client with `index_lookup=True` silently fell back
  to the standard `{prefix}/{entity}/{bundle}` URL instead of the
  endpoint advertised by the JSON:API index — a divergence from the JS
  client, where index-fetching is embedded in `createURL()` itself and
  applies uniformly to every method that builds a URL.

### Changed

- A line-by-line audit against the JS client turned up several behavioural
  differences that had never been documented. Two were bugs and are fixed
  above. Two more are fixed in this release (the JSON:API index cache and
  `cache_key` on writes). The remainder are **deliberate** and are called out
  here so they are not mistaken for oversights:

  - `fetch` lets `httpx.HTTPError` propagate; the JS client returns a
    `{response, error}` result and never throws on transport failure.
    Exceptions are the Python idiom, and a result tuple would fight `httpx`.
  - `get_view(view_id, display_id)` takes two arguments where JS packs them
    into one `"view--display"` string. URLs and cache keys are identical.
  - The `Cache` protocol requires `delete` (JS is `get`/`set` only) — this is
    what makes invalidation-on-write possible.
  - Write methods accept `query_string` (JS's do not) and omit
    `disable_cache`, which is meaningless here: JS uses it to suppress the
    post-write cache write, and this client invalidates instead.
  - `raw_response=True` performs no cache write; JS caches the body anyway.
  - Request bodies must be a `dict`; JS also accepts a pre-serialized string.
  - The `Serializer` protocol requires both `deserialize` and `serialize`;
    JS declares both optional. `DefaultSerializer.serialize` raises
    `NotImplementedError`.
  - A 204 response parses to `{}` rather than JS's `""`. Only observable via
    `raw_response=True` on a delete, since the normal path returns `None`.

### Notes

- Decoupled Router `translate_path` URL-encodes the `path` query parameter
  (JS interpolates it raw). Cache keys are unaffected (they use the raw
  path, matching JS); only the request URL differs.

## [0.2.0] - 2026-05-05

### Added

- `DecoupledRouterClient` — resolves Drupal path aliases via the Decoupled Router module.
- `translate_path()` method with locale, caching, raw response, and raise-for-status support.
- Discriminated union response types: `ResolvedPath` and `UnresolvedPath` (`DecoupledRouterResponse = ResolvedPath | UnresolvedPath`).
- `RawDecoupledRouterResponse` for access to both `httpx.Response` and parsed JSON.
- `create_url()` and `create_cache_key()` helpers.
- `JsonApiClient` foundations — constructor, URL/cache-key helpers, response processing.
- `RawJsonApiResponse` dataclass for raw response access.
- `_get_entity_type_and_bundle()` static helper with stricter validation than JS — JS silently returns empty bundle on malformed input, Python raises `ValueError`.
- `create_url()` and `create_cache_key()` for JSON:API endpoints, with SHA-256 query-string hashing matching the JS implementation byte-for-byte.
- `_process_api_response()` helper for JSON parsing and serializer integration.
- `JsonApiClient.get_collection()`, `get_resource()`, `get_view()`, `get_resource_by_path()` — read operations.
- `JsonApiClient._fetch_index()` — lazy index discovery for `index_lookup=True`.
- 204 No Content handling in `_process_api_response()`.
- `ResourceNotFoundError` — raised by `get_resource_by_path()` when the path cannot be resolved.
- `JsonApiClient.create_resource()`, `update_resource()`, `delete_resource()` — write operations.
- Cache invalidation on successful writes: drops canonical collection key and (for update/delete) canonical resource key.
- `Cache.delete()` method added to the protocol; `InMemoryCache` updated to implement it.
- Write methods default `raise_for_status=True` (reads default to `False`).

### Changed

- `ApiClient.fetch()` — replaced `body` parameter with separate `json` and `content` parameters mirroring httpx. `ValueError` raised when both are provided.
- Write methods invalidate cached entries rather than caching write responses (a divergence from the JS implementation). A subsequent read of a just-updated resource will trigger an HTTP request.
- `Cache` protocol now requires a `delete(key)` method. Existing custom implementations will need updating.

## [0.1.0] - 2026-05-04

### Added

- `ApiClient` base class with `fetch()`, `add_authorization_header()`, `get_cached_response()`.
- Authentication support: `BasicAuth`, `OAuthAuth`, `CustomAuth` frozen dataclasses.
- OAuth2 token management with `client_credentials` and `password` grant types.
- `Cache` protocol with `InMemoryCache` default implementation.
- `Serializer` protocol with `PassthroughSerializer` default implementation.
- Custom exception hierarchy: `DrupalApiClientError`, `AuthenticationError`, `ConfigurationError`.
- Context manager support (`with ApiClient(...) as client:`).
- PEP 561 `py.typed` marker for type checking support.
