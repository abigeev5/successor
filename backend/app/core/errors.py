"""Application errors. API responses always look like {"detail": "<Russian text>", "code": "<code>"}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    detail = "Некорректный запрос"

    def __init__(self, detail: str | None = None, *, code: str | None = None, status_code: int | None = None):
        self.detail = detail or self.detail
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        super().__init__(self.detail)


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    detail = "Войдите в систему"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    detail = "Недостаточно прав"


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    detail = "Не найдено"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    detail = "Конфликт данных"


_HTTP_DETAILS = {
    401: ("not_authenticated", "Войдите в систему"),
    403: ("forbidden", "Недостаточно прав"),
    404: ("not_found", "Не найдено"),
    405: ("method_not_allowed", "Метод не поддерживается"),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail, "code": exc.code}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "Некорректные данные запроса",
                "code": "validation_error",
                "errors": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
            },
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, detail = _HTTP_DETAILS.get(exc.status_code, ("http_error", "Ошибка запроса"))
        return JSONResponse({"detail": detail, "code": code}, status_code=exc.status_code)
