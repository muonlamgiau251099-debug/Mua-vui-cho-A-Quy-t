# GĐ2.2 — RuleConfig schema, mapping Excel và quy trình Admin

## 1. Nguyên tắc
- **Một** RuleConfig GLOBAL đang ACTIVE. Khi tạo ván mới, server đọc version ACTIVE và chép toàn bộ vào `games.rules_snapshot` (bất biến), tính `rules_hash = sha256(canonical_json)`.
- Snapshot gồm **cả** phần Admin chỉnh được (`config`) **và** phần cố định (`invariants`, kèm `engineVersion`), nên replay về sau không phụ thuộc vào code hiện tại.
- Chỉ có các loại giá trị: boolean, enum, integer có giới hạn, danh sách thứ tự, ma trận điểm. Không có biểu thức hoặc script.
- `ruleKey` dạng `group.name`; mỗi field ghi Excel ID nguồn (`x-excel-id`) để UI hiện tooltip từ cột D và diff hiện theo ID.

## 2. Schema (Pydantic v2 — mô tả thiết kế)

```text
RuleConfig (schemaVersion = 1)
├─ turn
│   ├─ timeLimitSeconds: int [10..120] = 30                       # 141 (10, 13 derived)
│   └─ timeoutAction: enum {LOSE_TURN} = LOSE_TURN                # 142, 88; leader → AUTO_PLAY_LOWEST_SINGLE (cố định, D13)
├─ opening
│   └─ mustIncludeThreeClubs: bool = true                          # 8
├─ chop                                                            # 29–48
│   ├─ threePairSeq.vsSingleTwo: bool = true                       # 29
│   ├─ fourKind.vsSingleTwo / vsPairTwo / vsThreePairSeq: bool     # 31, 32, 33
│   ├─ fourPairSeq.vsSingleTwo / vsPairTwo / vsFourKind / vsThreePairSeq: bool   # 35–38
│   ├─ fourPairSeq.outOfTurn: bool = true                          # 42
│   ├─ allowChain: bool = true                                     # 41
│   ├─ pairTwoOverPairTwoScoresAsChop: bool = true                 # 44
│   ├─ allowAfterFirstFinisher: bool = true                        # 48
│   └─ chainSettlement: enum {CUMULATIVE} = CUMULATIVE             # 83 (D3)
├─ instantWin                                                      # 49–67
│   ├─ fourTwos / sixPairs / dragonStraight: bool = true           # 49, 52, 53
│   ├─ priorityOrder: list[FOUR_TWOS|SIX_PAIRS|DRAGON] = [FOUR_TWOS, DRAGON, SIX_PAIRS]  # 62/64 — theo ảnh luật (N1)
│   ├─ tieBreak: enum {SPLIT_EQUALLY, FIRST_IN_TURN_ORDER} = SPLIT_EQUALLY   # 63 — ảnh luật: cùng loại thì chia tiền (N2)
│   └─ checkDuringPlay: bool = false                               # 67
├─ redeal
│   ├─ fourThrees: bool = true                                     # 58
│   └─ pairSeqWithThreeClubs: bool = true                          # 59
├─ penalty
│   ├─ cong.enabled: bool = true                                   # 68
│   ├─ cong.allTable: bool = true                                  # 69 (chỉ là nhãn hiển thị; cách tính điểm giống cóng thường — G11)
│   └─ rot: { blackTwo, redTwo, fourKind, threePairSeq, fourPairSeq }: bool = true   # 72, 73, 75–77; 74 = tổng 2 heo (derived — G11)
├─ special
│   ├─ blindThreeSpades: bool = true                               # 89
│   ├─ trappedThreeSpades.enabled: bool = true                     # KHÔNG có Excel ID — ảnh luật §3.3 (N6)
│   └─ trappedThreeSpades.perPlayer: int [0..10000] = 200          # người về chót còn đúng 1 lá 3♠ → trả mỗi người còn lại
├─ scoring
│   ├─ rank: { first: 200, second: 100, third: -100, last: -200 }  # 112–115 (CHƯA CHỐT số)
│   ├─ blackTwoValue: int [0..10000] = 100                         # 117
│   ├─ redTwoValue: int [0..10000] = 200                           # 118
│   ├─ chopTargetValue: { threePairSeq: 200, fourKind: 400, fourPairSeq: 400 }   # 119–122 (heo: theo 117/118)
│   ├─ rotComboValue: { fourKind: 200, threePairSeq: 200, fourPairSeq: 200 }     # 75–77 (D8)
│   ├─ congValue: int = 200                                        # 123
│   ├─ instantWinPerLoser: int = 200                               # 124
│   └─ blindThreeSpadesPerLoser: int = 200                         # 125
└─ room
    └─ seatHoldSeconds: int [30..600] = 120                        # 144
```

