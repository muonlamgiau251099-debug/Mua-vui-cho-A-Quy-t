# Lớp học Thầy Trung

Web chơi Tiến Lên Miền Nam 4 người, luật do Admin quản lý tập trung. Không dùng tiền thật.

- Tài liệu: [GĐ1 Discovery](docs/gd1/GD1-Discovery.md) · [GĐ2 Design](docs/gd2/README.md) · [GĐ3 Plan](docs/gd3/GD3-Plan.md) · [Vận hành](docs/runbook.md)
- Nguồn luật: `Cau_hinh_luat_Tien_Len_Mien_Nam.xlsx` → `tools/gen_rule_catalog.py` → `engine/src/tlmn_engine/catalog.json`

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `engine/` | Rules engine Python thuần (`tlmn_engine`) |
| `backend/` | FastAPI REST + WebSocket, SQLAlchemy, Alembic |
| `frontend/` | React + TypeScript + Vite |
| `tools/` | Sinh rule catalog từ Excel, kiểm tra test phủ đủ rule ID |
| `deploy/` | Docker Compose |

## Chạy trên máy local

Yêu cầu: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, Docker Desktop.

```bash
uv sync --all-packages                                   # cài Python (engine + backend + công cụ)
docker compose -f deploy/docker-compose.dev.yml up -d db # PostgreSQL 16
cp .env.example .env
cd backend && uv run alembic upgrade head && cd ..
uv run uvicorn app.main:app --reload --app-dir backend/src   # http://localhost:8000/api/health
cd frontend && npm install && npm run dev                # http://localhost:5173
```

Tạo tài khoản Admin (không có trang đăng ký công khai), rồi vào http://localhost:5173/admin:

```bash
cd backend && uv run python -m app.cli create-admin --username admin   # hỏi mật khẩu (≥ 12 ký tự)
```

Lần chạy đầu tiên, server tự tạo bộ luật v1 từ cấu hình mặc định đã duyệt (hoặc chạy `uv run python -m app.cli seed-rules`).

## Kiểm tra

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest          # test cần PostgreSQL tự bỏ qua nếu DB chưa chạy; đặt REQUIRE_DB=1 để bắt buộc
uv run python tools/gen_rule_catalog.py --appendix --check   # catalog/Phụ lục A khớp Excel
uv run python tools/check_rule_trace.py                      # số rule ID đã có test
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Kiểm thử trên trình duyệt thật (Playwright) với stack production chạy bằng Docker:

```bash
cp deploy/.env.example deploy/.env   # chạy thử trên máy: ENVIRONMENT=staging, SITE_ADDRESS=:80, HTTP_PORT=8080,
                                     # ALLOWED_ORIGINS=["http://localhost:8080"], COOKIE_SECURE=false
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
cd frontend && npx playwright install chromium && E2E_BASE_URL=http://localhost:8080 npm run e2e
```

Triển khai, sao lưu, nâng cấp, kiểm thử tải: xem [docs/runbook.md](docs/runbook.md).

Khi sửa file Excel luật: chạy `uv run python tools/gen_rule_catalog.py --appendix`. Nếu Excel thêm hoặc bớt ID thì cập nhật `tools/rule_mapping.json` trước (công cụ sẽ báo ID nào lệch).
