# GĐ2.3 — Rules Engine, State machine, Scoring ledger

Package `tlmn_engine`: Python thuần, không I/O, không đọc clock, không random. Mọi hàm public đều nhận `rules: RuleSnapshot`.

## 1. Biểu diễn bài và bộ bài

- `card_id = rank_index * 4 + suit_index` (0..51). `rank_index`: 3→0 … A→11, 2→12. `suit_index`: ♠0 ♣1 ♦2 ♥3 (ID 5, 6).
- So hai lá = so `card_id` (cùng số thì chất quyết định). Lá nhỏ nhất 3♠ = 0; **3♣ = 1**.

| `ComboType` | Điều kiện | `key` để so |
|---|---|---|
| SINGLE | 1 lá | card_id |
| PAIR | 2 lá cùng số | card_id lớn nhất (ID 18, 19, 27) |
| TRIPLE | 3 lá cùng số (Q-P1-2) | rank |
| FOUR_KIND | 4 lá cùng số | rank (ID 34) |
| STRAIGHT(n) | n ≥ 3 số liên tiếp, không chứa 2, không vòng (ID 21–23) | card_id lớn nhất |
| PAIR_SEQ(k) | k ≥ 3 đôi số liên tiếp, không chứa 2 (Q-P1-3) | card_id lớn nhất |

Nhóm dùng cho chặt (`ChopCategory`): `HEO_SINGLE`, `HEO_PAIR`, `PS3` (= PAIR_SEQ(3)), `FK`, `PS4`. PAIR_SEQ(5–6) đánh được như bộ thường nhưng **không** có quyền chặt và không phải target.

## 2. Engine API

| Hàm | Vai trò |
|---|---|
| `classify_hand(cards) -> Combo \| None` | Nhận diện bộ |
| `compare_plays(a, b) -> int` | So hai bộ cùng type và cùng độ dài |
| `can_beat(top, play, ctx) -> BeatResult` | Bảng quyết định §3: `LEAD / BEAT / CHOP / reject(code)` + `scoresAsChop`, `targetValue` |
| `can_interrupt(state, seat, play) -> bool` | Chặt ngoài lượt (chỉ PS4, ID 42, R8) |
| `validate_move(state, seat, action) -> Ok \| Reject(code)` | Kiểm tra đầy đủ: lượt, bài có trong tay, 3♣ mở ván, pass hợp lệ |
| `apply(state, action, rules, now) -> (state', events[])` | Reducer duy nhất; mọi thay đổi trạng thái đi qua đây |
| `check_instant_win(hands, leader_seat, rules)` | ID 49–53, 62–66 |
| `detect_redeal(hands, rules)` | ID 58, 59 (chỉ ván mở bằng 3♣) |
| `resolve_trick(state)` | Đóng vòng, quyết toán chuỗi chặt, chọn người mở vòng (ID 14, 105) |
| `finish_game(state) -> GameResult` | Xếp hạng, cóng, thối, transfers |
| `calculate_score(result, rules) -> Transfer[]` | Sinh transfer (zero-sum theo cấu trúc) |
| `compute_rot(hand, rules) -> RotItem[]` | Thối heo + hàng, không tính trùng |
| `validate_rule_config(cfg) -> ValidationReport` | V1–V10 ở [02](02-ruleconfig.md) |
| `project_public(state)`, `project_private(state, seat)` | Chỉ hai hàm này được dùng để tạo dữ liệu gửi client |

## 3. Bảng quyết định `can_beat` (theo thứ tự ưu tiên)

| Bước | Điều kiện | Kết quả |
|---|---|---|
| 1 | `classify_hand(play)` = None | reject `INVALID_COMBINATION` |
| 2 | Bàn trống (đang mở vòng) | Nước mở đầu ván ở chế độ THREE_CLUBS mà không chứa 3♣ → `MUST_INCLUDE_THREE_CLUBS` (ID 8); ngược lại → `LEAD` |
| 3 | Cùng type, cùng độ dài, `play.key > top.key` | `BEAT`; `scoresAsChop = true` nếu top ∈ {PS3, FK, PS4} (Q-P1-8) hoặc top = HEO_PAIR và bật ID 44 |
| 4 | Cùng type, cùng độ dài, không lớn hơn | reject `CANNOT_BEAT` |
| 5 | Khác type: tra **ma trận chặt** (bên dưới) và cờ tương ứng đang bật | `CHOP`, `scoresAsChop = true` |
| 6 | Còn lại | reject `CANNOT_BEAT` (ID 24) |
| 7 | Nếu kết quả có `scoresAsChop` và bàn đang là nước chặt mà `allowChain = false` | reject `CHAIN_NOT_ALLOWED` (ID 41) |
| 8 | Nếu kết quả có `scoresAsChop`, đã có người về nhất và `allowAfterFirstFinisher = false` | reject `CHOP_NOT_ALLOWED` (ID 48) |

