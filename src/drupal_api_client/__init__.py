"""drupal-api-client — base HTTP client for Drupal APIs."""

from drupal_api_client.async_client import AsyncApiClient
from drupal_api_client.async_decoupled_router import AsyncDecoupledRouterClient
from drupal_api_client.async_graphql import AsyncGraphqlClient
from drupal_api_client.async_jsonapi import AsyncJsonApiClient
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
from drupal_api_client.graphql import GraphqlClient
from drupal_api_client.jsonapi import JsonApiClient, RawJsonApiResponse
from drupal_api_client.serializer import (
    DefaultSerializer,
    PassthroughSerializer,
    Resource,
    ResourceCollection,
    Serializer,
)

__all__ = [
    "ApiClient",
    "AsyncApiClient",
    "AsyncDecoupledRouterClient",
    "AsyncGraphqlClient",
    "AsyncJsonApiClient",
    "Authentication",
    "AuthenticationError",
    "BasicAuth",
    "Cache",
    "ConfigurationError",
    "CustomAuth",
    "DefaultSerializer",
    "DecoupledRouterClient",
    "DecoupledRouterResponse",
    "DrupalApiClientError",
    "GraphqlClient",
    "InMemoryCache",
    "JsonApiClient",
    "OAuthAuth",
    "OAuthTokenResponse",
    "PassthroughSerializer",
    "RawDecoupledRouterResponse",
    "RawJsonApiResponse",
    "Resource",
    "ResourceCollection",
    "ResourceNotFoundError",
    "ResolvedPath",
    "Serializer",
    "UnresolvedPath",
]
