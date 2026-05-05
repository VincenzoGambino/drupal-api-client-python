# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
