# GĐ3 — Kế hoạch triển khai

- Trạng thái: **ĐÃ DUYỆT (2026-10-30)**
- Đầu vào: [GĐ1 (đã duyệt)](../gd1/GD1-Discovery.md), [GĐ2 (đã duyệt)](../gd2/README.md)

## 1. Cấu trúc thư mục (repo)

```
tienlenmiennam/
├─ Cau_hinh_luat_Tien_Len_Mien_Nam.xlsx     # nguồn luật gốc (giữ nguyên)
├─ CLAUDE.md
├─ docs/                                    # gd1, gd2, gd3, adr, runbook
├─ engine/                                  # package Python thuần: tlmn_engine
│  ├─ src/tlmn_engine/
│  │  ├─ cards.py  combos.py  compare.py  chop.py
│  │  ├─ rules_config.py  catalog.json      # RuleConfig (Pydantic) + catalog sinh từ Excel
│  │  ├─ state.py  reducer.py  instant_win.py  redeal.py
│  │  ├─ rot.py  scoring.py  projection.py  invariants.py
│  └─ tests/  (unit theo Excel ID, property Hypothesis, fixtures đối soát)
├─ backend/                                 # FastAPI app
│  ├─ src/app/
│  │  ├─ api/ (admin, rules, guests, rooms, history)
│  │  ├─ realtime/ (ws_gateway, room_actor, timer_service)
│  │  ├─ services/  repo/  models/  security/  config.py  main.py
│  ├─ migrations/ (Alembic)
│  └─ tests/ (integration API + WS với PostgreSQL thật)
├─ frontend/                                # React + TS + Vite
│  ├─ src/ (pages, components, hooks/useRoomSocket, api, styles)
│  └─ tests/ (vitest) · e2e/ (Playwright)
├─ tools/
│  ├─ gen_rule_catalog.py                   # Excel → engine/src/tlmn_engine/catalog.json
│  └─ check_rule_trace.py                   # bảo đảm 130/130 Excel ID có test
├─ deploy/
│  ├─ docker-compose.yml  docker-compose.dev.yml
│  ├─ Caddyfile  api.Dockerfile  web.Dockerfile
│  └─ backup/ (pg_dump cron, restore.sh)
└─ .github/workflows/ci.yml
```

## 2. Công nghệ và phiên bản

| Phần | Lựa chọn |
|---|---|
| Python | 3.12; quản lý gói bằng **uv** (lock file); ruff (lint + format), mypy strict cho engine |
| Backend | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x async, asyncpg, Alembic, argon2-cffi |
| Test Python | pytest, pytest-asyncio, Hypothesis, httpx, websockets, coverage |
| Frontend | Node 24 (đã có trên máy), React 18, TypeScript 5, Vite, React Router, TanStack Query, @dnd-kit, vitest, ESLint, Playwright |
| DB | PostgreSQL 16 |
| Chạy và triển khai | Docker + Docker Compose, Caddy 2 (HTTPS tự động) |

**Máy hiện tại:** đã có Git, Python 3.12, Node 24. **Chưa có Docker và uv.**
- Cần cài Docker Desktop để chạy PostgreSQL và môi trường giống production. Đây là việc duy nhất anh/chị phải tự làm.
- uv tôi sẽ cài bằng `pip` ở slice S0.

## 3. Thứ tự làm (theo CLAUDE.md §9 GĐ4)

Mỗi slice làm xong thì chạy được và có test. Hết mỗi slice tôi báo: đã thay đổi gì, kết quả test thật, và chờ anh/chị trả lời "tiếp".