Ma trận chặt (attacker → target, cờ):

| Attacker \ Target | HEO_SINGLE | HEO_PAIR | PS3 | FK | PS4 |
|---|---|---|---|---|---|
| PS3 | 29 | — | (cùng loại, 30) | — | — |
| FK | 31 | 32 | 33 | (cùng loại, 34) | — |
| PS4 | 35 | 36 | 38 | 37 | (cùng loại, 39) |

**Điều kiện lượt:**
- Mặc định: phải là `currentSeat` và chưa pass (ID 13, 43, D6).
- Ngoại lệ `can_interrupt` (ID 42, R8): play là PS4, bàn đang có target hợp lệ (cột của hàng PS4), người chặt đang ACTIVE và không phải `topSeat`. Được phép kể cả khi chưa tới lượt hoặc đã pass. Sau khi chặt ngoài lượt, người chặt được **gỡ khỏi danh sách đã pass**.
- Mọi lệnh mang `baseSeq`; nếu `baseSeq ≠ lastSeq` → `STALE_STATE` (tránh chặt một bài đã bị đè, tránh race giữa hai lệnh).

**Giá trị target** (dùng cho chuỗi chặt, ID 117–122): HEO_SINGLE = 100 (đen) hoặc 200 (đỏ); HEO_PAIR = tổng 2 lá; PS3 = `chopTargetValue.threePairSeq` (200); FK = 400; PS4 = 400.

## 4. State machine

### 4.1 Phòng
```
WAITING ──(đủ 4 ghế & cả 4 ready, ID 139–140)──► IN_GAME ──(ván kết thúc/hủy)──► WAITING (reset ready)
   │                                                 │
   └──── chủ phòng đóng / tất cả rời (D5) ───────────┴──► CLOSED   (đóng khi đang chơi → hủy ván, Q-P2-3)
```

### 4.2 Ghế / kết nối
```
EMPTY ─join─► CONNECTED ─mất WS─► DISCONNECTED(hold_until = now + 120s) ─reconnect─► CONNECTED
                                     └─ hết hạn ─► đang trong ván: FORFEIT (D9, R6)
                                                   ngoài ván: giải phóng ghế → EMPTY
Rời chủ động: đang trong ván → FORFEIT ngay; ngoài ván → EMPTY.
Ghế đổi người ⇒ phiên hiện tại kết thúc, phiên mới bắt đầu ở ván tiếp theo (Q-P1-10).
```

### 4.3 Ván
```
DEALING ─► check_instant_win ─có─► FINISHED(INSTANT_WIN)
    │                     └─không─► (THREE_CLUBS & detect_redeal) ─có─► REDEAL ─► DEALING
    └────────────────────────────────────────────────────────────────không─► PLAYING
PLAYING ─(vòng lặp trick)─► FINISHED(NORMAL | BLIND_THREE_SPADES)
PLAYING / DEALING ─(lỗi hệ thống, Admin hủy, đóng phòng, tất cả rời)─► CANCELLED
```

### 4.4 Người chơi trong ván
`ACTIVE → FINISHED(rank) | CONG(rank đáy) | FORFEITED(rank thấp nhất còn trống)`.

## 5. Pseudo-code các trường hợp biên

