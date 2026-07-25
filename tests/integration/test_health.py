import pytest


@pytest.mark.asyncio
async def test_healthz(client):
    response = await client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_checks_db_connectivity(client):
    response = await client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
