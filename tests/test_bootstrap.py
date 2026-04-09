"""Bootstrap tests for the project foundation."""


async def test_health_endpoint(async_client) -> None:
    """The health endpoint should return a successful service status."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
