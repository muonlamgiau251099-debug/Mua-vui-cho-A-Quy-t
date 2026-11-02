# GĐ1 — Discovery: Tiến Lên Miền Nam Online

- Trạng thái: **ĐÃ DUYỆT (2026-10-29)** — luật, phạm vi, tiêu chí nghiệm thu và phân loại ruleKey
- Nguồn: `Cau_hinh_luat_Tien_Len_Mien_Nam.xlsx` (bản lưu 2026-10-29 16:19), `CLAUDE.md` (Master Prompt v1.3), câu trả lời duyệt vòng 1
- Phụ lục A (130 ID → ruleKey, phân loại, default, trạng thái): [A-rule-inventory.md](A-rule-inventory.md)

Quy ước nhãn: **[Excel]** dữ kiện từ file · **[Yêu cầu]** CLAUDE.md · **[Duyệt Dn]** quyết định của người duyệt · **[Giả định]/[Đề xuất]** của tôi, chờ duyệt.
Thứ tự ưu tiên: yêu cầu mới nhất > quyết định đã duyệt > Excel > đề xuất.

---

## 1. Dữ kiện từ file Excel

| Hạng mục | Kết quả kiểm đếm |
|---|---|
| Sheet | 1 sheet `Cấu hình luật`, 138 hàng × 6 cột, header ở hàng 4 |
| Hàng ẩn / cột ẩn / comment / data validation | Không có |
| Tiêu đề | "DANH SÁCH 156 LUẬT" — **thực tế 130 ID**, không trùng |
| ID khuyết (26) | 20, 28, 40, 45, 50, 51, 54–57, 61, 78, 79, 86, 91–98, 108, 110, 116, 126 — **không tự tạo** |
| Cột E | 34/130 có giá trị; 96 trống |
| Cột F | Trống toàn bộ |

**Thay đổi Excel trong vòng 1 (bản lưu 16:19):**

| ID | Thay đổi |
|---|---|
| 43 | Tên: "3 đôi thông cần vòng" → "3 đôi thông/ tứ quý cần vòng" |
| 58 | D: chia lại khi có tứ quý 3 **ở ván bắt buộc đánh 3♣ đầu tiên (ván đầu hoặc ván sau tới trắng)** |
| 59 | D: tương tự 58, với 3 hoặc 4 đôi thông chứa 3♣ |
| 60 | **ID mới:** "Sau khi tới trắng thì ván tiếp theo 3 chuồn đánh trước" |

Phân bố theo nhóm: Cơ bản 16 · So sánh 10 · Chặt hàng 18 · Tới trắng 10 · Chia lại 2 · Phạt 18 · Thưởng đặc biệt 2 · Kết thúc ván 10 · Điểm số 21 · Phòng online 23 = **130**.
Phân loại (cập nhật sau GĐ2): fixedInvariant 48 · adminConfigurable 45 · derivedRule 16 · operationalPolicy 21.

---

## 2. Quyết định đã chốt (vòng 1–3)

