"""drupal-api-client — base HTTP client for Drupal APIs."""

from drupal_api_client.auth import (
    Authentication,
    BasicAuth,
    CustomAuth,
    OAuthAuth,
    OAuthTokenResponse,
)
from drupal_api_client.cache import Cache, InMemoryCache
from drupal_api_client.client import ApiClient
from drupal_api_client.decoupled_router import (
    DecoupledRouterClient,
    DecoupledRouterResponse,
    RawDecoupledRouterResponse,
    ResolvedPath,
    UnresolvedPath,
)
from drupal_api_client.errors import (
    AuthenticationError,
    ConfigurationError,
    DrupalApiClientError,
    ResourceNotFoundError,
)
from drupal_api_client.jsonapi import JsonApiClient, RawJsonApiResponse
from drupal_api_client.serializer import PassthroughSerializer, Serializer

__all__ = [
    "ApiClient",
    "Authentication",
    "AuthenticationError",
    "BasicAuth",
    "Cache",
    "ConfigurationError",
    "CustomAuth",
    "DecoupledRouterClient",
    "DecoupledRouterResponse",
    "DrupalApiClientError",
    "InMemoryCache",
    "JsonApiClient",
    "OAuthAuth",
    "OAuthTokenResponse",
    "PassthroughSerializer",
    "RawDecoupledRouterResponse",
    "RawJsonApiResponse",
    "ResourceNotFoundError",
    "ResolvedPath",
    "Serializer",
    "UnresolvedPath",
]
