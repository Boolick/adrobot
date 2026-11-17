"""Smoke tests for the FastAPI application health endpoint."""

from httpx import ASGITransport, AsyncClient

from adrobot.main import create_app


async def test_health_endpoint_returns_ok() -> None:
    """Verify GET /health responds with 200 OK and expected JSON body."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