**Invariants** (không hiện ô chỉnh, chỉ xem): deck 52, 4 người, 13 lá, chiều kim đồng hồ, thứ tự số/chất, 3♣ mở ván, sảnh không chứa 2, khóa sau khi pass, hưởng sái, tứ quý/3 đôi thông cần đúng lượt, tới trắng kết thúc ngay và 3 người còn lại về thứ 4, ván sau tới trắng mở bằng 3♣, cóng xét thối, thối chỉ xét người bét, `endMode = LAST_ONE_REMAINING`, `allowNegative = true`, `zeroSum = true`, không giới hạn điểm, điểm đầu phiên 0, snapshot theo ván, `finish.allowTwoAsLastCard = true`, `chop.allowWhenTargetHasOneCard = true`.

## 3. Validation (dependency / conflict)

| Mã | Quy tắc | Mức |
|---|---|---|
| V1 | `scoring.rank.first == -scoring.rank.last` **và** `second == -third` (điểm hạng là các cặp chuyển bét→nhất, ba→nhì; bảo đảm zero-sum cả khi có cóng) — **G1** | Error |
| V2 | `first > second ≥ 0`; mọi giá trị điểm là số nguyên 0..10000 (trừ third/last âm) | Error |
| V3 | `instantWin.priorityOrder` là hoán vị đúng 3 phần tử, không trùng | Error |
| V4 | Loại tới trắng bị tắt vẫn có thể nằm trong `priorityOrder` (bị bỏ qua khi chạy) | Warning |
| V5 | Tắt `chop.allowChain` nhưng vẫn bật các luật chặt hàng-đè-hàng (30, 33, 34, 37–39) → các nước đó chỉ hợp lệ khi bài trên bàn **không** phải nước chặt | Warning |
| V6 | `penalty.cong.allTable = true` yêu cầu `penalty.cong.enabled = true` | Error |
| V7 | `chopTargetValue.fourKind < chopTargetValue.threePairSeq` | Warning (bất thường) |
| V8 | Tất cả `rot.*` tắt nhưng `rotComboValue` > 0 | Info |
| V9 | `turn.timeLimitSeconds` nằm trong [10..120]; `seatHoldSeconds` ≥ 2 × `timeLimitSeconds` | Error / Warning |
| V10 | Field lạ hoặc kiểu sai → reject (Pydantic `extra="forbid"`, strict) | Error |

Validator trả về `{errors[], warnings[], infos[]}`, mỗi mục có `ruleKey`, `excelIds[]`, `message`. Publish bị chặn khi còn Error. Warning cần Admin tick "Tôi đã hiểu".

## 4. Mapping Excel → ruleKey
Bảng đủ 130 ID ở [GĐ1 Phụ lục A](../gd1/A-rule-inventory.md). Khi build, một **rule catalog** (JSON tĩnh, version theo `schemaVersion`) được sinh từ file Excel: `{excelId, group, name, description(D), excelValue(E), ruleKey, class}`. Catalog phục vụ tooltip, trang "Xem luật", trace test, và test bảo đảm mọi ID có mặt (AC1).

**Luật bổ sung ngoài Excel** (lấy từ ảnh "Luật Tiến Lên Miền Nam – Luật bản" gửi ngày 2026-10-30, không tự tạo Excel ID): `special.trappedThreeSpades` (bị nhốt 3♠). Trong catalog, mục này có `excelId = null` và `source = "rule-image-2026-10-30 §3.3"`.

## 5. Migration
`schemaVersion` tăng khi thêm/đổi field. Mỗi bước có hàm `migrate_v{n}_to_v{n+1}(dict) -> dict` (thuần, có test). Snapshot của ván cũ **không** bị migrate: engine đọc snapshot theo `schemaVersion` của nó.

## 6. Quy trình Admin

```
ACTIVE vN ──"Tạo draft"──► DRAFT (copy vN, lock_version=1)
DRAFT ──PUT (If-Match: lock_version)──► DRAFT (lock_version+1)      ← 409 nếu người khác đã sửa
DRAFT ──Validate──► kết quả + config_hash
DRAFT ──Diff (vs ACTIVE)──► danh sách thay đổi theo ruleKey/Excel ID
DRAFT ──Publish {expectedHash, expectedActiveVersion, note}──► ACTIVE v(N+1); vN → SUPERSEDED
ACTIVE ──Rollback {targetVersion, note}──► ACTIVE v(N+1) với config = config của target
Mọi bước ghi rule_audit_logs. Publish xong → broadcast `rules.updated` tới mọi phòng.
```

- Publish chỉ thành công khi `expectedHash` trùng hash của draft (không publish nhầm bản chưa validate) và `expectedActiveVersion` trùng version ACTIVE hiện tại (tránh hai Admin publish chồng nhau).
- Ván đang chơi giữ snapshot cũ; ván kế tiếp dùng version mới; client được thông báo "Luật v(N+1) sẽ áp dụng từ ván sau".
- Guest/chủ phòng chỉ có `GET /api/rules/*` (read-only).
