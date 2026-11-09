# Lớp học Thầy Trung — Tiến Lên Miền Nam

Bản Render Free dùng RAM, không PostgreSQL, Redis, SQLite hay dịch vụ lưu trữ ngoài.
Source được khôi phục từ ZIP gốc và cập nhật các bản sửa trong `giaitri-main (1).zip`: chat ngắn tự do/câu mẫu, kéo thả xếp bài, giao diện điện thoại dọc/ngang, popup luật/thông tin và đổi tên ở sảnh. Sau đút mù 3♠, ván tiếp theo mở bằng 3♣ theo bản sửa mới. Kiến trúc Render Free/RAM được giữ nguyên.

## Chơi online

- Nhập tên, không đăng ký tài khoản. Tạo phòng và chia sẻ mã 6 ký tự hoặc link `/r/MAPHONG`.
- Mỗi phòng 3 hoặc 4 ghế; tối đa 20 người đang ngồi trên toàn server. Ghế mất kết nối được giữ 120 giây.
- Đủ người theo số ghế đã chọn kết nối và sẵn sàng thì chia bài. Server kiểm tra mọi nước đánh bằng engine gốc.
- HTTPS, REST và WebSocket cùng domain. Client tự chọn `wss://` khi trang dùng HTTPS.
- 00:00 Asia/Tokyo: xóa phòng chờ và dữ liệu ngày cũ. Phòng đang chơi chốt ván rồi đóng/xóa; không bắt đầu ván mới ở phòng đó. Phòng tạo trong ngày mới không bị lần reset đang chờ ảnh hưởng.
- Bộ cấu hình luật v1 được cố định; quy tắc mở ván sau đút mù 3♠ áp dụng bản sửa mới. API Admin/đăng nhập và chỉnh luật không được bật trong bản RAM public; mã PostgreSQL cũ còn lại trong repo chỉ để tham khảo, không được cài hay chép vào image production.
- Lịch sử/replay chỉ tạm: giữ tối đa 100 ván và 100 phiên để giới hạn RAM. Chỉ thành viên được đọc; không được xem bài người khác khi ván đang chơi.

## Chạy và kiểm thử

Python 3.12+, uv, Node 22+:

```bash
uv sync --all-packages --locked
cd frontend
npm ci
npm run build
npm test
cd ..
uv run pytest
uv run python tools/smoke_memory.py
uv run uvicorn app.main:app --host 0.0.0.0 --port 10000 --workers 1 --ws-max-size 4096 --ws-max-queue 16 --no-access-log
```

`tools/smoke_memory.py` tự chạy ASGI production rồi kết nối **4 client WebSocket TCP thật**, chơi trọn ván, kiểm tra bài riêng, tổng điểm 0 và replay hash. Có thể chạy với URL public:

```bash
uv run python tools/smoke_memory.py https://TEN-DICH-VU.onrender.com
```

Với Docker:

```bash
docker compose -f deploy/docker-compose.yml up --build
# http://localhost:8080
```

Kiểm thử trình duyệt desktop/mobile (sau khi server chạy):

```bash
cd frontend
npx playwright install chromium
E2E_BASE_URL=http://localhost:8080 npm run e2e
```

CI chạy Python, frontend, build Docker và test 4 trình duyệt (một iPhone giả lập). `backend/tests` là test PostgreSQL nguyên bản, không còn thuộc bộ test mặc định; bản RAM kiểm thử tại `backend/memory_tests`.

## Render Free

Dùng `render.yaml`: một Web Service Docker, **plan: free**, Singapore, nhánh `feature/render-free-memory`, health check `/api/health`. Không có DB, disk, cron hay worker trả phí. Không cần secret. Auto-deploy tắt để tránh reset bất ngờ giữa ván; deploy thủ công khi không có người chơi.

Một worker Uvicorn là bắt buộc vì trạng thái nằm trong RAM. Không thêm workers/replicas.

### Thống kê khách theo giờ Nhật

Trong Render Dashboard, mở **Logs** của web service và lọc `TLMN_GUEST_LOGIN`.
Mỗi dòng chứa `hour_jst` và tương ứng với một phiên khách được tạo hoặc xác thực
thành công trong giờ đó. Tải lại trong cùng giờ không đếm lại cùng phiên. Người
chỉ xem trang chưa có phiên, hoặc tiếp tục chơi trong phòng đã mở mà không xác
thực lại hồ sơ, không được tính trong giờ mới.

Đây là số phiên khách theo giờ, không phải số người duy nhất trong ngày: cùng
một người có thể dùng nhiều trình duyệt hoặc tạo lại phiên sau khi server reset.
Dòng thống kê không chứa tên, địa chỉ IP, mã phòng, ID khách hay token. Số liệu
chỉ có từ lúc tính năng được deploy và tuân theo thời hạn giữ log của Render
(7 ngày với workspace Hobby). Xem [Render Logs](https://render.com/docs/logging).

### Giới hạn cần biết

- Render có thể restart bất kỳ lúc nào; sleep, restart hoặc deploy sẽ mất toàn bộ RAM, kể cả ván đang chơi. Cam kết “chơi hết ván rồi reset” áp dụng cho reset ngày do ứng dụng quản lý, không thể bảo đảm khi nền tảng dừng máy.
- Free ngủ sau 15 phút không có HTTP/WebSocket message; lần mở tiếp có thể mất khoảng một phút. Không dùng keep-alive bên ngoài để né giới hạn Free.
- Free có 750 giờ/tháng cho toàn workspace; nhiều dịch vụ cùng chia giờ này.
- **Free compute không tự bảo đảm mọi khoản đều 0** nếu tài khoản có phương thức thanh toán: bandwidth và build minutes vượt mức có thể phát sinh phí. Cần kiểm tra Billing/spend limit và included usage trước khi xác nhận tổng chi phí 0 JPY. Không thêm thẻ hoặc nâng gói tự động.
- Chưa có URL public cho tới khi Render báo deploy `live` và kiểm thử trên URL đó đạt. Tài liệu này không thay thế xác nhận deploy.

Tài liệu chính thức: [Free](https://render.com/docs/free), [Compute plans](https://render.com/docs/compute-plans), [Blueprint](https://render.com/docs/blueprint-spec).
