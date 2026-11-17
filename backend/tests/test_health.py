"""Smoke tests for the FastAPI application health endpoint and settings."""

import pytest
from httpx import ASGITransport, AsyncClient

from adrobot.core.config import Settings
from adrobot.main import create_app


async def test_health_endpoint_returns_ok() -> None:
    """Verify GET /health responds with 200 OK and expected JSON body."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_accepts_keitaro_base_url_alias_and_default_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify KEITARO_BASE_URL alias populates keitaro_api_url and default CORS includes 8080."""
    monkeypatch.delenv("KEITARO_API_URL", raising=False)
    monkeypatch.setenv("KEITARO_BASE_URL", "https://keitaro.example.com/admin_api/v1/")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://localhost:8080","http://localhost:3000","http://localhost:5173"]',
    )

    settings = Settings()

    assert settings.keitaro_api_url == "https://keitaro.example.com/admin_api/v1"
    assert "http://localhost:8080" in settings.cors_origins
    assert "http://localhost:3000" in settings.cors_origins