| Slice | Nội dung | Excel ID chính | Xong khi |
|---|---|---|---|
| **S0 Nền móng** | `git init`, cấu trúc repo, uv/npm, lint, Docker Compose (db), Alembic khung, CI khung, **sinh rule catalog từ Excel** + test đủ 130 ID | — | CI xanh; `catalog.json` có đủ 130 ID |
| **S1 Admin + luật global** | Bảng admin/rules/audit; CLI tạo Admin; login/logout; RuleConfig + validator V1–V10; draft → validate → diff → publish → rollback; trang Admin Rules Dashboard; trang xem luật công khai | 134–138, 156 + toàn bộ cấu hình | Guest gọi API ghi luật bị 403; publish/rollback có audit; hai Admin sửa cùng lúc thì một người nhận 409 |
| **S2 Guest + phòng** | Nickname + token; tạo phòng, mã/link mời, vào ghế, ready, rời, đóng phòng; WS `room.state`, presence; giữ ghế 120s ngoài ván; trang Home, Lobby, Phòng chờ | 2, 139, 140, 143, 144, 146, 147 | 4 trình duyệt vào cùng phòng, ready đủ thì phòng chuyển sang "bắt đầu" |
| **S3 Engine + test** | Toàn bộ `tlmn_engine`: nhận diện bộ, so bài, ma trận chặt, reducer, hưởng sái, cóng, thối, tới trắng, chia lại, đút mù, bị nhốt 3♠, timeout, thoát ván, tính điểm, projection | 1–133 | Có test cho từng ID; property test ≥ 10.000 ván; 9 ví dụ đối soát đúng; độ phủ engine ≥ 90% |
| **S4 Chơi realtime** | RoomActor, pipeline lưu DB trước rồi mới gửi, idempotency, `baseSeq`, timer 30s, tự pass / tự đánh lá nhỏ nhất, chặt ngoài lượt; snapshot luật vào ván; bàn chơi desktop và mobile | 10–14, 42, 136, 137, 141, 142, 145, 151–153, 156 | 4 client chơi trọn một ván; gửi trùng lệnh không bị xử lý 2 lần; publish luật giữa ván không ảnh hưởng ván đang chơi |
| **S5 Điểm + lịch sử** | Lưu từng khoản chuyển điểm, bảng điểm phiên, màn kết quả ván (giải thích từng khoản), lịch sử phiên, khởi động lại phiên, đổi người = phiên mới | 111–133, 148, 150 | Điểm trong DB khớp kết quả engine; ván bị hủy không được tính điểm |
| **S6 Khôi phục + xem lại** | Snapshot + event, khôi phục khi server khởi động lại, reconnect gửi bài riêng đúng người, replay sau ván, kiểm chứng bộ bài, API tranh chấp cho Admin | 143, 149, 154, 155 | Tắt server giữa ván rồi bật lại, ván chơi tiếp đúng; replay không lộ bài khi ván chưa kết thúc |
| **S7 Hoàn thiện** | Rate limit, CSRF, header bảo mật, lọc log, test lộ bài, E2E đầy đủ, load test 100 bàn, backup/restore, hướng dẫn vận hành | 151–153, 155 | Checklist bảo mật đạt; E2E xanh; diễn tập backup/restore thành công |

GĐ5 (QA/Deploy theo CLAUDE.md) đi sau S7: chạy lại E2E, load/race, kiểm tra restart, triển khai thật, hướng dẫn vận hành và rollback.

## 4. Danh sách việc chi tiết

<details><summary>S0 — Nền móng</summary>

- `git init`, `.gitignore`, `.editorconfig`, README chạy local
- `engine/`, `backend/`: `pyproject.toml` (uv), ruff, mypy, pytest
- `frontend/`: Vite React TS, ESLint, vitest
- `deploy/docker-compose.dev.yml`: PostgreSQL 16 + volume
- Alembic khởi tạo, migration rỗng đầu tiên
- `tools/gen_rule_catalog.py` (đọc Excel bằng openpyxl) + test: đủ 130 ID, không trùng, khớp Phụ lục A
- `tools/check_rule_trace.py` (lúc đầu chỉ báo cáo, không làm fail CI)
- CI: lint → test engine → test backend (service PostgreSQL) → build frontend
</details>

<details><summary>S1 — Admin + luật global</summary>

- Model + migration: admin_users, admin_sessions, global_rule_versions, rule_audit_logs (kèm trigger/quyền append-only)
- Lệnh CLI `create-admin`
- Login (argon2id, khóa tạm khi sai nhiều lần), session cookie, CSRF
- `RuleConfig` + invariants + validator V1–V10 trong engine (có test)
- Seed version 1 = cấu hình mặc định đã duyệt
- API draft/validate/diff/publish/rollback/audit với optimistic lock
- UI: Admin Login, Rules Dashboard (tab theo nhóm, toggle/select/number/bảng/kéo thả), Diff, Publish dialog, Versions, Audit
- UI công khai `/rules` (chỉ xem, tooltip mô tả lấy từ Excel)
</details>

<details><summary>S2 — Guest + phòng</summary>

- Model: guest_players, rooms, room_seats, game_sessions
- API guest/room; mã phòng 6 ký tự; chặn một guest ngồi 2 phòng
- WS gateway: auth bằng message, kiểm tra Origin, envelope, rate limit, `room.state`, `presence`, `room.ready`
- Giữ ghế 120s (ngoài ván), chủ phòng đóng phòng, tất cả rời thì đóng phòng
- UI: Home, Lobby, Phòng chờ, banner kết nối lại
</details>

<details><summary>S3 — Engine</summary>

