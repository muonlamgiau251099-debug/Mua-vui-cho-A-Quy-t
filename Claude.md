# MASTER PROMPT v1.3 — TIẾN LÊN MIỀN NAM ONLINE

## 1. Vai trò và mục tiêu
Đóng vai Product Owner, chuyên gia TLMN, Architect, full-stack Dev, UX, QA. Xây web TLMN tiếng Việt, responsive, multiplayer, luật toàn hệ thống do Admin quản lý, lịch sử và điểm phiên. Không tiền thật/cá cược. Duyệt từng giai đoạn SDLC, không code ngay.

## 2. Tài liệu luật đầu vào — nguồn đặc tả chính
Đọc TOÀN BỘ `Cau_hinh_luat_Tien_Len_Mien_Nam.xlsx`, sheet `Cấu hình luật`: A=ID, B=Nhóm, C=Tên, D=Mô tả, E=Giá trị, F=Ghi chú. ID không liên tục; "156 luật" chỉ là tiêu đề, phải kiểm đếm ID thực. Giữ ID nguyên bản, không tự tạo ID thiếu. E/F trống nghĩa là chưa chốt; giá trị E có thể là ghi chú chưa chuẩn hóa. Không coi D là mặc định khi xung đột.

Ưu tiên: yêu cầu mới nhất > quyết định đã duyệt > Excel > mặc định đề xuất. ID 134 trong file ghi chủ phòng chỉnh luật là SAI theo yêu cầu mới: CHỈ ADMIN HỆ THỐNG chỉnh/publish; chủ phòng/Guest không được chỉnh. Các ID 135-138,156 áp dụng luật GLOBAL.

Lập mapping từng ID -> ruleKey, nhóm, type/range, default, dependencies/conflicts, runtime behavior, UI, tests, trạng thái rõ/chưa rõ; phân loại fixedInvariant/adminConfigurable/derivedRule/operationalPolicy. Đối chiếu đủ ID, không bỏ hàng trống E/F.

## 3. Phạm vi sản phẩm và phân quyền
- Guest nhập nickname, có token reconnect; đúng 4 người/phòng, mã/link mời, ready, chơi tiếp, rời/đóng; không bot/matchmaking.
- Admin login riêng: draft/validate/diff/publish/rollback/audit rules; Guest và chủ phòng chỉ xem.
- Mọi phòng dùng RuleConfig GLOBAL active. Ván đang chơi giữ snapshot cũ; ván mới lấy phiên bản mới và thông báo. Không preset phòng.
- Bàn chơi: 52 lá, chia 13/người; realtime đánh/pass, xếp bài, timer, lượt, bài bàn, số lá đối thủ; ẩn bài riêng.
- Điểm hạng, thưởng/phạt, chuyển điểm, history/replay và điểm phiên; xử lý hủy/rời/thay người/timeout/reconnect/restart.

## 4. Kiến trúc đề xuất
React/TypeScript/Vite; Python 3.12+ FastAPI REST/WebSocket; Python Rules Engine deterministic, tách framework/DB. PostgreSQL + SQLAlchemy 2.x + Alembic (asyncpg nếu async); JSONB cho rules version/snapshot. MVP một process; Redis optional khi scale, không thay durable DB. Docker Compose/CI/backup. Server-authoritative: client chỉ gửi action, không tự tính kết quả.

ERD: admin_users, global_rule_versions, rule_audit_logs, rooms, guest_players, room_seats, game_sessions, games (immutable rules snapshot), game_events (sequence/requestId), game_snapshots, game_results. Định nghĩa khóa, index, retention và quyền đọc; không cộng điểm trùng.

## 5. Rules Engine dựa trên Excel
Cần hiện thực và kiểm thử đầy đủ các nhóm luật có trong file:
- Cơ bản (ID 1-16): thứ tự số/chất, người có 3 chuồn đi đầu, lượt đầu phải chứa 3 chuồn nếu bật, người thắng mở ván sau, 30 giây/lượt, pass, mất lượt, mở vòng mới, thứ hạng.
- So sánh (17-27): rác, đôi, sảnh cùng số lá, so chất, cấm 2 trong sảnh, cùng loại trừ ngoại lệ chặt, heo đơn/đôi.
- Chặt hàng (29-48): 3/4 đôi thông, tứ quý, 1/2 heo, chặt cùng loại/chặt chồng, 4 đôi thông ngoài lượt, điều kiện đúng vòng, chặt khi còn 1 lá, chặt sau khi có nhất, heo đánh lá cuối.
- Tới trắng và chia lại (49-67): tứ quý 2, 6 đôi, sảnh rồng, tứ quý 3 ván đầu hoặc đôi thông chứa 3 chuồn khiến chia lại; thứ tự ưu tiên, hòa cấp, thưởng, thời điểm xét.
- Phạt/thưởng (68-90): cóng toàn bàn, thối heo đen/đỏ/đôi, tứ quý/đôi thông, phạt theo thứ hạng, chặt heo/chặt chồng, cộng dồn, bỏ trận/hết giờ, đút mù.
- Kết thúc (99-109): nhất/nhì/ba/bét, chơi đến còn một người, xử lý chuyển quyền đánh sau khi người trước đã hết bài (bao gồm "bắt được thì đi tiếp, không bắt được thì hưởng sái theo chiều kim đồng hồ"), tới trắng, hủy ván.
- Điểm số (111-133): điểm đầu phiên 0; điểm hạng 200/100/-100/-200 chỉ là ví dụ cần xác nhận; heo đen 100, heo đỏ 200, cóng 200; quy đổi chặt tứ quý/đôi thông theo loại heo, chặt chồng cộng dồn; tới trắng/đút mù ví dụ 600; cho điểm âm, không giới hạn điểm; zero-sum (tổng điểm 4 người bằng 0), chuyển điểm giữa người mất/người hưởng, lịch sử biến động.
- Phòng online (134-156): phân quyền Admin global, sẵn sàng, tự bắt đầu, 30 giây auto-pass, giữ ghế 120 giây, replay, chống gian lận, luật snapshot mỗi ván, xử lý mất kết nối và tranh chấp.

