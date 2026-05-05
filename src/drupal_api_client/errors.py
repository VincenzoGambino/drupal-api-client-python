"""Exception types for drupal-api-client."""


class DrupalApiClientError(Exception):
    """Base exception for all drupal-api-client errors."""


class AuthenticationError(DrupalApiClientError):
    """Raised when authentication fails (OAuth fetch fails, missing credentials)."""


class ConfigurationError(DrupalApiClientError):
    """Raised for configuration issues (missing base_url, bad config)."""


class ResourceNotFoundError(DrupalApiClientError):
    """Raised when a path or resource cannot be resolved."""
