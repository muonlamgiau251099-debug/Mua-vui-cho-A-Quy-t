# Frontend tĩnh + reverse proxy (Caddy, HTTPS tự động). Build từ thư mục gốc repo:
#   docker build -f deploy/web.Dockerfile -t tlmn-web .
FROM node:22-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2.8-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
