# Hướng dẫn vận hành — Lớp học Thầy Trung

Dành cho người triển khai và vận hành hệ thống. Kiến trúc: [GĐ2](gd2/README.md) · Kế hoạch: [GĐ3](gd3/GD3-Plan.md).

## 1. Thành phần

| Dịch vụ (docker compose) | Vai trò |
|---|---|
| `web` | Caddy: HTTPS tự động, phục vụ giao diện, chuyển `/api/*` và `/ws/*` sang `api` |
| `api` | FastAPI + rules engine, **1 tiến trình** (giữ trạng thái ván trong bộ nhớ, ghi DB trước khi gửi cho người chơi) |
| `db` | PostgreSQL 16 (volume `pgdata`) |
| `backup` | `pg_dump` định kỳ (mặc định mỗi ngày, giữ 14 ngày) vào `BACKUP_DIR` |

Yêu cầu máy chủ: 2 vCPU, 4 GB RAM, Docker + Docker Compose, tên miền trỏ về IP máy chủ, mở cổng 80 và 443.

## 2. Triển khai lần đầu

```bash
git clone https://github.com/manh-elnino/tienlenmiennam.git && cd tienlenmiennam
cp deploy/.env.example deploy/.env      # sửa: POSTGRES_PASSWORD (dài, ngẫu nhiên), SITE_ADDRESS, ALLOWED_ORIGINS
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.cli create-admin --username admin
```

- Lần chạy đầu, `api` tự chạy migration và tự tạo bộ luật v1 từ cấu hình mặc định đã duyệt.
- Với `ENVIRONMENT=production`, server **từ chối khởi động** nếu `COOKIE_SECURE` tắt, `ALLOWED_ORIGINS` có `http://`, hoặc DB dùng mật khẩu mặc định.
- Trang Admin: `https://<tên miền>/admin` (không có trang đăng ký; tài khoản tạo bằng lệnh `create-admin`).

## 3. Kiểm tra sức khỏe

`GET /api/health`:

```json
{"status": "ok", "db": "ok", "liveGames": 3, "commandLatency": {"count": 5000, "p50Ms": 17.7, "p95Ms": 66.5, "p99Ms": 168.4}}
```

- `status: degraded` / `db: unavailable` → kiểm tra container `db`.
- `commandLatency` = thời gian server xử lý một nước đi (nhận lệnh → đã ghi DB → gửi xác nhận), tính trên 5.000 lệnh gần nhất. Mục tiêu p95 < 150 ms.
- Log (`docker compose logs api`) ở dạng JSON khi không phải môi trường `local`; token, cookie, mật khẩu và bài trên tay được che (`***`).

## 4. Sao lưu và khôi phục

```bash
# Sao lưu ngay (ngoài lịch tự động):
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec backup sh /scripts/backup-once.sh
# Khôi phục vào DB riêng để kiểm tra (KHÔNG đụng DB đang chạy), in số dòng các bảng chính:
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec backup sh /scripts/restore.sh /backups/tlmn-<thời gian>.dump tlmn_restore
```

**Khôi phục thật sau sự cố** (mất dữ liệu):
1. Khôi phục bản gần nhất vào `tlmn_restore` như trên, kiểm tra số liệu.
2. `docker compose ... stop api` → trong `db`: `ALTER DATABASE tlmn RENAME TO tlmn_broken; ALTER DATABASE tlmn_restore RENAME TO tlmn;`
3. `docker compose ... start api` → kiểm tra `/api/health`.

Nên chép thư mục `BACKUP_DIR` sang nơi lưu trữ khác máy chủ (ổ khác / object storage). Đã diễn tập: sao lưu → khôi phục vào DB riêng → số dòng `games`, `game_events`, `score_transfers`, `global_rule_versions` khớp với DB gốc.

## 5. Nâng cấp phiên bản và quay lại

```bash
git pull
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec backup sh /scripts/backup-once.sh   # luôn sao lưu trước
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

- **Ván đang chơi không mất** khi `api` khởi động lại: server dựng lại ván từ snapshot + log, kiểm tra hash, đánh dấu mọi người "mất kết nối" (giữ ghế 120 giây) và cấp lại đủ thời gian cho lượt hiện tại. Người chơi chỉ cần chờ trình duyệt tự kết nối lại.
- Nếu một ván không dựng lại được (log không khớp hash) thì ván đó bị **hủy, không tính điểm** (log `Không khôi phục được ván …`); các ván khác vẫn chạy.
- **Quay lại bản cũ:** `git checkout <commit cũ>` rồi `up -d --build`. Migration chỉ thêm bảng/cột nên bản cũ chạy được trên DB mới. Nếu bắt buộc phải lùi DB thì khôi phục bản sao lưu vừa tạo (mục 4).

## 6. Xử lý tình huống

| Tình huống | Cách xử lý |
|---|---|
| Người chơi khiếu nại kết quả | Admin → **Đối soát ván** → nhập mã ván: hệ thống kiểm tra lại bộ bài (so với mã công bố lúc chia), luật của ván, log từng bước và điểm đã lưu. Người chơi tự xem lại ván ở trang lịch sử → "Xem lại" |
| Ván bị kẹt / cần hủy | `POST /api/admin/games/{gameId}/cancel` (đã đăng nhập Admin): điểm của ván không được tính, có ghi nhật ký |
| Sai luật đang áp dụng | Admin → Phiên bản → "Quay lại phiên bản này" (tạo phiên bản mới, áp dụng từ ván tiếp theo) |
| Nghi bị dò mã phòng / spam | Giới hạn sẵn: tạo phòng 10/giờ/khách, tra cứu & vào phòng 30/phút/IP, đăng nhập Admin 5/phút/IP (khóa 15 phút sau 10 lần sai), WebSocket 10 lệnh/giây/kết nối |
| Đổi mật khẩu Admin / thêm Admin | `exec api python -m app.cli create-admin --username <tên mới>` (vô hiệu hóa tài khoản cũ trực tiếp trong DB: `UPDATE admin_users SET is_active=false WHERE username='...'`) |

## 7. Kiểm thử tải

```bash
ROOM_LOOKUP_PER_MINUTE=100000 docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d api   # nới giới hạn theo IP khi test
uv run python tools/loadtest.py --base http://localhost:8080 --tables 100
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d api   # trả lại giới hạn mặc định
```

Kết quả đo trên máy phát triển (Windows, Docker Desktop, công cụ đo và server cùng máy) — 100 bàn, 400 WebSocket, 7.594 lệnh, 100/100 ván xong, 0 lỗi:

| | p50 | p95 | p99 |
|---|---|---|---|
| Server tự đo (`/api/health`) | 17,7 ms | 66,5 ms | 168 ms |
| Phía công cụ đo (qua Caddy + mạng Docker Desktop) | 25,5 ms | 637 ms | 2,2 s |

Đuôi dài phía công cụ đo chủ yếu do một tiến trình Python trên Windows gánh 400 kết nối cùng máy với server; cần đo lại từ máy riêng trên hạ tầng thật (GĐ5).

## 8. Giới hạn hiện tại

- **Một tiến trình `api`**: không chạy nhiều bản song song (khóa theo phòng nằm trong bộ nhớ). Mở rộng ngang cần định tuyến theo phòng + Redis pub/sub (ADR-003).
- Tài khoản Admin chưa có 2FA.
- Giờ trên đồng hồ lượt được bù theo giờ server khi kết nối; nếu máy người chơi đổi giờ giữa chừng thì hiển thị có thể lệch tới lần kết nối sau (server vẫn là nơi quyết định hết giờ).
