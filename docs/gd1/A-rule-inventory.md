# Phụ lục A — Inventory rule ID (sinh từ Excel)

Cột *Excel D/E* chép nguyên văn file. Các cột còn lại là mapping đã duyệt qua GĐ1–GĐ2.
Phân loại: FIX=fixedInvariant, ADM=adminConfigurable, DER=derivedRule, OPS=operationalPolicy.
File này được sinh bởi `tools/gen_rule_catalog.py --appendix`; không sửa tay.

| ID | Hàng | Nhóm | Tên | Excel D | Excel E | ruleKey | Loại | Kiểu | Default | Nguồn default | Trạng thái | Phụ thuộc/xung đột | Runtime/Test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | Cơ bản | Bộ bài | 52 lá, không Joker | 52 | `deck.size` | FIX | int =52 | 52 | Excel | Rõ |  | Test: deck 52 lá, không trùng, không Joker |
| 2 | 6 | Cơ bản | Số người | 4 người trong phòng | 4 | `table.playerCount` | FIX | int =4 | 4 | Excel | Rõ | Yêu cầu: đúng 4 người | Start chỉ khi 4 ghế đủ |
| 3 | 7 | Cơ bản | Chia bài | Mỗi người 13 lá | 13 | `deal.cardsPerPlayer` | FIX | int =13 | 13 | Excel | Rõ | 1,2 | Property test: 4×13=52 |
| 4 | 8 | Cơ bản | Chiều đánh | Theo thứ tự ghế /  chiều kim đồng hồ | Chiều kim đồng hồ | `turn.direction` | FIX | enum CLOCKWISE | CLOCKWISE | Excel | Rõ | 105,106 | next_seat = (seat+1)%4 bỏ qua người hết bài |
| 5 | 9 | Cơ bản | Thứ tự quân | 3 4 5 6 7 8 9 10 J Q K A 2 | 3<4<5<6<7<8<9<10<J<Q<K<A<2 | `card.rankOrder` | FIX | list | 3<…<A<2 | Excel | Rõ | 17,21 | Test so rank |
| 6 | 10 | Cơ bản | Thứ tự chất | Bích < Chuồn < Rô < Cơ | Bích<Chuồn<Rô<Cơ | `card.suitOrder` | FIX | list | ♠<♣<♦<♥ | Excel | Rõ | 7,26,89 | Test so chất |
| 7 | 11 | Cơ bản | Người đánh đầu | Ván đầu người giữ 3 chuồn |  | `firstGame.leaderCard` | FIX | card | 3♣ | Duyệt D1 | ĐÃ CHỐT | 6,89 | Ván đầu: người giữ 3♣ đi đầu |
| 8 | 12 | Cơ bản | Bắt buộc 3 chuồn | Lượt mở đầu phải có 3 chuồn |  | `firstGame.mustIncludeLeaderCard` | ADM | bool | true | Đề xuất | Thiếu giá trị | 7 | validate_move: nước đầu phải chứa 3♣ (đơn/đôi/sảnh/bộ đều được) |
| 9 | 13 | Cơ bản | Các ván tiếp theo | Người thắng ván trước đánh đầu |  | `nextGame.leaderIsPreviousWinner` | FIX | bool | true | Đề xuất | Trừ ván sau tới trắng (60); người thắng rời bàn: Q-P2-1 | 7,60 | Người nhất ván trước đánh tự do |
| 10 | 14 | Cơ bản | Đánh theo lượt | Người chơi đánh bài hoặc bỏ lượt | Mỗi lượt tối đa 30 giây | `(→141) turn.timeLimitSeconds` | DER | — | theo 141 | Excel | Trùng 141 | 141,13 | Dùng 1 nguồn duy nhất là 141 |
| 11 | 15 | Cơ bản | Đè bài | Cùng loại, cùng số lá và mạnh hơn trừ chặt đặc biệt |  | `play.beatRule` | FIX | — | cùng loại, cùng số lá, mạnh hơn | Excel (D) | Rõ | 24,25 | compare_plays/can_beat |
| 12 | 16 | Cơ bản | Bỏ lượt | Người chơi có thể bỏ lượt |  | `play.passAllowed` | FIX | bool | true (trừ người mở vòng) | Đề xuất | Rõ | 13 | Leader không được pass |
| 13 | 17 | Cơ bản | Mất lượt | Đã bỏ không tham gia đến vòng bài mới | Quá 30 giây | `trick.passLocksUntilNewTrick` | FIX | bool | true | Excel (D) | BẤT NHẤT D/E (Q-P1) | Ngoại lệ 42; E 'Quá 30 giây' trùng 141/142 | Đã pass thì không đánh lại trong vòng |
| 14 | 18 | Cơ bản | Kết thúc vòng | Không ai chặn: người giữ quyền mở vòng mới |  | `trick.lastPlayerLeads` | FIX | — | người đánh cuối mở vòng mới | Excel (D) | Rõ | 105 | resolve_trick |
| 15 | 19 | Cơ bản | Hết bài | Hết bài đầu tiên đạt vị trí nhất |  | `finish.firstOutIsFirst` | FIX | — | — | Excel (D) | Rõ | 99 |  |
| 16 | 20 | Cơ bản | Xếp hạng | Theo thứ tự hết bài |  | `finish.rankByFinishOrder` | FIX | — | — | Excel (D) | Rõ | 99-102,107 |  |
| 17 | 21 | So sánh | So rác | So số rồi đến chất |  | `compare.single` | FIX | — | rank rồi suit | Excel (D) | Rõ | 5,6 | Unit test 52×52 |
| 18 | 22 | So sánh | So đôi | Đôi có giá trị lớn hơn thắng |  | `compare.pair` | FIX | — | rank | Excel (D) | Rõ |  |  |
| 19 | 23 | So sánh | Đôi bằng giá trị | So chất lá cao nhất trong đôi |  | `compare.pairTie` | FIX | — | suit lá cao nhất | Excel (D) | Rõ |  |  |
| 21 | 24 | So sánh | So sảnh | Sảnh bằng số lá; so quân cao nhất |  | `compare.straight` | FIX | — | cùng số lá; so lá cao nhất; dài ≥3 (giả định) | Excel (D)+Giả định | Thiếu độ dài tối thiểu (Q-P1) | 23 |  |
| 22 | 25 | So sánh | Sảnh bằng giá trị | So chất lá cao nhất |  | `compare.straightTie` | FIX | — | suit lá cao nhất | Excel (D) | Rõ |  |  |
| 23 | 26 | So sánh | Sảnh không chứa 2 | Cấm 2 xuất hiện trong sảnh thường |  | `straight.allowTwo` | FIX | bool | false | Excel (D) | Rõ | Áp dụng cả đôi thông (giả định) | Không vòng A-2-3 |
| 24 | 27 | So sánh | Không đánh khác loại | Không đè khác loại ngoài chặt |  | `play.noCrossType` | FIX | — | — | Excel (D) | Rõ | 25 |  |
| 25 | 28 | So sánh | Ngoại lệ chặt hàng | Bộ đặc biệt được đè khác loại |  | `play.chopException` | DER | — | theo bảng chặt 29-44 | Excel (D) | Rõ | 29-44 | can_beat dùng chop matrix |
| 26 | 29 | So sánh | So 2 | 2 cơ > 2 rô > 2 chuồn > 2 bích |  | `compare.twoSuit` | FIX | — | 2♥>2♦>2♣>2♠ | Excel (D) | Rõ | 6 |  |
| 27 | 30 | So sánh | So đôi 2 | So chất lá 2 lớn nhất trong đôi |  | `compare.pairOfTwos` | FIX | — | suit lá 2 lớn nhất | Excel (D) | Rõ | 44 |  |
| 29 | 31 | Chặt hàng | 3 đôi thông chặt heo | 3 đôi thông chặt 1 quân 2 |  | `chop.threePairSeq.vsSingleTwo` | ADM | bool | true | Đề xuất | Thiếu giá trị | 43,81,120 | Chỉ đúng lượt |
| 30 | 32 | Chặt hàng | 3 đôi thông chặt 3 đôi thông | Bộ lớn hơn thắng |  | `(cùng loại) threePairSeq vs threePairSeq` | DER | — | bộ lớn hơn thắng | Excel (D) | Rõ | 120 (điểm khi 'chặt đè') |  |
| 31 | 33 | Chặt hàng | Tứ quý chặt 1 heo | Cho phép tứ quý chặt 1 quân 2 |  | `chop.fourKind.vsSingleTwo` | ADM | bool | true | Đề xuất | Thiếu giá trị | 119 |  |
| 32 | 34 | Chặt hàng | Tứ quý chặt đôi heo | Cho phép tứ quý chặt đôi 2 |  | `chop.fourKind.vsPairTwo` | ADM | bool | true | Đề xuất | Thiếu giá trị | 119 |  |
| 33 | 35 | Chặt hàng | Tứ quý chặt 3 đôi thông | Cho phép tứ quý chặt 3 đôi thông |  | `chop.fourKind.vsThreePairSeq` | ADM | bool | true | Đề xuất | Thiếu giá trị | 119,41 |  |
| 34 | 36 | Chặt hàng | Tứ quý chặt tứ quý | Tứ quý lớn hơn thắng |  | `(cùng loại) fourKind vs fourKind` | DER | — | tứ quý lớn hơn | Excel (D) | Rõ | 119 |  |
| 35 | 37 | Chặt hàng | 4 đôi thông chặt 1 heo | Cho phép |  | `chop.fourPairSeq.vsSingleTwo` | ADM | bool | true | Excel (D: Cho phép) | Rõ | 121 |  |
| 36 | 38 | Chặt hàng | 4 đôi thông chặt đôi heo | Cho phép |  | `chop.fourPairSeq.vsPairTwo` | ADM | bool | true | Excel (D: Cho phép) | Rõ | 121 |  |
| 37 | 39 | Chặt hàng | 4 đôi thông chặt tứ quý | Cho phép |  | `chop.fourPairSeq.vsFourKind` | ADM | bool | true | Excel (D: Cho phép) | Rõ | 121 |  |
| 38 | 40 | Chặt hàng | 4 đôi thông chặt 3 đôi thông | Cho phép |  | `chop.fourPairSeq.vsThreePairSeq` | ADM | bool | true | Excel (D: Cho phép) | Rõ | 121 |  |
| 39 | 41 | Chặt hàng | 4 đôi thông chặt 4 đôi thông | Bộ lớn hơn thắng |  | `(cùng loại) fourPairSeq vs fourPairSeq` | DER | — | bộ lớn hơn | Excel (D) | Rõ | 121 |  |
| 41 | 42 | Chặt hàng | Chặt chồng | Cho phép tiếp tục chặt bộ vừa chặt |  | `chop.allowChain` | ADM | bool | true | Excel (D) | Rõ | 83,119-121 (cách tính) | Chặt chồng nhiều tầng |
| 42 | 43 | Chặt hàng | Chặt không cần vòng | 4 đôi thông có thể chặt ngoài lượt |  | `chop.fourPairSeq.outOfTurn` | ADM | bool | true | Excel (D) | CHƯA RÕ phạm vi (Q-P0-6) | Ngoại lệ của 13 | can_interrupt; race → server serialize |
| 43 | 44 | Chặt hàng | 3 đôi thông/ tứ quý cần vòng | Cần đến đúng lượt |  | `chop.requiresTurn (3 đôi thông + tứ quý)` | FIX | bool | true | Duyệt D6 | ĐÃ CHỐT (Excel sửa nhưng chưa lưu) | 13; chỉ 4 đôi thông được ngoài lượt (42) | Tứ quý/3 đôi thông phải đúng lượt, chưa pass |
| 44 | 45 | Chặt hàng | Đôi 2 lớn chặt đôi 2 nhỏ | Đôi 2 lớn có chứa 2 cơ chặt được đôi 2 nhỏ hơn | Phạt tiền như bị chặt đôi 2 | `chop.pairTwoOverPairTwo.scoreAsChop` | ADM | bool | true | Excel (E) | Cần xác nhận (Q-P1) | 27; 'tiền' → 'điểm' | Thực tế đôi 2 đè được đôi 2 luôn chứa 2♥ |
| 46 | 46 | Chặt hàng | Đánh heo cuối cùng | Cho phép 2 là lá cuối |  | `finish.allowTwoAsLastCard` | FIX | bool | true | Excel (D) + G3 | ĐÃ CHỐT |  |  |
| 47 | 47 | Chặt hàng | Chặt khi còn một lá | Cho phép chặt khi đối thủ còn 1 lá |  | `chop.allowWhenTargetHasOneCard` | FIX | bool | true | Excel (D) + G3 | ĐÃ CHỐT |  |  |
| 48 | 48 | Chặt hàng | Chặt sau khi có nhất | Cho phép khi ván vẫn tiếp tục |  | `chop.allowAfterFirstFinisher` | ADM | bool | true | Excel (D) | Rõ | 104 |  |
| 49 | 49 | Tới trắng | Tứ quý 2 | Tới trắng với 4 quân 2 |  | `instantWin.fourTwos` | ADM | bool | true | Đề xuất | Thiếu giá trị | 62,124 | check_instant_win sau chia |
| 52 | 50 | Tới trắng | 6 đôi bất kỳ | Tới trắng có 6 đôi bất kỳ |  | `instantWin.sixPairs` | ADM | bool | true | Đề xuất | CHƯA RÕ tứ quý =2 đôi? (Q-P1) | 62,124 |  |
| 53 | 51 | Tới trắng | Sảnh rồng | Tới trắng sảnh 3 đến A |  | `instantWin.dragonStraight` | ADM | bool | true | Đề xuất | CHƯA RÕ định nghĩa (Q-P0-4) | 62,124 | 12 lá 3→A, không cần đồng chất (giả định) |
| 58 | 52 | Chia lại | Tứ quý 3 ở ván đầu | Khi phải bắt buộc phải đánh 3 chuồn đầu tiên như ván đầu hoặc sau khi tới trắng mà có tứ quý 3 thì chia lại bài |  | `redeal.fourThrees` | ADM | bool | true | Excel (D, sửa 16:19) | ĐÃ CHỐT; thứ tự với tới trắng: R7 | Chỉ ván mở bằng 3♣ (7, 60) | detect_redeal |
| 59 | 53 | Chia lại | 3 hoặc 4 đôi thông chứa 3 chuồn ván đầu | Khi phải bắt buộc phải đánh 3 chuồn đầu tiên như ván đầu hoặc sau khi tới trắng mà có 3 hoặc 4 đôi thông chứa 3 chuồn thì chia lại bài |  | `redeal.pairSeqWithThreeClubs` | ADM | bool | true | Excel (D, sửa 16:19) | ĐÃ CHỐT; thứ tự với tới trắng: R7 | Chỉ ván mở bằng 3♣ (7, 60) | Có 33(gồm 3♣)-44-55 |
| 60 | 54 | Tới trắng | Tới trắng | Sau khi tới trắng thì ván tiếp theo 3 chuồn đánh trước |  | `opening.threeClubsAfterInstantWin` | FIX | bool | true | Excel (D, ID mới 16:19) | ĐÃ CHỐT | 7,8,9,58,59 | Ván sau tới trắng: mở bằng 3♣, có xét chia lại |
| 62 | 55 | Tới trắng | Tới trắng nhiều người | Tứ quý 2 > 6 đôi bất kỳ > Sảnh rồng |  | `instantWin.priorityOrder` | ADM | ordered list | [FOUR_TWOS, DRAGON, SIX_PAIRS] | Ảnh luật §6 (N1) | ĐÃ CHỐT | Trùng 64 | 4 heo > sảnh 3→A > 6 đôi |
| 63 | 56 | Tới trắng | Tới trắng đồng cấp | Ai đi trước thì thắng |  | `instantWin.tieBreak` | ADM | enum | SPLIT_EQUALLY | Ảnh luật §6 (N2) | ĐÃ CHỐT | 62,124 | Cùng loại → chia đều tiền |
| 64 | 57 | Tới trắng | Ưu tiên điều kiện | Thứ hạng các điều kiện tới trắng |  | `(→62) instantWin.priorityOrder` | DER | — | theo 62 | — | Trùng 62 | 62 | Gộp vào 62 |
| 65 | 58 | Tới trắng | Thưởng tới trắng | Hệ số điểm thưởng |  | `(→124) scoring.instantWin` | DER | — | theo 124 | — | Thiếu giá trị | 124 |  |
| 66 | 59 | Tới trắng | Tới trắng kết thúc ngay | Ván tự kết thúc sau chia bài |  | `instantWin.endsImmediately` | FIX | bool | true | Excel (D) | Rõ | 107 |  |
| 67 | 60 | Tới trắng | Tới trắng khi đang chơi | Có xét điều kiện sau khi bắt đầu hay không |  | `instantWin.checkDuringPlay` | ADM | bool | false | Đề xuất | Thiếu giá trị | 66 | Chỉ xét ngay sau chia |
| 68 | 61 | Phạt | Cóng | Chưa đánh lá nào khi đối thủ về nhất |  | `penalty.cong.enabled` | ADM | bool | true | Duyệt D7, D11, D15 | ĐÃ CHỐT | 123,72-77 | 200 = khoản bét → nhất; dừng ngay; 1 cóng thì 2 người còn lại đánh tiếp |
| 69 | 62 | Phạt | Cóng toàn bàn | Cả 3 đối thủ chưa đánh lá nào |  | `penalty.congAll (nhãn)` | DER | — | nhãn hiển thị | Duyệt D7, D12, G11 | ĐÃ CHỐT | 68,123 | Tính điểm như cóng thường: 3×200 + thối → nhất |
| 70 | 63 | Phạt | Thưởng cóng | Cộng điểm người thắng |  | `(→123) cong reward to first` | DER | — | người về nhất nhận | Duyệt D7 | ĐÃ CHỐT | 123 |  |
| 71 | 64 | Phạt | Phạt cóng | Trừ điểm người bị cóng |  | `(→123) cong penalty` | DER | — | 200/người cóng | Duyệt D7 | ĐÃ CHỐT | 123 |  |
| 72 | 65 | Phạt | Thối heo đen | Phạt giữ 2 bích/chuồn |  | `rot.blackTwo` | ADM | int | 100/lá | Duyệt D8, D12 | ĐÃ CHỐT | 117,85 | Thối người cóng → nhất; bét thường → người về 3 |
| 73 | 66 | Phạt | Thối heo đỏ | Phạt giữ 2 rô/cơ |  | `rot.redTwo` | ADM | int | 200/lá | Duyệt D8, D12 | ĐÃ CHỐT | 118,85 | Thối người cóng → nhất; bét thường → người về 3 |
| 74 | 67 | Phạt | Thối đôi heo | Phạt khi giữ đôi 2 |  | `(→72,73) rot.pairTwo` | DER | — | tổng 2 heo | Duyệt D8, G11 | ĐÃ CHỐT | 72,73 |  |
| 75 | 68 | Phạt | Thối tứ quý | Phạt khi còn tứ quý |  | `rot.fourKind` | ADM | int | 200 | Duyệt D8, D12 | ĐÃ CHỐT | 85 | Thối người cóng → nhất; bét thường → người về 3 |
| 76 | 69 | Phạt | Thối 3 đôi thông | Phạt khi còn 3 đôi thông |  | `rot.threePairSeq` | ADM | int | 200 | Duyệt D8, D12 | ĐÃ CHỐT | 85 | Thối người cóng → nhất; bét thường → người về 3 |
| 77 | 70 | Phạt | Thối 4 đôi thông | Phạt khi còn 4 đôi thông |  | `rot.fourPairSeq` | ADM | int | 200 | Duyệt D8, D12 | ĐÃ CHỐT | 85 | Thối người cóng → nhất; bét thường → người về 3; không tính trùng 3 đôi thông |
| 80 | 73 | Phạt | Phạt theo thứ hạng | Mức phạt nhất nhì ba bét | Theo hạng | `scoring.rankPoints.enabled` | DER | bool | true | Excel (E: Theo hạng) | Rõ | 112-115 |  |
| 81 | 74 | Phạt | Phạt bị chặt heo | Người bị chặt mất điểm |  | `chop.penaltyEnabled` | ADM | bool | true | Đề xuất | Thiếu giá trị | 119-122 |  |
| 82 | 75 | Phạt | Thưởng chặt heo | Người chặt nhận điểm |  | `(→81) chop reward` | DER | — | đối xứng 81 | — | Rõ | 132,133 |  |
| 83 | 76 | Phạt | Phạt chặt chồng | Tính từng lần chặt |  | `chop.chainSettlement` | ADM | enum | CUMULATIVE | Duyệt D3 | ĐÃ CHỐT | 41,119-121 | Người bị chặt cuối trả toàn chuỗi khi vòng kết thúc |
| 84 | 77 | Phạt | Thối hàng khi cóng | Cộng dồn |  | `rot.applyWhenCong` | FIX | bool | true | Duyệt D11, D12 | ĐÃ CHỐT | 68,69 | Người cóng bị xét thối heo + hàng, trả cho nhất |
| 85 | 78 | Phạt | Thối sau người nhất | Thời điểm kiểm tra hàng thối |  | `rot.checkTiming` | FIX | enum | AT_GAME_END_LAST_PLACE | Duyệt D8 | ĐÃ CHỐT | 104 | Chỉ người về 4 (+ cóng toàn bàn) |
| 87 | 79 | Phạt | Phạt bỏ trận | Xử thua khi thoát ván |  | `forfeit.policy` | OPS | enum | LOWEST_FREE_RANK (4→3→…) | Duyệt D9 | ĐÃ CHỐT; thối/cóng với người thoát: R6 | 145,144 |  |
| 88 | 80 | Phạt | Phạt hết giờ | Bỏ lượt hoặc xử thua |  | `(→142) timeout.action` | DER | — | mất lượt | Duyệt D9 | ĐÃ CHỐT | 142 |  |
| 89 | 81 | Thưởng đặc biệt | Đút mù | 3 bích là lá cuối |  | `special.blindThreeSpades` | ADM | bool | true | Duyệt D10, D14 | ĐÃ CHỐT | 125 | Về nhất + nước cuối là 3♠ đánh đơn → hết ván |
| 90 | 82 | Thưởng đặc biệt | Thưởng đút mù | Điểm thưởng khi đút mù |  | `(→125) blind reward` | DER | — | theo 125 | — | Thiếu giá trị | 125 |  |
| 99 | 83 | Kết thúc ván | Về nhất | Người hết bài đầu |  | `rank.first` | FIX | — | — | Excel (D) | Rõ |  |  |
| 100 | 84 | Kết thúc ván | Về nhì | Người hết bài thứ 2 |  | `rank.second` | FIX | — | — | Excel (D) | Rõ |  |  |
| 101 | 85 | Kết thúc ván | Về ba | Người hết bài thứ 3 |  | `rank.third` | FIX | — | — | Excel (D) | Rõ |  |  |
| 102 | 86 | Kết thúc ván | Về bét | Người cuối cùng còn bài |  | `rank.last` | FIX | — | — | Excel (D) | Rõ |  |  |
| 103 | 87 | Kết thúc ván | Kết thúc khi có nhất | Dừng ván sau người đầu hết bài | Không | `game.endMode` | FIX | enum | LAST_ONE_REMAINING | Excel (E: Không) + G2 | ĐÃ CHỐT | 104 |  |
| 104 | 88 | Kết thúc ván | Chơi đến còn 1 người | Tiếp tục cho đủ thứ hạng | Có | `game.endMode` | FIX | enum | LAST_ONE_REMAINING | Excel (E: Có) + G2 | ĐÃ CHỐT | 103 |  |
| 105 | 89 | Kết thúc ván | Chuyển quyền khi hết bài | Quy tắc chuyển người mở vòng | bắt được thì đi tiếp không bắt được thì đi theo chiều kim đồng hồ hưởng sái | `lead.afterFinisher` | FIX | enum | CATCH_CONTINUES_ELSE_NEXT_CLOCKWISE | Duyệt D2 | ĐÃ CHỐT | 13,14,106 | Không ai chặn → người còn bài kế tiếp theo chiều kim đồng hồ |
| 106 | 90 | Kết thúc ván | Bỏ qua người hết bài | Không tham gia lượt tiếp theo |  | `turn.skipFinished` | FIX | bool | true | Excel (D) | Rõ | 4 |  |
| 107 | 91 | Kết thúc ván | Xếp hạng khi tới trắng | Quy tắc các người chưa đánh | người bị cóng là bét | `instantWin.othersRanking` | FIX | enum | ALL_FOURTH | Duyệt D4 | ĐÃ CHỐT | 124 |  |
| 109 | 93 | Kết thúc ván | Hủy ván | Hủy do lỗi hoặc quyết định phòng |  | `game.cancelPolicy` | OPS | structured | chỉ hệ thống/Admin; không tính điểm | Đề xuất | Thiếu giá trị (Q-P1) |  |  |
| 111 | 94 | Điểm số | Điểm ban đầu | Điểm mỗi người khi bắt đầu phiên | 0 | `session.initialScore` | FIX | int | 0 | Excel (E) | Rõ | 133 |  |
| 112 | 95 | Điểm số | Điểm thắng | Điểm cho vị trí nhất | tùy chỉnh: vd 200 | `scoring.rank.first` | ADM | int | 200 | Excel (ví dụ) | Chưa chốt | 133: tổng 112-115 = 0 |  |
| 113 | 96 | Điểm số | Điểm nhì | Điểm vị trí nhì | tùy chỉnh: vd 100 | `scoring.rank.second` | ADM | int | 100 | Excel (ví dụ) | Chưa chốt | 133 |  |
| 114 | 97 | Điểm số | Điểm ba | Điểm vị trí ba | tùy chỉnh: vd -100 | `scoring.rank.third` | ADM | int | -100 | Excel (ví dụ) | Chưa chốt | 133 |  |
| 115 | 98 | Điểm số | Điểm bét | Điểm vị trí bét | tùy chỉnh: vd -200 | `scoring.rank.last` | ADM | int | -200 | Excel (ví dụ) | Chưa chốt | 133 |  |
| 117 | 100 | Điểm số | Điểm heo đen | Hệ số phạt 2 đen | 100 | `scoring.blackTwoValue` | ADM | int ≥0 | 100 | Excel (E) | Rõ | 72,119-121 |  |
| 118 | 101 | Điểm số | Điểm heo đỏ | Hệ số phạt 2 đỏ | 200 | `scoring.redTwoValue` | ADM | int ≥0 | 200 | Excel (E) | Rõ | 73,119-121 |  |
| 119 | 102 | Điểm số | Điểm tứ quý | Điểm phạt/thưởng tứ quý | tứ quý chặt heo thì tính theo heo / chặt đôi thông thì tính 1 heo đỏ / chặt đè tứ quý tính 2 heo đỏ  / có thể cộng dồn | `scoring.chop.fourKind` | ADM | matrix | xem bảng chặt §4 | Excel (E) | Rõ phần lớn | 83,118 |  |
| 120 | 103 | Điểm số | Điểm 3 đôi thông | Hệ số phạt/thưởng | đôi thông chặt heo thì tính theo heo /  đôi thông chặt đè đôi thông thì tính 1 heo đỏ / tính cộng dồn | `scoring.chop.threePairSeq` | ADM | matrix | xem bảng chặt §4 | Excel (E) | 'chặt đè' chưa rõ (Q-P1) | 83 |  |
| 121 | 104 | Điểm số | Điểm 4 đôi thông | Hệ số phạt/thưởng | có thể chặt tối đa 2 heo 1 lúc tính theo heo / chặt 3 đôi tính heo đỏ chặt tứ quý tính 2 heo đỏ / 4 đôi đè 4 đôi tính 2 heo đỏ / có thể cộng dồn | `scoring.chop.fourPairSeq` | ADM | matrix | xem bảng chặt §4 | Excel (E) | Rõ phần lớn | 83 |  |
| 122 | 105 | Điểm số | Điểm chặt hàng | Điểm trao đổi giữa người chặt và bị chặt |  | `(→119-121) scoring.chop.matrix` | DER | — | theo matrix | — | Thiếu giá trị | 119-121 |  |
| 123 | 106 | Điểm số | Điểm cóng | Hệ số phạt cóng | 200 | `scoring.congValue` | ADM | int ≥0 | 200 | Excel (E) + D7 | ĐÃ CHỐT → người về nhất | 68-71 |  |
| 124 | 107 | Điểm số | Điểm tới trắng | Thưởng theo loại tới trắng | 200*3 =600 | `scoring.instantWinPerLoser` | ADM | int ≥0 | 200 (×3 = 600) | Duyệt D4 | ĐÃ CHỐT; không xét thối | 65,107 |  |
| 125 | 108 | Điểm số | Điểm đút mù | Điểm thưởng đút mù (đánh 3 bích cuối và thắng luôn, kết thúc trận) | 200*3 = 600 | `scoring.blindThreeSpadesPerLoser` | ADM | int ≥0 | 200 (×3 = 600) | Duyệt D10 | ĐÃ CHỐT | 89 |  |
| 127 | 109 | Điểm số | Điểm âm | Cho phép tổng điểm âm | Có | `scoring.allowNegative` | FIX | bool | true | Excel (E) | Rõ | Bắt buộc true nếu 133=true |  |
| 128 | 110 | Điểm số | Giới hạn điểm | Ngưỡng thắng/thua phiên | Không giới hạn | `scoring.sessionLimit` | FIX | nullable int | null (không giới hạn) | Excel (E) | Rõ |  |  |
| 129 | 111 | Điểm số | Reset điểm | Reset khi bắt đầu phiên |  | `session.resetOnStart` | OPS | bool | true | Đề xuất | Thiếu giá trị | 111,148 |  |
| 130 | 112 | Điểm số | Tổng kết phiên | Xếp hạng theo điểm tích lũy |  | `session.summaryByTotal` | OPS | — | xếp hạng theo tổng điểm | Excel (D) | Rõ |  |  |
| 131 | 113 | Điểm số | Lịch sử điểm | Lưu biến động từng ván |  | `history.scoreLedger` | OPS | — | ledger từng ván | Excel (D) | Rõ |  |  |
| 132 | 114 | Điểm số | Chuyển điểm | Điểm người thua chuyển sang người thắng |  | `scoring.transferModel` | FIX | enum | PAIRWISE_TRANSFER | Excel (D) | Rõ | 133 |  |
| 133 | 115 | Điểm số | Bảo toàn điểm | Tổng điểm 4 người bằng 0 | Có | `scoring.zeroSum` | FIX | bool | true | Excel (E) | Rõ | 112-115 phải tổng 0 | Property test |
| 134 | 116 | Phòng online | Admin cấu hình luật | Chỉ chủ phòng được chỉnh luật |  | `rules.editPermission` | OPS | enum | SYSTEM_ADMIN_ONLY | YÊU CẦU MỚI (override Excel) | OVERRIDE | Excel ghi 'chủ phòng' → SAI |  |
| 135 | 117 | Phòng online | Luật toàn phòng | Cả 4 người dùng chung cấu hình |  | `rules.scope` | OPS | enum | GLOBAL | Yêu cầu | OVERRIDE (diễn giải global) |  |  |
| 136 | 118 | Phòng online | Khóa luật đang chơi | Không sửa cấu hình đang áp dụng |  | `rules.lockedDuringGame` | OPS | bool | true | Yêu cầu | Rõ | 156 |  |
| 137 | 119 | Phòng online | Thay đổi giữa các ván | Luật mới áp dụng từ ván tiếp |  | `rules.applyFromNextGame` | OPS | bool | true | Yêu cầu | Rõ | 156 | Thông báo version mới |
| 138 | 120 | Phòng online | Hiển thị luật phòng | Tất cả người chơi xem được |  | `rules.visibleToPlayers` | OPS | bool | true | Yêu cầu | Rõ |  | Hiển thị version/hash |
| 139 | 121 | Phòng online | Ready | Người chơi xác nhận sẵn sàng |  | `room.readyRequired` | OPS | bool | true | Excel (D) | Rõ |  |  |
| 140 | 122 | Phòng online | Tự bắt đầu | Đủ người ready thì bắt đầu |  | `room.autoStartWhenAllReady` | OPS | bool | true | Excel (D) | Rõ | 2 |  |
| 141 | 123 | Phòng online | Thời gian lượt | Giới hạn giây mỗi lượt | 30 | `turn.timeLimitSeconds` | ADM | int 10-120 | 30 | Excel (E) | Rõ | 10,13,142 |  |
| 142 | 124 | Phòng online | Hết thời gian | Auto pass hoặc xử lý khác | Tự bỏ lượt | `turn.timeoutAction` | ADM | enum | LOSE_TURN; leader: AUTO_PLAY_LOWEST_SINGLE | Duyệt D9, D13 | ĐÃ CHỐT | 88,8 | Ván mở 3♣: tự đánh 3♣ |
| 143 | 125 | Phòng online | Mất kết nối | Reconnect vào phòng |  | `conn.reconnect` | OPS | bool | true | Excel (D) | Rõ | 144 | Private snapshot khi reconnect |
| 144 | 126 | Phòng online | Giữ ghế | Giữ ghế tạm thời | 120 | `conn.seatHoldSeconds` | ADM | int 30-600 | 120 | Excel (E) | Rõ | 143,145 |  |
| 145 | 127 | Phòng online | Thoát giữa ván | Xử lý khi rời phòng |  | `room.leaveMidGame` | OPS | structured | →87 | Duyệt D9 | ĐÃ CHỐT | 87 |  |
| 146 | 128 | Phòng online | Thay người | Chỉ thay sau khi ván kết thúc |  | `room.replaceOnlyBetweenGames` | OPS | bool | true | Excel (D) | Rõ |  |  |
| 147 | 129 | Phòng online | Giải tán phòng | Chủ phòng có quyền đóng |  | `room.ownerCanClose` | OPS | bool | true | Excel (D) | Rõ (chỉ khi không có ván đang chơi?) |  |  |
| 148 | 130 | Phòng online | Khởi động lại phiên | Reset điểm/lịch sử theo chọn |  | `session.restart` | OPS | structured | chủ phòng, giữa các ván | Đề xuất | Ai được quyền? (Q-P2) | 129 |  |
| 149 | 131 | Phòng online | Lưu lịch sử ván | Lưu bộ bài, hành động, kết quả |  | `history.gameLog` | OPS | — | deck seed/order, events, result | Excel (D) | Rõ |  |  |
| 150 | 132 | Phòng online | Lưu lịch sử phiên | Lưu tổng điểm và kết quả |  | `history.sessionLog` | OPS | — | — | Excel (D) | Rõ |  |  |
| 151 | 133 | Phòng online | Chống gian lận | Server xác thực mọi nước đi |  | `security.serverAuthoritative` | FIX | — | — | Excel (D) | Rõ |  |  |
| 152 | 134 | Phòng online | Ẩn bài đối thủ | Không cho xem bài đối phương |  | `security.hideOpponentHands` | FIX | — | — | Excel (D) | Rõ | 154 | Property test không lộ bài |
| 153 | 135 | Phòng online | Xáo bài ngẫu nhiên | Server xáo bài |  | `security.serverShuffle` | FIX | — | CSPRNG (secrets) | Excel (D) | Rõ |  |  |
| 154 | 136 | Phòng online | Xem lại ván | Replay các hành động |  | `replay.enabled` | OPS | bool | true; lộ bài chỉ sau khi ván kết thúc | Đề xuất | Quyền xem (Q-P2) | 152 |  |
| 155 | 137 | Phòng online | Tranh chấp kết quả | Dựa log và snapshot luật |  | `dispute.evidence` | OPS | — | events + rules snapshot hash | Excel (D) | Rõ | 149,156 |  |
| 156 | 138 | Phòng online | Snapshot luật | Chốt cấu hình luật vào từng ván | Mỗi ván | `rules.snapshotPerGame` | FIX | — | Mỗi ván | Excel (E) | Rõ | 136,137 |  |

**Thống kê phân loại:** adminConfigurable: 45, derivedRule: 16, fixedInvariant: 48, operationalPolicy: 21 — tổng 130.

## Luật bổ sung ngoài Excel (không có Excel ID)

| Nguồn | Tên | ruleKey | Loại | Default | Mô tả |
|---|---|---|---|---|---|
| rule-image-2026-10-30 §3.3 | Bị nhốt 3♠ | `special.trappedThreeSpades` | ADM | enabled=true, perPlayer=200 | Người về chót mà khi kết thúc vẫn còn đúng 1 lá 3♠ trên tay phải đền làng: trả cho mỗi người còn lại, cộng thêm tiền bét thông thường |
