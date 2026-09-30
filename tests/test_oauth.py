"""Tests for OAuth authentication flows."""

import time
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from drupal_api_client import (
    ApiClient,
    AuthenticationError,
    JsonApiClient,
    OAuthAuth,
    OAuthTokenResponse,
)


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


# -- 0.3.1: refresh margin, 401 retry, scope ---------------------------------

COLLECTION_URL = "https://example.com/jsonapi/node/article"


def _token_response(access_token: str, expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access_token,
            "expires_in": expires_in,
            "token_type": "Bearer",
        },
    )


class TestJsonApiOAuth:
    @pytest.mark.parametrize(
        ("margin_kwargs", "expires_in"),
        [
            # Default margin (60s): a 30s token would have been reused under
            # the old fixed 10s margin, so this is what proves the change.
            ({}, 30),
            ({"token_refresh_margin": 300.0}, 120),
        ],
    )
    @respx.mock
    def test_token_refreshed_when_less_than_margin_remains(
        self, margin_kwargs: dict[str, float], expires_in: int
    ) -> None:
        token_route = respx.post(OAUTH_URL).mock(
            return_value=_token_response("tok", expires_in=expires_in)
        )
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        auth = OAuthAuth(client_id="id", client_secret="secret", **margin_kwargs)
        with JsonApiClient("https://example.com", authentication=auth) as client:
            client.get_collection("node--article")
            client.get_collection("node--article")
        assert token_route.call_count == 2

    @respx.mock
    def test_401_refetches_token_and_retries_once_then_raises(self) -> None:
        token_route = respx.post(OAUTH_URL).mock(
            side_effect=[_token_response("tok-1"), _token_response("tok-2")]
        )
        resource_route = respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(401, json={"errors": []})
        )
        with JsonApiClient(
            "https://example.com",
            authentication=OAuthAuth(client_id="id", client_secret="secret"),
        ) as client:
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                client.get_collection("node--article", raise_for_status=True)

        assert exc_info.value.response.status_code == 401
        assert token_route.call_count == 2
        assert resource_route.call_count == 2
        sent = [call.request.headers["authorization"] for call in resource_route.calls]
        assert sent == ["Bearer tok-1", "Bearer tok-2"]

    @pytest.mark.parametrize("scope", ["content_editor", None])
    @respx.mock
    def test_scope_sent_in_token_request_only_when_set(
        self, scope: str | None
    ) -> None:
        token_route = respx.post(OAUTH_URL).mock(return_value=_token_response("tok"))
        respx.get(COLLECTION_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with JsonApiClient(
            "https://example.com",
            authentication=OAuthAuth(
                client_id="id", client_secret="secret", scope=scope
            ),
        ) as client:
            client.get_collection("node--article")

        body = parse_qs(token_route.calls.last.request.content.decode())
        if scope is None:
            assert "scope" not in body
        else:
            assert body["scope"] == [scope]
