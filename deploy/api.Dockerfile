# Backend FastAPI + rules engine. Build từ thư mục gốc repo:
#   docker build -f deploy/api.Dockerfile -t tlmn-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /app
# Cài dependency trước (cache layer), rồi mới chép mã nguồn.
COPY pyproject.toml uv.lock ./
COPY engine/pyproject.toml engine/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY engine/src engine/src
COPY backend/src backend/src
RUN uv sync --locked --no-dev --package tlmn-backend

COPY backend/alembic.ini backend/alembic.ini
COPY backend/migrations backend/migrations

RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /app/backend
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000

# Migration chỉ thêm cột/bảng (docs/gd3 §7) nên chạy trước khi khởi động là an toàn.
# 1 worker: lock theo phòng nằm trong bộ nhớ (ADR-003, G13).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
