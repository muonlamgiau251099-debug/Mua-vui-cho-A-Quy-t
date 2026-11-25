FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/app/frontend/dist
WORKDIR /app
COPY backend/requirements-render.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY engine/src/ /app/engine/src/
COPY backend/src/app/__init__.py backend/src/app/main.py backend/src/app/memory.py backend/src/app/errors.py backend/src/app/http_security.py /app/backend/src/app/
COPY backend/src/app/realtime/__init__.py backend/src/app/realtime/chat.py /app/backend/src/app/realtime/
COPY --from=frontend /build/frontend/dist /app/frontend/dist
ENV PYTHONPATH=/app/backend/src:/app/engine/src
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers --forwarded-allow-ips='*' --ws-max-size 4096 --ws-max-queue 16 --no-access-log"]
