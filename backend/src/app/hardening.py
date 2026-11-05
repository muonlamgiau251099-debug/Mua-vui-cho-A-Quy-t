"""Hardening (docs/gd2/06 §1): header bảo mật, giới hạn request, lọc log, kiểm tra cấu hình prod."""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.errors import problem

MAX_BODY_BYTES = 64 * 1024

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
}


def install_hardening(app: FastAPI, settings: Settings) -> None:
    headers = dict(SECURITY_HEADERS)
    if settings.cookie_secure:  # chỉ bật HSTS khi chạy sau HTTPS
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
            response: Response = problem(413, "PAYLOAD_TOO_LARGE", "Dữ liệu gửi lên quá lớn")
        else:
            response = await call_next(request)
        for name, value in headers.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # dữ liệu cá nhân, không cache
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=guard)


# --- Lọc log: không bao giờ ghi token, cookie, mật khẩu hay bài trên tay (docs/gd2/04 §6) -------------------

_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
    (re.compile(r"(?i)(tlmn_admin_(?:session|csrf)=)[^;\s]+"), r"\1***"),
    (re.compile(r"(?i)((?:token|password)=)[^&\s]+"), r"\1***"),
]
_SECRET_KEYS = ("token", "password", "csrfToken", "yourHand", "hands", "deck", "deckSalt")
_KEY = re.compile(r'"(' + "|".join(_SECRET_KEYS) + r')"\s*:\s*')
_QUOTE = '"'
_BACKSLASH = "\\"


def _skip_json_value(text: str, i: int) -> int:
    """Vị trí ngay sau giá trị JSON bắt đầu tại i: chuỗi, mảng/object lồng nhau, hoặc giá trị đơn."""
    n = len(text)
    if i < n and text[i] == _QUOTE:
        j = i + 1
        while j < n and text[j] != _QUOTE:
            j += 2 if text[j] == _BACKSLASH else 1
        return min(j + 1, n)
    if i < n and text[i] in "[{":
        depth, j, in_string = 0, i, False
        while j < n:
            ch = text[j]
            if in_string:
                if ch == _BACKSLASH:
                    j += 1
                elif ch == _QUOTE:
                    in_string = False
            elif ch == _QUOTE:
                in_string = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return n
    j = i
    while j < n and text[j] not in ",}]\n":
        j += 1
    return j


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    out, pos = [], 0
    for match in _KEY.finditer(text):
        if match.start() < pos:
            continue
        out.append(text[pos : match.end()] + '"***"')
        pos = _skip_json_value(text, match.end())
    out.append(text[pos:])
    return "".join(out)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            data["error"] = redact(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.addFilter(RedactFilter())
    if settings.environment != "local":
        handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


class InsecureConfigError(RuntimeError):
    pass


def check_production_settings(settings: Settings) -> None:
    """Từ chối khởi động production với cấu hình không an toàn."""
    if settings.environment != "production":
        return
    problems = []
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE phải bật (chạy sau HTTPS)")
    if any(o.startswith("http://") for o in settings.allowed_origins):
        problems.append("ALLOWED_ORIGINS chỉ được chứa địa chỉ https://")
    if ":tlmn@" in settings.database_url:
        problems.append("DATABASE_URL đang dùng mật khẩu mặc định 'tlmn'")
    if problems:
        raise InsecureConfigError("Cấu hình production không an toàn: " + "; ".join(problems))
