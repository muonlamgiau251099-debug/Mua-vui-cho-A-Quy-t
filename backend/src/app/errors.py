"""Lỗi ứng dụng trả về dạng application/problem+json (RFC 9457)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def problem(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    body = {"type": "about:blank", "title": message, "status": status, "code": code, **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return problem(exc.status, exc.code, exc.message, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return problem(422, "PAYLOAD_INVALID", "Dữ liệu gửi lên không hợp lệ", errors=errors)
