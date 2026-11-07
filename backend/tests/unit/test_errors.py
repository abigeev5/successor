import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import Forbidden, install_error_handlers


def make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    class Body(BaseModel):
        n: int

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise Forbidden("Нет доступа к этой передаче дел", code="handover_forbidden")

    @app.post("/body")
    async def body(data: Body) -> int:
        return data.n

    return app


async def request(method: str, path: str, **kw: object) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url="http://t") as c:
        return await c.request(method, path, **kw)  # type: ignore[arg-type]


async def test_app_error_format() -> None:
    response = await request("GET", "/forbidden")
    assert response.status_code == 403
    assert response.json() == {"detail": "Нет доступа к этой передаче дел", "code": "handover_forbidden"}


async def test_validation_error_is_russian() -> None:
    response = await request("POST", "/body", json={"n": "abc"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Некорректные данные запроса"
    assert response.json()["code"] == "validation_error"


async def test_unknown_route_is_russian() -> None:
    response = await request("GET", "/nope")
    assert response.json() == {"detail": "Не найдено", "code": "not_found"}
