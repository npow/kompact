"""Tests for the proxy server header forwarding."""

import pytest
from fastapi.testclient import TestClient

from kompact.config import KompactConfig
from kompact.proxy.server import create_app


@pytest.fixture
def app():
    config = KompactConfig()
    config.anthropic_base_url = "http://testserver"
    return create_app(config)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_strips_hop_by_hop_headers(app, httpx_mock):
    """Proxy must strip content-encoding/transfer-encoding to avoid double-decompression."""
    httpx_mock.add_response(
        url="http://testserver/v1/messages",
        json={"type": "message", "content": [{"type": "text", "text": "hi"}]},
    )

    with TestClient(app) as client:
        resp = client.post(
            "/v1/messages",
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "x-api-key": "test-key",
                "anthropic-version": "2023-06-01",
            },
        )

    assert resp.status_code == 200
    # These must NOT be forwarded to the client (httpx already decompresses)
    assert "content-encoding" not in resp.headers
    assert "transfer-encoding" not in resp.headers


def test_forwards_auth_headers(app, httpx_mock):
    """Proxy must forward x-api-key and anthropic-version to upstream."""
    httpx_mock.add_response(
        url="http://testserver/v1/messages",
        json={"type": "message", "content": [{"type": "text", "text": "hi"}]},
    )

    with TestClient(app) as client:
        client.post(
            "/v1/messages",
            json={
                "model": "test",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "x-api-key": "my-secret-key",
                "anthropic-version": "2023-06-01",
            },
        )

    req = httpx_mock.get_request()
    assert req.headers["x-api-key"] == "my-secret-key"
    assert req.headers["anthropic-version"] == "2023-06-01"


def test_kompact_headers_in_response(app, httpx_mock):
    """Response should include kompact metrics headers."""
    httpx_mock.add_response(
        url="http://testserver/v1/messages",
        json={"type": "message", "content": [{"type": "text", "text": "hi"}]},
    )

    with TestClient(app) as client:
        resp = client.post(
            "/v1/messages",
            json={
                "model": "test",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "x-api-key": "test",
                "anthropic-version": "2023-06-01",
            },
        )

    assert "x-kompact-tokens-saved" in resp.headers
    assert "x-kompact-compression-ratio" in resp.headers
    assert "x-kompact-latency-ms" in resp.headers
