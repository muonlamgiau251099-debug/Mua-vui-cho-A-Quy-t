# GĐ2.4 — REST API, WebSocket, Persistence và Recovery

## 1. REST API (`/api`, JSON, lỗi theo RFC 9457 `application/problem+json`)

### Admin (cookie session + header `X-CSRF-Token` cho lệnh ghi)
| Method | Path | Mô tả |
|---|---|---|
| POST | `/admin/login` · `/admin/logout` · GET `/admin/me` | Đăng nhập (rate limit 5 lần/phút/IP, khóa 15 phút sau 10 lần sai) |
| GET | `/admin/rules/active` · `/admin/rules/versions` · `/admin/rules/versions/{v}` | Xem |
| GET / POST / PUT / DELETE | `/admin/rules/draft` | Xem / tạo (từ ACTIVE hoặc `?from=v`) / sửa (`If-Match: <lock_version>` → 409 nếu lệch) / hủy draft |
| POST | `/admin/rules/draft/validate` | Trả `{errors, warnings, infos, configHash}` |
| GET | `/admin/rules/draft/diff?against=active\|{v}` | Diff theo ruleKey + Excel ID |
| POST | `/admin/rules/draft/publish` | Body `{expectedHash, expectedActiveVersion, note, acknowledgedWarnings[]}` |
| POST | `/admin/rules/rollback` | Body `{targetVersion, expectedActiveVersion, note}` → version mới |
| GET | `/admin/audit?from&to&action&page` | Audit log |
| GET | `/admin/games/{id}/events` · `/admin/games/{id}/replay` | Xem toàn bộ để xử lý tranh chấp (có ghi audit) |
| POST | `/admin/games/{id}/cancel` | Hủy ván (Q-P1-9) |

### Công khai / Guest (`Authorization: Bearer <guestToken>`)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/rules/active` · `/rules/versions/{v}` · `/rules/catalog` | Xem luật (read-only), version, hash, mô tả Excel |
| POST | `/guests` `{nickname}` | Trả `{guestId, token}` — token chỉ trả **một lần** |
| GET / PATCH | `/guests/me` | Xem / đổi nickname (chỉ khi không ngồi trong ván đang chơi) |
| POST | `/rooms` | Tạo phòng → `{roomId, code, inviteUrl}`; người tạo là chủ phòng, ngồi ghế 0 |
| GET | `/rooms/by-code/{code}` | Xem trước phòng (số ghế trống) |
| POST | `/rooms/{roomId}/join` `{seatNo?}` | Vào ghế (409 nếu hết ghế / đang có ván) |
| POST | `/rooms/{roomId}/leave` | Rời (đang có ván → FORFEIT) |
| POST | `/rooms/{roomId}/close` | Chủ phòng đóng (ID 147) |
| POST | `/rooms/{roomId}/sessions/restart` | Chủ phòng khởi động lại phiên, chỉ giữa các ván (ID 148) |
| GET | `/rooms/{roomId}/sessions` · `/sessions/{id}` | Bảng điểm phiên + lịch sử theo ván (ID 130, 131, 150) |
| GET | `/games/{id}/result` · `/games/{id}/replay` | Chỉ người chơi trong ván; replay chỉ khi ván đã kết thúc (ID 149, 154) |

Mã phòng: 6 ký tự từ bảng chữ không gây nhầm (bỏ 0/O/1/I), unique trong số phòng chưa đóng. Join bị rate limit để chống dò mã.

## 2. WebSocket `/ws/rooms/{roomId}`

- Kiểm tra `Origin` theo allowlist. Message đầu tiên phải là `auth` trong vòng 5 giây, nếu không thì đóng (4401).
- Tối đa 1 kết nối/guest/phòng; kết nối mới đẩy kết nối cũ ra (4409).
- Frame tối đa 4 KB; tối đa 10 message/giây/kết nối (vượt → `RATE_LIMITED`, vượt nhiều lần → đóng).

### Envelope
```json
{ "type": "game.play", "requestId": "uuid-v4", "roomId": "…", "gameId": "…",
  "sequence": 57, "payload": { "cards": [1, 5, 9] } }
```
- Client → server: `sequence` = `baseSeq`, tức seq cuối cùng client đã thấy.
- Server → client: `sequence` = seq của event; client phát hiện thiếu event thì gửi `sync.request`.

| Client → Server | Payload |
|---|---|
| `auth` | `{token, lastSeq?}` |
| `room.ready` | `{ready: bool}` |
| `game.play` | `{cards: int[]}` |
| `game.pass` | `{}` |
| `sync.request` | `{sinceSeq}` |
| `ping` | `{}` |

