import httpx

from app.config import Settings
from app.main import create_app


async def test_health_without_db_reports_degraded(no_db_settings: Settings) -> None:
    app = create_app(no_db_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    await app.state.engine.dispose()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "unavailable"
    assert body["ruleCatalogSize"] == 130


async def test_health_with_db_is_ok(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    assert (body["status"], body["db"]) == ("ok", "ok")
