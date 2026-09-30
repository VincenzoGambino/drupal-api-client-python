"""Authentication types for drupal-api-client."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BasicAuth:
    """Basic authentication using username and password."""

    username: str
    password: str


@dataclass(frozen=True)
class OAuthAuth:
    """OAuth2 authentication using client credentials or password grant.

    ``scope`` is sent as the ``scope`` field of the token request when set,
    and omitted entirely when ``None``. ``token_refresh_margin`` is how many
    seconds before expiry a cached token is considered stale and replaced.
    """

    client_id: str
    client_secret: str
    grant_type: str = "client_credentials"
    username: str | None = None
    password: str | None = None
    scope: str | None = None
    token_refresh_margin: float = 60.0


@dataclass(frozen=True)
class CustomAuth:
    """Custom authentication using a pre-formed Authorization header value."""

    value: str


Authentication = BasicAuth | OAuthAuth | CustomAuth


@dataclass(frozen=True)
class OAuthTokenResponse:
    """Stores an OAuth token with its expiry and type."""

    access_token: str
    valid_until: float
    token_type: str