| Mã | ID | Quyết định |
|---|---|---|
| D1 | 7, 8 | Lá mở ván là **3♣** (dù 3♠ là lá nhỏ nhất theo thứ tự chất) |
| D2 | 105 | Người về nhất/nhì đánh bài cuối mà **không ai chặn** → người **còn bài kế tiếp theo chiều kim đồng hồ** được mở vòng ("hưởng sái"); chặn được thì vòng tiếp tục bình thường |
| D3 | 83, 119–121 | Chặt chồng **cộng dồn**: người bị chặt cuối cùng trả toàn bộ chuỗi cho người chặt cuối |
| D4 | 107, 124 | Tới trắng: **không xét thối**; 3 người còn lại **cùng về thứ 4**; mỗi người trả 200 → người tới trắng +600 |
| D5 | 7, 58, 59, 60 | "Ván đầu" = ván đầu tiên khi vào bàn. Ván **ngay sau tới trắng** cũng mở bằng 3♣ và cũng xét chia lại. **Tất cả cùng thoát → hủy bàn** |
| D6 | 43 | **Tứ quý cần đúng vòng**, giống 3 đôi thông. Chỉ 4 đôi thông được chặt ngoài lượt (42) |
| D7 | 68–71, 123 | Người cóng trả **200 cho người về nhất**, **dừng chơi ngay và xếp bét** (có thể 2–3 người cùng bét). Cóng toàn bàn = 3 × 200 **+ xét thối heo** |
| D8 | 72–77, 85 | **Người về thứ 4** bị xét thối: heo đen 100, heo đỏ 200; 3 đôi thông / 4 đôi thông / tứ quý: **200 mỗi bộ**, trả cho **người về 3**; tứ quý 2 = 4 heo |
| D9 | 87, 88, 142, 145 | **Hết giờ = mất lượt.** Người thoát giữa ván xếp thứ 4; người thoát tiếp theo xếp thứ 3, và cứ thế |
| D10 | 89, 125 | Đút mù = **hết ván ngay**; người đút mù +600, 3 người còn lại −200 mỗi người |
| D11 | 68, 84, 123 | (vòng 2–3) Người cóng trả **200 = khoản bét** cho người nhất (không trừ thêm điểm hạng bét), **cộng thêm thối heo và thối hàng** |
| D12 | 72–77, 69 | (vòng 2–3) Thối của người **bị cóng** (bất kể 1, 2 hay 3 người cóng) trả cho **người về nhất**. Thối của người **bét bình thường** (không cóng) trả cho **người về 3** |
| D13 | 142 | (vòng 2) Người mở vòng hết giờ → **server tự đánh lá đơn nhỏ nhất** (ván mở bằng 3♣ thì tự đánh 3♣). Người không mở vòng hết giờ → mất lượt |
| D14 | 89 | (vòng 2) Đút mù = người **về nhất** với nước cuối là **3♠ đánh đơn** |
| D15 | 68, 104 | (vòng 3) 1 người cóng → 2 người còn lại **đánh tiếp** để xác định nhì/ba |

### Bảng tính điểm cuối ván (theo D7, D8, D11, D12, D15)

Điểm hạng là các cặp chuyển: **bét → nhất 200**, **ba → nhì 100**. Người cóng trả khoản bét 200 dưới dạng tiền cóng.

| Tình huống (A về nhất) | Điểm hạng / cóng | Thối trả cho |
|---|---|---|
| Không ai cóng; B nhì, C ba, D bét | A +200 ← D; B +100 ← C | Thối của D → C (về 3) |
| 1 người cóng (D); B, C đánh tiếp → B nhì, C ba | A +200 ← D (cóng); B +100 ← C | Thối của D → **A** |
| 2 người cóng (C, D); B còn lại | A +400 ← C, D (cóng); B: 0 | Thối của C, D → **A** |
| Cóng toàn bàn (B, C, D) | A +600 ← B, C, D (cóng) | Thối của B, C, D → **A** |

Ví dụ: chỉ D bị cóng, D đang giữ 2♠, 2♥ và một tứ quý 7 → D trả A 200 (cóng) + 100 + 200 + 200 (thối) = **700**. B và C đánh tiếp, B về nhì → C trả B 100. Kết quả: A +700, B +100, C −100, D −700, tổng = 0.

**Hệ quả tôi suy ra (cần xác nhận nếu sai):**
- Tới trắng (D4) và đút mù (D10) đều zero-sum: +600 / −200 × 3, **không** cộng thêm điểm hạng 112–115.
- Ván sau đút mù: người đút mù là người nhất nên được mở ván (ID 9). Ván sau tới trắng: mở bằng 3♣ (ID 60).
- Thối hàng: 4 đôi thông chứa sẵn 3 đôi thông thì chỉ tính một bộ (200). Tứ quý 2 = 2×100 + 2×200 = 600, không tính thêm thối tứ quý.
- Người về 3 lúc hết ván vẫn còn bài nhưng **không** bị xét thối (chỉ người bét bị xét).
- Đút mù (D14): điểm chặt đã chốt trước đó trong ván vẫn giữ nguyên; người còn lại không bị xét thối, giống tới trắng.

---

## 3. Bảng quyết định chặt hàng + điểm (đã cập nhật D3, D6)

Điểm chặt tính theo **bộ bị chặt (target)**. Cách tính này khớp với cả ba mô tả ở ID 119, 120 và 121:

| Bài bị chặt (target) | Bộ được phép chặt | Điều kiện lượt | Điểm |
|---|---|---|---|
| Heo đơn | 3 đôi thông (29) · Tứ quý (31) · 4 đôi thông (35) | 3 đôi thông/tứ quý: đúng lượt (43); 4 đôi thông: ngoài lượt được (42) | heo đen 100 / đỏ 200 |
| Đôi heo | Tứ quý (32) · 4 đôi thông (36) · Đôi heo lớn hơn (27, 44) | như trên; đôi heo: đúng lượt | tổng 2 heo |
| 3 đôi thông | 3 đôi thông lớn hơn (30) · Tứ quý (33) · 4 đôi thông (38) | như trên | 200 |
| Tứ quý | Tứ quý lớn hơn (34) · 4 đôi thông (37) | như trên | 400 |
| 4 đôi thông | 4 đôi thông lớn hơn (39) | ngoài lượt được | 400 |

