"""Hằng số và hàm dùng chung cho test backend."""

import httpx

ADMIN_USER = "admin"
ADMIN_PASSWORD = "mat-khau-dai-123"


def make_client(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def login(
    client: httpx.AsyncClient, username: str = ADMIN_USER, password: str = ADMIN_PASSWORD
) -> None:
    response = await client.post("/api/admin/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
