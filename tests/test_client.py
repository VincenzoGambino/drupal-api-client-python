"""Tests for ApiClient core behaviour."""

import httpx
import pytest
import respx

from drupal_api_client import ApiClient, BasicAuth, ConfigurationError


class TestBaseUrlNormalization:
    def test_trailing_slash_added(self) -> None:
        with ApiClient("https://example.com") as client:
            assert client.base_url == "https://example.com/"

    def test_trailing_slash_preserved(self) -> None:
        with ApiClient("https://example.com/") as client:
            assert client.base_url == "https://example.com/"

    def test_empty_base_url_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            ApiClient("")


class TestFetch:
    @respx.mock
    def test_fetch_get(self) -> None:
        respx.get("https://example.com/api/test").mock(
            return_value=httpx.Response(200, json={"data": "ok"})
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch("https://example.com/api/test")
            assert response.status_code == 200
            assert response.json() == {"data": "ok"}

    @respx.mock
    def test_fetch_post(self) -> None:
        respx.post("https://example.com/api/test").mock(
            return_value=httpx.Response(201, json={"created": True})
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch(
                "https://example.com/api/test",
                method="POST",
                content=b'{"title": "New"}',
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 201

    @respx.mock
    def test_fetch_json_body(self) -> None:
        respx.post("https://example.com/api/test").mock(
            return_value=httpx.Response(201, json={"created": True})
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch(
                "https://example.com/api/test",
                method="POST",
                json={"title": "New"},
            )
            assert response.status_code == 201

    def test_fetch_json_and_content_mutually_exclusive(self) -> None:
        with ApiClient("https://example.com") as client:
            with pytest.raises(ValueError, match="mutually exclusive"):
                client.fetch(
                    "https://example.com/api/test",
                    method="POST",
                    json={"title": "New"},
                    content=b"raw",
                )

    @respx.mock
    def test_fetch_no_body(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch("https://example.com/test")
            assert response.status_code == 200

    @respx.mock
    def test_custom_http_client(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        custom = httpx.Client()
        client = ApiClient("https://example.com", http_client=custom)
        try:
            response = client.fetch("https://example.com/test")
            assert response.status_code == 200
        finally:
            client.close()
        # Custom client must NOT be closed by ApiClient.
        assert not custom.is_closed
        custom.close()

    @respx.mock
    def test_disable_authentication_bypasses_auth(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(200)
        )
        with ApiClient(
            "https://example.com",
            authentication=BasicAuth(username="user", password="pass"),
        ) as client:
            response = client.fetch(
                "https://example.com/test",
                disable_authentication=True,
            )
            assert response.status_code == 200
            assert "authorization" not in response.request.headers

    @respx.mock
    def test_raise_for_status_enabled(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(404)
        )
        with ApiClient("https://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.fetch(
                    "https://example.com/test",
                    raise_for_status=True,
                )

    @respx.mock
    def test_raise_for_status_disabled_by_default(self) -> None:
        respx.get("https://example.com/test").mock(
            return_value=httpx.Response(404)
        )
        with ApiClient("https://example.com") as client:
            response = client.fetch("https://example.com/test")
            assert response.status_code == 404


class TestContextManager:
    def test_close_owned_client(self) -> None:
        client = ApiClient("https://example.com")
        assert client._owns_client is True
        client.close()
        assert client._http_client.is_closed

    def test_close_does_not_close_injected_client(self) -> None:
        custom = httpx.Client()
        client = ApiClient("https://example.com", http_client=custom)
        assert client._owns_client is False
        client.close()
        assert not custom.is_closed
        custom.close()