- cards/combos/compare (+ bảng so 52×52)
- Ma trận chặt + điều kiện lượt + `can_interrupt`
- Reducer: mở vòng, đè, pass, khóa sau khi pass, đóng vòng, hưởng sái, người hết bài, cóng, thoát ván, timeout (tự pass / tự đánh)
- Tới trắng (ưu tiên, chia tiền khi cùng loại), chia lại, ván sau tới trắng mở 3♣
- Thối (tách bài cho tổng phạt lớn nhất), đút mù, bị nhốt 3♠
- Scoring: các khoản chuyển điểm + chuỗi chặt cộng dồn
- Projection public/private
- Invariants + property test + 9 fixture đối soát; marker `@pytest.mark.rule(id)`; bật check 130/130 làm fail CI
</details>

<details><summary>S4 → S7</summary>

Theo đúng bảng §3. Danh sách việc chi tiết của các slice này sẽ được bổ sung trong báo cáo cuối slice trước, để phản ánh những gì học được.
</details>

## 5. Môi trường

| Môi trường | Cách chạy | Dữ liệu |
|---|---|---|
| **Local** (máy anh/chị) | `docker compose -f deploy/docker-compose.dev.yml up db` + `uv run uvicorn` (tự reload) + `npm run dev` (Vite proxy `/api`, `/ws`) | DB local, seed Admin + luật v1 |
| **Dev / Staging** | 1 VPS, `docker compose up -d` (caddy + api + db), deploy thủ công từ nhánh `main` | Dữ liệu thử, có thể xóa |
| **Production** | 1 VPS (2 vCPU, 4 GB RAM là đủ), Docker Compose, Caddy HTTPS tự động theo tên miền | Backup hằng ngày, giữ 14 bản, có bản ngoài máy |

Cấu hình qua biến môi trường (`DATABASE_URL`, `ALLOWED_ORIGINS`, `SESSION_SECRET`…). Secret không commit vào git; có file `.env.example`.

## 6. CI (GitHub Actions; đổi sang GitLab CI dễ dàng nếu công ty dùng GitLab)

```
on: push, pull_request
jobs:
  lint:      ruff · mypy(engine) · eslint · tsc --noEmit
  engine:    pytest engine (unit + property) · coverage ≥ 90% · check_rule_trace 130/130
  backend:   service postgres:16 · alembic upgrade head · pytest backend (API + WS)
  frontend:  vitest · vite build
  e2e:       (từ S4) docker compose up · Playwright 4 người chơi · desktop + mobile viewport
  images:    (nhánh main) build api.Dockerfile, web.Dockerfile, gắn tag theo commit
```

## 7. Triển khai và rollback

1. Build image `api` và `web` theo tag commit.
2. Trên server: `pg_dump` trước khi nâng cấp → `docker compose run api alembic upgrade head` → `docker compose up -d`.
3. Kiểm tra `/api/health` (DB + số phòng đang chơi).
4. **Rollback:** chạy lại image tag cũ. Migration chỉ thêm, không xóa cột trong cùng một lần phát hành, nên bản cũ vẫn chạy được trên DB mới. Nếu bắt buộc phải lùi DB thì restore bản `pg_dump` vừa tạo.
5. Nâng cấp khi đang có ván: server khôi phục ván sau khi khởi động (S6), người chơi được cấp lại thời gian lượt (G5).

## 8. Cách tôi báo cáo mỗi slice

- Danh sách file thay đổi chính và tóm tắt.
- **Kết quả test thật** (số test pass/fail, độ phủ), không tuyên bố thành công nếu chưa chạy.
- Những gì chưa làm hoặc phát sinh (nếu có), đề xuất cách xử lý.
- Dừng lại chờ anh/chị trả lời "tiếp".
- Commit git cuối mỗi slice (chỉ commit local; chỉ push khi anh/chị yêu cầu).

**Khi GĐ3 được duyệt, tôi bắt đầu S0.**

## 9. Tiến độ triển khai (GĐ4)

| Slice | Commit | Ghi chú |
|---|---|---|
| S0 Nền móng | `bdc9884` | |
| S1 Admin + luật global | `0dd3740` | |
| S2 Guest + phòng | `a6ba263` | |
| S3 Engine | `da5a098` | 10.000 ván ngẫu nhiên đạt bất biến |
| S4 Chơi realtime | `d8edfc5` | |
| S5 Điểm + lịch sử | `defea08` | |
| S6 Khôi phục + xem lại | `602bc14` | Khôi phục ván sau khi tắt hẳn server |
| S7 Hoàn thiện | (commit S7) | Hardening, Docker, sao lưu/khôi phục, E2E Playwright, kiểm thử tải — xem [runbook](../runbook.md) |

Rule trace 130/130 Excel ID. Bước tiếp theo theo CLAUDE.md: **GĐ5 QA/Deploy**.