**Chặt chồng cộng dồn (D3), ví dụ:** A đánh 2♥ → B chặt bằng 3 đôi thông → C chặt bằng tứ quý → không ai chặn tiếp.
Kết quả: B trả C 200 + 200 = **400**; A không mất điểm. Điểm chỉ chốt **khi vòng kết thúc**; mỗi lần chặt vẫn được ghi event riêng để đối soát.

[Giả định] Không cho phép: 3 đôi thông chặt đôi heo hoặc tứ quý; tứ quý chặt 4 đôi thông. Heo đè heo nhỏ hơn = đè thường, không tính điểm chặt.

---

## 4. Trạng thái câu hỏi

- **R2, R3, R4, R5 (P0): đã chốt** → D11–D15 ở §2.
- **R6–R8 (P1): không có phản đối → áp dụng default** (vẫn sửa được ở GĐ2):

| Mã | Default áp dụng |
|---|---|
| R6 | Người thoát (hoặc mất kết nối quá 120s) bị loại khỏi vòng chơi như người đã hết bài; xếp hạng thấp nhất còn trống; **bị xét thối** nếu là người bét; **không** tính cóng |
| R7 | Ván mở bằng 3♣: xét **tới trắng trước**, không ai tới trắng thì mới xét chia lại |
| R8 | 4 đôi thông chặt ngoài lượt mọi target hợp lệ ở §3, kể cả khi đã pass; lượt tiếp theo tính từ người chặt; lệnh đến cùng lúc thì server xử lý tuần tự |

### Các câu P1/P2 từ vòng 1 → **áp dụng default** (không có phản đối)

| Mã | Default áp dụng |
|---|---|
| Q-P1-1 (13) | Đã pass thì bị khóa đến vòng mới; hết giờ = pass |
| Q-P1-2 | Có bộ ba (sám), so theo số |
| Q-P1-3 | Sảnh ≥ 3 lá, không vòng; đôi thông 3–6 đôi được đánh, chỉ loại 3 và 4 đôi có quyền chặt |
| Q-P1-4 (44) | Đôi 2 đè đôi 2 → người bị đè trả giá trị đôi heo của mình |
| Q-P1-5 (52) | 6 đôi: tứ quý tính 2 đôi; đôi 2 có tính |
| Q-P1-7 (63) | "Đi trước" = gần người được quyền mở ván nhất theo chiều kim đồng hồ |
| Q-P1-8 (120) | Bất kỳ hàng nào bị hàng lớn hơn đè đều tính điểm theo §3 |
| Q-P1-9 (109) | Chỉ hệ thống/Admin được hủy ván; hủy ván thì bỏ toàn bộ điểm của ván |
| Q-P1-10 | Đổi người chơi = mở phiên mới (điểm về 0) |
| Q-P1-11 (47) | Cố định = true |
| Q-P2-1 (9) | Người thắng ván trước đã rời bàn → ván mở bằng 3♣ (có xét chia lại) |
| Q-P2-2 (148) | Chủ phòng khởi động lại phiên, chỉ giữa các ván |
| Q-P2-3 (147) | Đóng phòng khi đang có ván → hủy ván, không tính điểm |
| Q-P2-4 (154) | Replay lộ toàn bộ bài chỉ sau khi ván kết thúc, chỉ cho 4 người trong ván xem |
| Q-P2-5 | Tài khoản Admin tạo qua CLI seed; 2FA làm ở giai đoạn hardening |
| Q-P2-6 | Khoảng giá trị Admin được chỉnh: thời gian lượt 10–120s, giữ ghế 30–600s, điểm 0–10.000 |

---

## 5. Bất nhất còn lại / ghi chú cho thiết kế

