import asyncio

import httpx

from app.main import app


def test_swagger_docs_and_bearer_auth_schema() -> None:
    async def get_docs() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/docs"), await client.get("/openapi.json")

    docs, openapi = asyncio.run(get_docs())

    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
    assert openapi.status_code == 200
    schema = openapi.json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/resources"]["get"]["security"] == [{"HTTPBearer": []}]


def test_health() -> None:
    async def request_health() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
