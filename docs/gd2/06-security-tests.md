# GĐ2.6 — Bảo mật và Test matrix

## 1. Threat model → biện pháp

| Mối đe dọa | Biện pháp |
|---|---|
| Nghe lén / MITM | TLS bắt buộc (Caddy, HSTS); WS chỉ chạy `wss` |
| Lộ bài đối thủ | Mọi dữ liệu gửi client chỉ đi qua `project_public` / `project_private`; replay và `game.ended` mới lộ bài; test tự động quét payload (AC3) |
| Client gian lận nước đi | Server-authoritative; client chỉ gửi danh sách `card_id`; server kiểm tra bài có trong tay, đúng lượt, đúng luật |
| Gửi lặp / replay lệnh | `requestId` + `command_dedup`; `baseSeq` → `STALE_STATE` |
| Race condition | Lock theo phòng; `UPDATE … WHERE last_seq = :old`; partial unique index (1 ván đang chơi/phòng, 1 ACTIVE rule, 1 draft) |
| Chiếm token guest | Token 256-bit, chỉ lưu sha256; không đặt trong URL; hết hạn 30 ngày không hoạt động; kết nối mới đẩy kết nối cũ |
| Tấn công đăng nhập Admin | argon2id; rate limit + lockout; cookie `HttpOnly/Secure/SameSite=Strict`; CSRF token; session thu hồi được; không có trang đăng ký Admin (tạo qua CLI) |
| Leo quyền sửa luật | Mọi endpoint ghi luật yêu cầu Admin session; test 403 cho Guest/chủ phòng (AC4); audit log append-only |
| Server bị nghi xáo bài gian | Deck commitment công bố khi chia, lộ salt sau ván |
| Payload độc / DoS | Pydantic strict, `extra=forbid`; giới hạn kích thước REST 64 KB, WS 4 KB; rate limit theo IP/guest/kết nối; mỗi guest chỉ ngồi 1 phòng chưa đóng; tạo phòng tối đa 10 lần/giờ/guest |
| Dò mã phòng | Mã 6 ký tự (~1 tỷ tổ hợp), rate limit join, phòng đóng thì mã bị giải phóng |
| XSS qua nickname | React tự escape; nickname giới hạn 2–20 ký tự chữ/số/khoảng trắng Unicode, chặn ký tự điều khiển; CSP `default-src 'self'` |
| CSWSH (WS cross-site) | Kiểm tra `Origin` + auth bằng message (không dựa vào cookie) |
| Rò rỉ qua log | Filter redaction; không log body lệnh `game.play` ở mức INFO; log lỗi không kèm token |
| Mất dữ liệu | Backup `pg_dump` hằng ngày, giữ 14 bản; diễn tập restore ở GĐ5 |

## 2. Các cấp độ kiểm thử

| Cấp | Công cụ | Phạm vi |
|---|---|---|
| Unit engine | pytest | Từng Excel ID (marker `@pytest.mark.rule(id)`), từng ô của bảng quyết định chặt, scoring |
| Property-based | Hypothesis | Ván ngẫu nhiên với nước đi hợp lệ ngẫu nhiên, kiểm các invariant |
| Trace coverage | Script CI | Đọc rule catalog + marker; fail nếu ID nào thiếu test (AC1: 130/130) |
| Integration API | pytest + httpx + PostgreSQL thật (Docker) | Admin workflow, phân quyền, optimistic lock, history |
| Integration realtime | pytest + 4 client WS | Ván đầy đủ, reconnect, nước đi đồng thời, chặt ngoài lượt, restart |
| E2E | Playwright (4 browser context, desktop + mobile viewport) | Home → bàn → kết quả → ván tiếp (AC9) |
| Load / race | Locust hoặc k6 | 100 bàn đồng thời; spam cùng lệnh; p95 thời gian ack < 150 ms |
| Security | Test tự động + checklist OWASP ASVS L1 | 403, CSRF, rate limit, quét payload lộ bài, header bảo mật |

## 3. Property / invariant (Hypothesis, ≥ 10.000 ván — AC2)

| # | Invariant |
|---|---|
| P1 | Sau mỗi action: 52 lá không trùng, không mất (tay + đã đánh) |
| P2 | Chỉ `currentSeat` được hành động, trừ PS4 chặt ngoài lượt hợp lệ |
| P3 | Tổng transfer mỗi ván = 0; tổng phiên = tổng các ván FINISHED |
| P4 | `project_private(state, s)` không chứa lá nào ngoài tay của s và các lá đã đánh |
| P5 | Replay events từ đầu cho ra đúng `state_hash` cuối |
| P6 | Ván luôn kết thúc: chỉ dùng timeout thì ván kết thúc sau hữu hạn bước (D13) |
| P7 | Rank là một hoán vị của 1..4 khi ván kết thúc NORMAL |
| P8 | Áp dụng một action 2 lần (cùng requestId) không làm đổi state |

## 4. Test matrix theo nhóm luật

| Nhóm (Excel ID) | Kịch bản bắt buộc (ngoài 1 test/ID) |
|---|---|
| Cơ bản 1–16 | Mở ván bằng 3♣ (bao gồm 3♣ nằm trong sảnh/đôi); người mở vòng không được pass; khóa sau khi pass; người thắng ván trước mở ván |
| So sánh 17–27 | Bảng 52×52 lá đơn; đôi cùng số khác chất; sảnh cùng độ dài so chất lá cao; sảnh chứa 2 bị từ chối; không đè khác loại |
| Chặt 29–48 | Mỗi ô ma trận (bật/tắt cờ); tứ quý/3 đôi thông ngoài lượt bị từ chối; PS4 ngoài lượt sau khi đã pass; 2 lệnh chặt cùng lúc → một lệnh nhận `STALE_STATE`; đôi 2 đè đôi 2 |
| Tới trắng / chia lại 49–67 | Từng loại; 2 người cùng tới trắng khác cấp và cùng cấp; tới trắng + tứ quý 3 cùng lúc (R7); ván sau tới trắng mở 3♣ + chia lại; 6 đôi có tứ quý |
| Phạt / thưởng 68–90 | Cóng 1/2/3 người kèm thối; thối tứ quý 2; thối 6 đôi thông (G4); chặt chồng 3 tầng; A bị chặt rồi chặt lại; đút mù; đút mù khi không về nhất (không tính) |
| Kết thúc 99–109 | Hưởng sái khi người về nhất/nhì đánh lá cuối; người hết bài bị bỏ qua; hủy ván loại điểm |
| Điểm 111–133 | 7 ví dụ đối soát ở [03 §7](03-engine-state-scoring.md); V1 chặn bộ điểm hạng không đối xứng |
| Phòng online 134–156 | Guest gọi API ghi luật → 403; publish khi đang có ván (AC5); rollback; ready/auto-start; timeout tự pass và tự đánh; giữ ghế 120s; thoát lần lượt (D9); đổi người → phiên mới; replay chỉ sau khi ván kết thúc; restart server giữa ván (AC7) |