| # | Nội dung | Xử lý |
|---|---|---|
| B2 | ID 134 ghi "chủ phòng chỉnh luật" | Override [Yêu cầu]: chỉ System Admin |
| B3 | ID 135–138, 156 ghi "luật phòng" | Override [Yêu cầu]: luật GLOBAL + snapshot theo ván |
| B5 | Thời gian 30 giây xuất hiện ở ID 10, 13, 141 | Nguồn duy nhất là 141 |
| B7 | ID 62 và 64 trùng | Gộp `instantWin.priorityOrder` |
| B13 | ID 112–115 vẫn ghi "vd" | Default 200/100/−100/−200, **chưa chốt**; validator yêu cầu tổng = 0 |
| B15 | ID 127 vs 133 | Khi bật zero-sum thì điểm âm bắt buộc phải được phép |
| B18 | ID 103 / 104 | Gộp thành enum `game.endMode` |
| B19 | Thối hàng (200/bộ) khác điểm chặt hàng (tứ quý 400) | Hai config riêng: `rot.*` và `scoring.chop.*` |
| B20 | Excel ID 83 cột D ("Tính từng lần chặt") và ID 124 cột E ("2oo*3") chưa sửa theo D3/D4 | Hệ thống theo D3/D4; nên sửa lại Excel để tránh hiểu nhầm về sau |

---

## 6. Phạm vi làm (đầy đủ theo Excel)

**Làm:** Admin (login, draft → validate → diff → publish → rollback → audit cho luật GLOBAL); Guest (nickname, token reconnect, phòng 4 ghế, mã/link mời, ready, tự bắt đầu, rời phòng, đóng phòng); bàn chơi realtime (chia bài, xếp bài, đánh/pass, timer, chặt kể cả ngoài lượt, số lá đối thủ, version/hash luật); rules engine Python deterministic thực hiện **đủ 130 ID**; scoring ledger zero-sum; reconnect, khôi phục sau restart, replay sau khi ván kết thúc; bảo mật cơ bản.

**Không làm (CLAUDE.md loại trừ hoặc không được yêu cầu):** bot, matchmaking, tiền thật, chat, khán giả, preset luật theo phòng, đa ngôn ngữ, app native, Redis scale-out.

## 7. Acceptance criteria

| # | Tiêu chí |
|---|---|
| AC1 | Mỗi ID trong 130 ID có ≥ 1 test tham chiếu đến ID đó; bảng trace ID → test đủ 130/130 |
| AC2 | Property test ≥ 10.000 ván ngẫu nhiên: 52 lá không trùng/mất; không ai đi sai lượt; tổng điểm 4 người mỗi ván = 0 |
| AC3 | Không API/WebSocket/replay nào lộ bài đối thủ trước khi ván kết thúc |
| AC4 | Chỉ Admin publish được luật (người khác bị 403); mọi publish/rollback đều có audit log |
| AC5 | Publish luật khi đang có ván: ván đó vẫn dùng snapshot cũ; ván sau dùng version mới và client nhận thông báo |
| AC6 | `requestId` trùng hoặc lệnh sai lượt → bị từ chối, trạng thái không đổi, không cộng điểm 2 lần |
| AC7 | Kill server giữa ván rồi khởi động lại → ván khôi phục đúng (bài, lượt, timer, điểm); người reconnect thấy đúng bài của mình |
| AC8 | Mất kết nối < 120s → quay lại đúng ghế; > 120s → áp dụng D9/R6; người mở vòng hết giờ → server tự đánh lá đơn nhỏ nhất (D13) |
| AC9 | E2E với 4 client trình duyệt: chơi trọn ván từ Home tới scoreboard trên desktop và mobile |
| AC10 | Từ events + rules snapshot tái tạo được đúng kết quả và điểm của mọi ván |
| AC11 | Test kịch bản bắt buộc: hưởng sái (D2), chặt chồng 3 tầng (D3), tới trắng → ván sau mở 3♣ + chia lại (D4, D5), cóng 1/2/3 người kèm thối (D7, D11, D12), thối có tứ quý 2 (D8), thoát lần lượt (D9, R6), đút mù (D10, D14) |

---

## 8. Cần anh/chị làm để kết thúc GĐ1

1. Duyệt phạm vi (§6), tiêu chí nghiệm thu (§7) và phân loại ruleKey trong [Phụ lục A](A-rule-inventory.md).
2. (Khuyến nghị) Sửa ID 83 (cột D) và ID 124 (cột E) trong Excel cho khớp D3/D4.

Khi được duyệt, tôi chuyển sang **GĐ2 Design**: ADR kiến trúc, ERD, RuleConfig schema + mapping Excel, state machine, API/WebSocket, scoring ledger, recovery, wireframe, security, test matrix — rồi dừng xin duyệt tiếp.

**Tôi dừng ở đây chờ duyệt. Chưa có thiết kế chi tiết và chưa có dòng code nào.**