```python
def opening_mode(prev_game):                        # ID 7, 9, 60, D5, G8
    if prev_game is None:                     return THREE_CLUBS     # ván đầu của phiên
    if prev_game.end_type in (INSTANT_WIN, CANCELLED): return THREE_CLUBS
    return WINNER_LEADS(prev_game.rank1_seat)      # roster không đổi trong phiên

def deal(game, rng):                                # ID 49–67
    while True:
        deck = rng.shuffle(52); hands = split_13(deck)
        leader = seat_holding(THREE_CLUBS) if mode == THREE_CLUBS else prev_winner
        iw = check_instant_win(hands, leader, rules)          # R7: tới trắng xét trước
        if iw: return end_instant_win(iw)                     # người không tới trắng trả perLoser (chia đều nếu nhiều người cùng loại), về thứ 4, không thối
        if mode == THREE_CLUBS and detect_redeal(hands, rules):
            emit(REDEALT, commitment_of_old_deck); continue   # cap an toàn 100 lần → CANCELLED
        return start_playing(hands, leader)

def check_instant_win(hands, leader, rules):
    for kind in rules.instantWin.priorityOrder:               # 62/64: mặc định 4 heo > sảnh rồng > 6 đôi
        if not enabled(kind): continue
        seats = [s for s in clockwise_from(leader) if qualifies(hands[s], kind)]
        if seats:                                             # 63: cùng loại → chia tiền (SPLIT_EQUALLY)
            return (seats, kind) if rules.instantWin.tieBreak == SPLIT_EQUALLY else ([seats[0]], kind)
# qualifies: FOUR_TWOS: 4 lá 2 · SIX_PAIRS: sum(count[r]//2) >= 6 (tứ quý = 2 đôi, Q-P1-5)
#            DRAGON: đủ 12 số 3..A (không cần đồng chất)

def on_play(state, seat, cards):
    r = can_beat(state.trick.top, classify_hand(cards), ctx)    # §3 + điều kiện lượt
    remove(cards, state.hands[seat]); state.played_count[seat] += len(cards)
    if r.scoresAsChop:
        state.trick.chain.append(ChopLink(chopper=seat, victim=state.trick.top_seat, value=target_value(state.trick.top)))
    state.trick.top, state.trick.top_seat = r.combo, seat
    state.trick.passed.discard(seat)                            # chặt ngoài lượt: gỡ khỏi passed
    if not state.hands[seat]:
        finish_player(state, seat, last_play=r.combo)
        if state.ended: return
    advance(state, after=seat)

def finish_player(state, seat, last_play):
    rank = lowest_unassigned_top_rank(state)                    # 1, 2, 3 … (ID 15, 16, 99–102)
    state.status[seat] = FINISHED(rank)
    if rank == 1 and rules.special.blindThreeSpades and last_play == SINGLE(3♠):   # D14
        return end_game(state, BLIND_THREE_SPADES)              # +perLoser×3; chặt đã quyết toán giữ nguyên
    if rank == 1 and rules.penalty.cong.enabled:                # D7, D11
        for s in clockwise_from(seat):
            if state.status[s] == ACTIVE and state.played_count[s] == 0:
                state.status[s] = CONG(lowest_free_bottom_rank(state))
    if count_active(state) <= 1:                                # ID 104, D15
        for s in active_seats(state): state.status[s] = FINISHED(lowest_unassigned_top_rank(state))
        close_trick_if_open(state); end_game(state, NORMAL)

def advance(state, after):                                      # ID 4, 13, 14, 105, 106
    responders = [s for s in clockwise_after(after)
                  if state.status[s] == ACTIVE and s not in state.trick.passed and s != state.trick.top_seat]
    if responders: state.current = responders[0]; start_turn_timer(); return
    close_trick(state)

def close_trick(state):
    settle_chain(state.trick.chain)                             # D3, §7
    top = state.trick.top_seat
    leader = top if state.status[top] == ACTIVE else next_active_clockwise(top)    # D2: hưởng sái
    state.trick = Trick(leader=leader); state.current = leader; start_turn_timer()

def on_pass(state, seat):                                       # ID 12, 13
    require(seat == state.current and state.trick.top is not None)  # người mở vòng không được pass
    state.trick.passed.add(seat); advance(state, after=seat)

def on_timeout(state):                                          # ID 141, 142, D9, D13
    seat = state.current
    if state.trick.top is None:
        card = THREE_CLUBS if must_include_three_clubs(state) else min(state.hands[seat])
        on_play(state, seat, [card], auto=True)
    else:
        on_pass(state, seat, auto=True)

def on_forfeit(state, seat, reason):                            # D9, R6
    state.status[seat] = FORFEITED(lowest_free_bottom_rank(state))   # thoát trước → hạng thấp hơn
    if all_seats_left(room): return cancel_game_and_close_room()      # D5
    if count_active(state) <= 1: ... end như finish_player
    elif state.current == seat: advance(state, after=seat)
    # nếu seat là top_seat: vòng vẫn tiếp tục; nếu không ai chặn thì hưởng sái như người đã hết bài
    # nợ chuỗi chặt của seat vẫn được quyết toán
```

**Invariants kiểm tra sau mỗi `apply`** (trong test luôn bật; production: vi phạm → hủy ván + log lỗi nghiêm trọng): 52 lá không trùng/mất (tay + đã đánh); `current` là ACTIVE; rank không trùng; `top_seat` có khi và chỉ khi `top` có; `passed ⊆ ACTIVE`; tổng mọi transfer của ván = 0.

