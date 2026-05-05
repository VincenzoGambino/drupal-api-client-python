"""Tests for authentication header injection."""

import base64

import httpx
import respx

from drupal_api_client import ApiClient, BasicAuth, CustomAuth


class TestBasicAuth:
    @respx.mock
    def test_basic_auth_header(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        with ApiClient(
            "https://example.com",
            authentication=BasicAuth(username="admin", password="secret"),
        ) as client:
            response = client.fetch("https://example.com/test")
            expected = base64.b64encode(b"admin:secret").decode()
            assert (
                response.request.headers["authorization"]
                == f"Basic {expected}"
            )


class TestCustomAuth:
    @respx.mock
    def test_custom_auth_header(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        with ApiClient(
            "https://example.com",
            authentication=CustomAuth(value="Bearer my-custom-token"),
        ) as client:
            response = client.fetch("https://example.com/test")
            assert (
                response.request.headers["authorization"]
                == "Bearer my-custom-token"
            )


class TestNoAuth:
    @respx.mock
    def test_no_auth_no_header(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch("https://example.com/test")
            assert "authorization" not in response.request.headers
