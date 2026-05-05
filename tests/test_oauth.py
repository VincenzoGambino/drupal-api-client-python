"""Tests for OAuth authentication flows."""

import time

import httpx
import pytest
import respx

from drupal_api_client import ApiClient, AuthenticationError, OAuthAuth, OAuthTokenResponse


OAUTH_URL = "https://example.com/oauth/token"


def _make_oauth_client(**overrides: object) -> ApiClient:
    defaults: dict[str, object] = {
        "client_id": "my-client",
        "client_secret": "my-secret",
    }
    defaults.update(overrides)
    return ApiClient(
        "https://example.com",
        authentication=OAuthAuth(**defaults),  # type: ignore[arg-type]
    )


class TestClientCredentialsFlow:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.post(OAUTH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "tok123",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )
        respx.get("https://example.com/api/test").mock(
            return_value=httpx.Response(200)
        )
        with _make_oauth_client() as client:
            resp = client.fetch("https://example.com/api/test")
            assert resp.status_code == 200
            assert resp.request.headers["authorization"] == "Bearer tok123"


class TestPasswordGrantFlow:
    @respx.mock
    def test_happy_path(self) -> None:
        respx.post(OAUTH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "pw-tok",
                    "expires_in": 1800,
                    "token_type": "Bearer",
                },
            )
        )
        respx.get("https://example.com/api/test").mock(
            return_value=httpx.Response(200)
        )
        with _make_oauth_client(
            grant_type="password",
            username="admin",
            password="pass",
        ) as client:
            resp = client.fetch("https://example.com/api/test")
            assert resp.request.headers["authorization"] == "Bearer pw-tok"


class TestTokenCaching:
    @respx.mock
    def test_token_reuse_before_expiry(self) -> None:
        token_route = respx.post(OAUTH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "cached-tok",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )
        respx.get("https://example.com/api/test").mock(
            return_value=httpx.Response(200)
        )
        with _make_oauth_client() as client:
            client.fetch("https://example.com/api/test")
            client.fetch("https://example.com/api/test")
            assert token_route.call_count == 1

    @respx.mock
    def test_token_refresh_after_expiry(self) -> None:
        token_route = respx.post(OAUTH_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new-tok",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )
        respx.get("https://example.com/api/test").mock(
            return_value=httpx.Response(200)
        )
        with _make_oauth_client() as client:
            client.fetch("https://example.com/api/test")
            assert token_route.call_count == 1

            # Simulate an expired token.
            client._oauth_token_response = OAuthTokenResponse(
                access_token="old-tok",
                valid_until=time.time() - 1,
                token_type="Bearer",
            )

            client.fetch("https://example.com/api/test")
            assert token_route.call_count == 2


class TestOAuthErrors:
    def test_missing_client_id_raises(self) -> None:
        with _make_oauth_client(client_id="", client_secret="secret") as client:
            with pytest.raises(AuthenticationError, match="client_id or client_secret"):
                client.add_authorization_header()

    def test_missing_client_secret_raises(self) -> None:
        with _make_oauth_client(client_id="id", client_secret="") as client:
            with pytest.raises(AuthenticationError, match="client_id or client_secret"):
                client.add_authorization_header()

    @respx.mock
    def test_failed_token_request_raises(self) -> None:
        respx.post(OAUTH_URL).mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )
        with _make_oauth_client() as client:
            with pytest.raises(
                AuthenticationError, match="Could not authenticate"
            ):
                client.add_authorization_header()

    def test_password_grant_missing_username_raises(self) -> None:
        with _make_oauth_client(grant_type="password") as client:
            with pytest.raises(AuthenticationError, match="username or password"):
                client.add_authorization_header()