## 6. Thối (ID 72–77, 84, 85; D8, D11, D12)

```python
def compute_rot(hand, rules):
    items = [RotItem("HEO", c, black_or_red_value(c)) for c in hand if rank(c) == 2]   # tứ quý 2 = 4 heo
    rest = [c for c in hand if rank(c) != 2]
    combos = enumerate_disjoint({FK, PS4, PS3} đang bật, rest)   # vét cạn, tay ≤ 13 lá
    best = max(combos, key=(tổng giá trị, -số bộ, rank cao))      # không tính trùng, deterministic
    return items + best
```
Người bị xét và người nhận:

| Người bị xét | Nhận thối |
|---|---|
| Mỗi người **CONG** (1, 2 hay 3 người) | Người về nhất |
| Người hạng 4 **không** cóng (bét bình thường, kể cả người thoát) | Người về 3 nếu người đó là FINISHED; nếu hạng 3 là người cóng/thoát → người về nhất (**G10**) |
| Tới trắng, đút mù | Không xét |

## 7. Scoring ledger

Mọi biến động là `Transfer(from_seat, to_seat, amount > 0, reason, detail)`. Tổng mỗi ván = 0 theo cấu trúc.

| Thời điểm | Reason | Quy tắc |
|---|---|---|
| Đóng vòng | `CHOP_CHAIN` | `chain[-1].victim → chain[-1].chopper`, amount = Σ value của mọi link (D3) |
| Kết thúc NORMAL | `CONG` | Mỗi người cóng → hạng 1: `congValue` (200 = khoản bét, D11) |
| | `RANK` | Hạng 4 không cóng → hạng 1: `rank.first`; hạng 3 không cóng → hạng 2: `rank.second` (V1: first = −last, second = −third) |
| | `ROT_*` | Theo §6 |
| INSTANT_WIN | `INSTANT_WIN` | Mỗi người **không** tới trắng trả `instantWinPerLoser` (200), chia đều cho những người tới trắng cùng loại; phần dư (nếu có) cho người gần người mở ván nhất. Ví dụ B, D cùng 6 đôi: A, C mỗi người trả 100 cho B và 100 cho D → B +200, D +200, A −200, C −200 |
| Kết thúc NORMAL | `TRAPPED_THREE_SPADES` | Người về chót (không cóng) còn **đúng 1 lá là 3♠** → trả `trappedThreeSpades.perPlayer` (200) cho **mỗi** người còn lại, cộng thêm tiền bét thông thường (ảnh luật §3.3) |
| BLIND_THREE_SPADES | `BLIND_THREE_SPADES` | Mỗi người còn lại → người đút mù: `blindThreeSpadesPerLoser`; không RANK, CONG, ROT |
| CANCELLED | — | Mọi transfer của ván bị loại khỏi tổng phiên |

Transfer chặt được ghi ngay khi vòng đóng (người chơi thấy "điểm tạm"), nhưng chỉ được cộng vào `session_scores` khi ván FINISHED.

### Ví dụ đối soát (A về nhất; giá trị mặc định)

| # | Tình huống | A | B | C | D |
|---|---|---|---|---|---|
| 1 | Bình thường: A, B, C, D về 1–4; D còn 2♥ | +200 | +100 | −100 +200 | −200 −200 |
| 2 | D cóng (giữ 2♠, 2♥, tứ quý 7); B nhì, C ba | +200 +500 | +100 | −100 | −200 −500 |
| 3 | C, D cóng, không giữ heo/hàng; B còn lại | +400 | 0 | −200 | −200 |
| 4 | Chặt chồng: A đánh 2♥, B chặt bằng 3 đôi thông, C chặt bằng tứ quý | 0 | −400 | +400 | 0 |
| 5 | D tới trắng | −200 | −200 | −200 | +600 |
| 6 | A đút mù | +600 | −200 | −200 | −200 |
| 7 | D thoát (hạng 4, còn 2♠), sau đó C thoát (hạng 3); A nhất, B nhì | +200 +100 | +100 | −100 | −200 −100 |

| 8 | Bị nhốt 3♠: A, B, C về 1–3; D về chót còn đúng 3♠ | +200 +200 | +100 +200 | −100 +200 | −200 −600 |
| 9 | B và D cùng tới trắng 6 đôi | −200 | +200 | −200 | +200 |

Trường hợp 7: D bét không cóng, nhưng người hạng 3 (C) cũng là người thoát, nên theo **G10** thối của D trả cho người nhất.

Mọi dòng có tổng = 0. Đây sẽ là test fixture cho scoring reconciliation.
