# GĐ2 — Design: Tiến Lên Miền Nam Online

- Trạng thái: **ĐÃ DUYỆT (2026-10-30)**
- Đầu vào: [GĐ1 Discovery (đã duyệt)](../gd1/GD1-Discovery.md) với D1–D15, [Phụ lục A](../gd1/A-rule-inventory.md) gồm 130 ID

| Tài liệu | Nội dung |
|---|---|
| [01-architecture-erd.md](01-architecture-erd.md) | Kiến trúc, 15 ADR, ERD 15 bảng, khóa/index, chống cộng điểm trùng, retention, quyền đọc |
| [02-ruleconfig.md](02-ruleconfig.md) | RuleConfig schema theo nhóm Excel, invariants, validation V1–V10, migration, quy trình draft → validate → diff → publish → rollback |
| [03-engine-state-scoring.md](03-engine-state-scoring.md) | Mã hóa lá bài, engine API, bảng quyết định chặt, state machine (phòng/ghế/ván/người chơi), pseudo-code trường hợp biên, thối, scoring ledger + 9 ví dụ đối soát |
| [04-api-realtime-recovery.md](04-api-realtime-recovery.md) | REST API, WebSocket envelope/message/error code, idempotency, pipeline commit-trước-broadcast, timer, recovery sau restart, reconnect, log tranh chấp |
| [05-ui.md](05-ui.md) | Sitemap, wireframe desktop/mobile, các màn hình, trạng thái loading/reconnect/timeout, component tree |
| [06-security-tests.md](06-security-tests.md) | Threat model, các cấp kiểm thử, invariant cho property test, test matrix theo nhóm luật |

## Quyết định mặc định (tôi tự chọn — anh/chị không cần trả lời, chỉ sửa nếu thấy sai)

### Theo ảnh "Luật Tiến Lên Miền Nam – Luật bản" (2026-10-30)

| Mã | Quyết định | Nguồn |
|---|---|---|
| N1 | Ưu tiên tới trắng: **4 heo > sảnh 3→A > 6 đôi** (Admin chỉnh được) | Ảnh §6 (mới hơn Excel ID 62) |
| N2 | Nhiều người tới trắng **cùng loại → chia tiền**: mỗi người không tới trắng trả 200, chia đều cho những người tới trắng | Ảnh §6 (thay Excel ID 63) |
| N3 | Về chót vẫn bị thối **tứ quý** 200 như đã chốt ở D8 (ảnh §8 thiếu tứ quý, tôi coi là sót) | D8 |
| N4 | Mục 3.1/3.3 của ảnh là **3♠** (tiêu đề ghi ♣ là gõ nhầm) | Nội dung ảnh |
| N5 | Xét tới trắng trước, không có ai tới trắng mới xét chia lại | Ảnh §2 + GĐ1 R7 |
| N6 | **Bị nhốt 3♠**: người về chót còn đúng 1 lá 3♠ → trả **200 cho mỗi người** còn lại, cộng thêm tiền bét (Admin chỉnh mức) | Ảnh §3.3 (luật mới, không có Excel ID) |

### Kỹ thuật

| Mã | Quyết định | Lý do |
|---|---|---|
| G1 | Điểm hạng đối xứng: nhất = −bét, nhì = −ba | Để tổng điểm luôn bằng 0 khi có người cóng |
| G2 | Ván luôn chơi đến khi còn 1 người (ID 103/104 cố định) | Đúng Excel E (103 = Không, 104 = Có) |
| G3 | ID 46, 47 luôn bật | Đúng Excel D ("Cho phép") |
| G4 | Thối hàng: tách bài sao cho tổng phạt lớn nhất, không tính trùng lá | Tránh tranh cãi |
| G5 | Server khởi động lại → lượt hiện tại được cấp lại đủ thời gian | Không phạt người chơi vì lỗi server |
| G6 | Rollback luật = tạo phiên bản mới | Lịch sử luật rõ ràng |
| G7 | Công bố mã kiểm chứng bộ bài lúc chia, sau ván cho kiểm tra | Chống nghi ngờ gian lận (ID 153, 155) |
| G8 | Ván sau ván bị hủy mở bằng 3♣ | Không có người thắng |
| G9 | Lệnh gửi dựa trên trạng thái cũ bị từ chối | Tránh chặt nhầm |
| G10 | Thối của người về chót trả cho người về 3; nếu người hạng 3 là người cóng/thoát thì trả cho người nhất | Trường hợp nhiều người thoát |
| G11 | ID 74 = tổng 2 heo; ID 69 chỉ là nhãn hiển thị | Theo D8/D12 không làm khác điểm |
| G12 | Người chặt ngoài lượt bằng 4 đôi thông được tham gia lại vòng đó | Hợp lý khi bị chặt lại |
| G13 | Chạy 1 server; mở rộng nhiều server khi cần | Đơn giản, đủ dùng |
| G14 | Lưu lịch sử ván 365 ngày, audit luật vĩnh viễn | Đủ để xử lý tranh chấp |

**Xác nhận cách tính điểm (2026-10-30):** người dùng đã xác nhận đúng 4 ví dụ: chặt heo, thối, 1 người cóng, 2 người cóng. Mọi khoản phạt là chuyển điểm từ người này sang người kia, nên tổng 4 người mỗi ván luôn bằng 0. Bảng điểm hạng 200/100/−100/−200 chỉ giữ nguyên dạng ở ván bình thường; khi có cóng/thối/chặt, điểm từng người thay đổi nhưng tổng vẫn bằng 0.

Phân loại các ID 46, 69, 74, 103, 104 trong Phụ lục A sẽ được cập nhật theo G2, G3, G11.

**Bước tiếp theo:** anh/chị chỉ cần trả lời **"duyệt GĐ2"** (hoặc chỉ ra chỗ muốn sửa). Sau đó tôi làm GĐ3 Plan (cấu trúc thư mục, danh sách việc, thứ tự làm, môi trường chạy, triển khai) rồi dừng xin duyệt. Chưa viết code.

## Ghi chú khi triển khai S3 (engine)

- **3♣ bắt buộc ở nước đầu (ID 8)** chỉ áp dụng khi người đi đầu đang giữ 3♣. Nếu người giữ 3♣ thoát ván trước khi đánh, người kế tiếp được đánh tự do (trước đây ván bị kẹt vĩnh viễn — phát hiện nhờ chạy 2.000 ván ngẫu nhiên).
- **Thối hàng (G4):** khi hai cách tách cho cùng số tiền, ưu tiên cách dùng nhiều lá hơn (vd ghi nhận "4 đôi thông" thay vì "3 đôi thông" bên trong).
- **Chia tiền tới trắng (N2):** phần dư khi chia không chẵn trả hết cho người thắng gần người mở ván nhất (vd 3 người cùng tới trắng: 68/66/66).