| Server → Client | Nội dung |
|---|---|
| `ack` | `{requestId, sequence}` — chỉ gửi **sau khi commit** |
| `error` | `{requestId, code, message}` — code: `NOT_YOUR_TURN, INVALID_COMBINATION, CANNOT_BEAT, MUST_INCLUDE_THREE_CLUBS, LEADER_CANNOT_PASS, ALREADY_PASSED, CARDS_NOT_IN_HAND, CHAIN_NOT_ALLOWED, CHOP_NOT_ALLOWED, STALE_STATE, GAME_NOT_ACTIVE, RATE_LIMITED, PAYLOAD_INVALID, UNAUTHORIZED` |
| `room.state` | Ghế, nickname, ready, kết nối, chủ phòng, rule version ACTIVE |
| `game.snapshot` | `project_private(state, mySeat)`: bài của mình, số lá đối thủ, vòng hiện tại, lượt, deadline, điểm tạm, `rulesVersion`, `rulesHash`, `deckCommitment` |
| `game.event` | Event công khai theo `project_public` (PLAYED, PASSED, TRICK_CLOSED, PLAYER_FINISHED, CONG_DECLARED, PLAYER_FORFEITED, TURN_STARTED{seat, deadline}, …) |
| `game.ended` | Thứ hạng, transfers, thối chi tiết, **bài cả 4 người**, `deckSalt` để tự kiểm chứng commitment |
| `rules.updated` | `{version, hash, appliesFrom: "next_game"}` (ID 137) |
| `presence` | `{seat, connected, holdUntil}` |

### Idempotency và chống replay
- `(gameId, seat, requestId)` lưu trong `command_dedup` cùng outcome. Gửi lại cùng `requestId` → server **trả lại đúng ack/error cũ**, không xử lý lại.
- `requestId` phải là UUID v4; frame thiếu hoặc sai định dạng → `PAYLOAD_INVALID`.
- `baseSeq` lệch → `STALE_STATE` kèm `game.snapshot` mới.

## 3. Pipeline xử lý lệnh (RoomActor)

```
recv frame → parse + validate schema (Pydantic strict) → rate limit
→ async with room.lock:
     dedup lookup → nếu có: gửi lại outcome, return
     state = room.cache (nạp từ DB nếu chưa có)
     check baseSeq
     (state', events) = engine.apply(state, action, rules_snapshot, now)   # reject → error, không ghi DB… (*)
     BEGIN TX
        INSERT game_events (seq liên tiếp, post_state_hash)
        INSERT score_transfers (nếu có)
        INSERT command_dedup (outcome)
        UPDATE games SET last_seq, state_hash  WHERE id=… AND last_seq = :old   ← chặn ghi chồng
        nếu đóng vòng hoặc seq % 20 == 0: INSERT game_snapshots
        nếu ván kết thúc: INSERT game_results; UPSERT session_scores; UPDATE rooms/games status
     COMMIT
     room.cache = state'
  → ack cho người gửi → broadcast từng event (public cho mọi người, private đúng người) → hẹn timer
(*) Lệnh bị reject cũng được ghi command_dedup để lần gửi lại trả đúng lỗi cũ.
```
Nếu COMMIT lỗi: cache giữ nguyên, trả `error INTERNAL`, client tự `sync.request`.

## 4. Timer
- Mỗi `TURN_STARTED` mang `deadline` tuyệt đối (giờ server, UTC). Client hiển thị đếm ngược theo `deadline − (serverNow − offset)`; offset đo bằng `ping/pong`.
- `TimerService` giữ một task cho mỗi phòng. Khi tới hạn: lấy lock, kiểm tra `state.seq` và `deadline` vẫn khớp (tránh timer cũ chạy nhầm), rồi `apply(TIMEOUT)` với `requestId = "timeout:{gameId}:{seq}"` (idempotent).
- Hết hạn giữ ghế (120 giây) được xử lý cùng cách, với action `FORFEIT`.

## 5. Recovery sau khi restart (ADR-005, ADR-014)

```
on startup:
  for game in games WHERE status = IN_PROGRESS:
      snap  = latest game_snapshots
      state = snap.state; for ev in events(seq > snap.seq): state = engine.replay(state, ev)
      assert hash(state) == games.state_hash          # lệch → CANCELLED + cảnh báo Admin
      cache[room] = state
      apply(SERVER_RESUMED, now)  →  deadline lượt hiện tại = now + timeLimit (G5)
                                    mọi ghế = DISCONNECTED, hold_until = now + seatHold
  rooms WAITING: mọi ghế DISCONNECTED với hold_until mới
```
- `engine.replay` dùng lại reducer; event lưu đủ input (action + now) nên replay luôn ra cùng trạng thái.
- **Reconnect**: client mở WS → `auth {token, lastSeq}` → server gửi `room.state` + `game.snapshot` (chỉ bài của chính người đó). Nếu `lastSeq` còn trong log thì gửi thêm các event bị thiếu.

## 6. Ghi log phục vụ tranh chấp (ID 155)
- `game_events` lưu đầy đủ (gồm bài từng nước) + `post_state_hash`, kèm `rules_hash`, `deck_commitment`.
- Log ứng dụng (stdout JSON) **không** chứa token, cookie, mật khẩu hoặc bài trên tay. Chỉ có `gameId`, `seq`, `type`, `seat`, `latency`, `outcome`. Áp dụng filter redaction toàn cục.
- Admin xem replay đầy đủ qua API riêng; mỗi lần xem được ghi vào audit.