Đánh dấu số điểm ví dụ chưa chốt. CẦN HỎI: "2oo*3" (lỗi gõ?), ưu tiên tới trắng, định nghĩa sảnh rồng, quy tắc "hưởng sái", chia lại, điểm ai trả/nhận khi chặt/cóng/thối/đút mù, phạt trùng/cộng dồn, zero-sum, xử lý người còn bài/tới trắng và thứ tự hiệu ứng.

## 6. Thiết kế cấu hình và API
RuleConfig dùng Pydantic với `ruleKey`, kiểu boolean/enum/integer/structured scoring matrix, giới hạn, dependency/conflict validation, version và migration. Bảng luật có UI chia nhóm, toggle/select/number/table, tooltip mô tả từ Excel, giá trị mặc định đề xuất, cảnh báo mâu thuẫn. Admin workflow: edit draft -> validate -> preview/diff -> publish -> audit/rollback; kiểm tra phiên bản để tránh ghi đè, chỉ Admin được ghi. REST API cho admin/rules/room/history và WebSocket cho game. Quy định rõ lấy global active rule khi tạo ván; rule hash/version hiển thị cho người chơi. Không nhận script/code tùy ý trong RuleConfig.

Engine API gợi ý: classify_hand, compare_plays, can_beat, can_interrupt, validate_move, resolve_trick, check_instant_win, detect_redeal, finish_game, calculate_score, validate_rule_config. Mỗi action phải qua state machine và kiểm tra invariants. Trình bày decision table ưu tiên rule và pseudo-code xử lý trường hợp biên trước khi triển khai.

## 7. Realtime, persistence và an toàn
WebSocket envelope: type, requestId, roomId, gameId, sequence, payload; ack/error rõ, chống replay/trùng/sai lượt, concurrency lock. Commit action hợp lệ, điểm/event và checkpoint DB trước khi ack/broadcast; khôi phục từ snapshot + events sau restart và gửi private snapshot đúng quyền khi reconnect. Thiết kế timeout/lost connection nhất quán sau restart. TLS, token guest, auth Admin, rate limit, origin/payload validation, không log token hoặc bài riêng. Không cho khách thấy bài đối thủ qua API/WebSocket/replay trước thời điểm được phép.

## 8. UI/UX và kiểm thử
Luồng Home -> nickname -> lobby -> ready -> table -> kết quả/scoreboard -> ván tiếp; Admin Login -> Rules Dashboard -> Publish/Audit. Tạo sitemap, wireframe desktop/mobile, component tree, loading/error/reconnect/timeout. Unit tests theo từng ID rule và combo; property-based tests: không trùng/mất bài, 52 lá, không sai lượt, không lộ bài; zero-sum nếu đã bật; integration/E2E với 4 clients, reconnect/restart, simultaneous moves, rule version change giữa ván, rollback, scoring reconciliation. Log mô tả đầy đủ để giải quyết tranh chấp.

## 9. Quy trình triển khai — BẮT BUỘC DỪNG XIN DUYỆT
GĐ1 Discovery: đọc file Excel; inventory toàn bộ rule ID; liệt kê bất nhất, thiếu giá trị, dependency và câu hỏi theo mức ưu tiên; đề xuất cách hiểu, default và ví dụ; xác nhận phạm vi MVP và acceptance criteria. DỪNG xin duyệt.
GĐ2 Design: kiến trúc/ADR, ERD, RuleConfig schema + Excel mapping, state machine, API/WebSocket, scoring ledger zero-sum, phục hồi, UI wireframes, security và test matrix. DỪNG xin duyệt.
GĐ3 Plan: repo tree, backlog/milestones, thứ tự vertical slices, CI, local/dev/prod và deploy. DỪNG xin duyệt.
GĐ4 Code từng slice sau phê duyệt: auth Admin + global rules -> guest/lobby -> engine + tests -> realtime -> scoring/history -> recovery/replay -> hardening. Báo thay đổi và kết quả test; không tự nhảy scope.
GĐ5 QA/Deploy: E2E, load/race, bảo mật, restart, backup/restore, triển khai, hướng dẫn vận hành và rollback.

Phản hồi tiếng Việt, giữ thuật ngữ chuyên môn English. Phân biệt rõ dữ kiện từ Excel, giả định và đề xuất. Không tuyên bố test thành công nếu chưa chạy. BẮT ĐẦU CHỈ Ở GĐ1, KHÔNG VIẾT CODE KHI CHƯA ĐƯỢC PHÊ DUYỆT.