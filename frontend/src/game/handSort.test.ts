import { beforeEach, expect, test, vi } from "vitest";
import { cardLabel, rankOf } from "./cards";
import { groupHand, loadSortKind, saveSortKind, sortByCard, type GroupedHand } from "./handSort";

const RANKS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"];
const SUITS = ["♠", "♣", "♦", "♥"];

/** "10♥" → mã lá (hạng × 4 + chất, chất ♠ < ♣ < ♦ < ♥). */
function card(label: string): number {
  const rank = RANKS.indexOf(label.slice(0, -1));
  const suit = SUITS.indexOf(label.slice(-1));
  if (rank < 0 || suit < 0) throw new Error(`Lá không hợp lệ: ${label}`);
  return rank * 4 + suit;
}
const hand = (text: string) =>
  text
    .replace(/\|/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map(card);
const show = (g: GroupedHand) => g.groups.map((grp) => grp.cards.map(cardLabel).join(" ")).join(" | ");

/** Bộ xáo trộn có seed để kết quả kiểm thử lặp lại được. */
function shuffled<T>(items: readonly T[], seed: number): T[] {
  let s = seed >>> 0 || 1;
  const rand = () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}

// --- Bốn ca bắt buộc -----------------------------------------------------------------------------------------------

const REQUIRED: Array<[string, string]> = [
  ["17:37", "3♠ 4♥ 5♥ 6♠ 7♠ 8♦ 9♣ 10♠ J♠ | 7♦ | 10♥ | K♣ | A♦"],
  ["17:40 (11 lá còn lại sau khi đánh đôi 4)", "10♠ 10♣ 10♦ | Q♠ Q♦ Q♥ | K♦ K♥ | 5♥ | 7♠ | 9♣"],
  ["17:43", "7♥ 8♣ 9♠ | 3♠ 3♥ | 4♠ 4♥ | 6♠ 6♦ | A♣ A♥ | Q♣ | 2♣"],
  ["18:06", "9♦ 10♦ J♥ | 8♠ 8♥ | J♣ J♦ | K♠ K♦ | 3♣ | 6♦ | A♦ | 2♦"],
];

test.each(REQUIRED)("ca bắt buộc %s", (_name, expected) => {
  expect(show(groupHand(hand(expected)))).toBe(expected);
});

test.each(REQUIRED)("ca bắt buộc %s: đảo thứ tự đầu vào cho cùng kết quả", (_name, expected) => {
  const ids = hand(expected);
  for (let seed = 1; seed <= 40; seed++) expect(show(groupHand(shuffled(ids, seed)))).toBe(expected);
  expect(show(groupHand([...ids].reverse()))).toBe(expected);
});

test.each(REQUIRED)("ca bắt buộc %s: mọi ID xuất hiện đúng một lần", (_name, expected) => {
  const ids = hand(expected);
  const out = groupHand(shuffled(ids, 7));
  expect([...out.order].sort((a, b) => a - b)).toEqual([...ids].sort((a, b) => a - b));
  expect(out.groups.flatMap((g) => g.cards)).toEqual(out.order);
});

// --- Xếp theo lá ---------------------------------------------------------------------------------------------------

test("xếp theo lá: hạng 3..A,2 rồi chất ♠ < ♣ < ♦ < ♥", () => {
  const ids = hand("2♠ A♥ 10♣ 3♥ 3♠ 10♦ J♠ 3♣");
  expect(sortByCard(ids).map(cardLabel).join(" ")).toBe("3♠ 3♣ 3♥ 10♣ 10♦ J♠ A♥ 2♠");
  expect(ids.map(cardLabel).join(" ")).toBe("2♠ A♥ 10♣ 3♥ 3♠ 10♦ J♠ 3♣"); // không sửa mảng đầu vào
});

// --- Ca biên -------------------------------------------------------------------------------------------------------

test("tay rỗng và tay một lá", () => {
  expect(groupHand([])).toEqual({ groups: [], order: [] });
  expect(show(groupHand(hand("2♥")))).toBe("2♥");
  expect(groupHand(hand("7♦")).groups).toEqual([{ type: "SINGLE", cards: [card("7♦")] }]);
});

test("lá 2 không vào sảnh: 2 luôn là lá lẻ / đôi / bộ ba", () => {
  expect(show(groupHand(hand("Q♠ K♣ A♦ 2♥")))).toBe("Q♠ K♣ A♦ | 2♥"); // sảnh Q-K-A, 2 đứng riêng
  expect(show(groupHand(hand("K♠ A♣ 2♦")))).toBe("K♠ | A♣ | 2♦"); // K-A-2 không phải sảnh
});

test("nhiều sảnh chồng nhau: ưu tiên sảnh dài trước, lá cùng hạng chia theo chất", () => {
  // Hai sảnh 3-8 (6 lá) + 4-7 (4 lá) cũng 2 nhóm như hai sảnh 5 lá; nhóm dài đứng trước. Hạng 4..7 mỗi hạng có đúng
  // 2 lá nên sảnh đứng trước nhận lá chất nhỏ (♠).
  expect(show(groupHand(hand("3♠ 4♠ 5♠ 6♠ 7♠ 4♣ 5♣ 6♣ 7♣ 8♣")))).toBe("3♠ 4♠ 5♠ 6♠ 7♠ 8♣ | 4♣ 5♣ 6♣ 7♣");
});

test("tứ quý được giữ khi không có cách chia nào ít nhóm hơn", () => {
  expect(show(groupHand(hand("5♠ 5♣ 5♦ 5♥ 9♠ 9♣ J♦")))).toBe("5♠ 5♣ 5♦ 5♥ | 9♠ 9♣ | J♦");
  expect(groupHand(hand("5♠ 5♣ 5♦ 5♥ 9♠ 9♣ J♦")).groups[0]!.type).toBe("FOUR_KIND");
});

test("tứ quý bị tách ra khi tách thì lập được sảnh (ít nhóm hơn)", () => {
  // 3♠ 4♠ 5? 6♠ thành sảnh + bộ ba 5 còn lại = 2 nhóm, tốt hơn tứ quý + 3 lá lẻ = 4 nhóm.
  expect(show(groupHand(hand("3♠ 4♠ 5♠ 5♣ 5♦ 5♥ 6♠")))).toBe("3♠ 4♠ 5♠ 6♠ | 5♣ 5♦ 5♥");
});

test("đôi thông: nhận diện từ 3 đôi liên tiếp, không có đôi thông 2 đôi", () => {
  const six = groupHand(hand("3♠ 3♣ 4♠ 4♣ 5♠ 5♣ 9♦"));
  expect(six.groups.map((g) => g.type)).toEqual(["PAIR_SEQ", "SINGLE"]);
  expect(show(six)).toBe("3♠ 3♣ 4♠ 4♣ 5♠ 5♣ | 9♦");
  // Chỉ 2 đôi liên tiếp thì không phải đôi thông: hai đôi riêng.
  expect(groupHand(hand("3♠ 3♣ 4♠ 4♣")).groups.map((g) => g.type)).toEqual(["PAIR", "PAIR"]);
  // Hạng thừa của tứ quý tách ra thành đôi: 3♠ 3♣ vào đôi thông, 3♦ 3♥ còn lại là một đôi.
  expect(show(groupHand(hand("3♠ 3♣ 3♦ 3♥ 4♠ 4♣ 5♠ 5♣")))).toBe("3♠ 3♣ 4♠ 4♣ 5♠ 5♣ | 3♦ 3♥");
});

test("thứ tự hiển thị: Sảnh → Tứ quý → Đôi thông → Bộ ba → Đôi → Lá lẻ", () => {
  const out = groupHand(hand("3♠ 4♠ 5♠ | 8♠ 8♣ 8♦ 8♥ | J♠ J♣ Q♠ Q♣ K♠ K♣"));
  expect(out.groups.map((g) => g.type)).toEqual(["STRAIGHT", "FOUR_KIND", "PAIR_SEQ"]);
  const mixed = groupHand(hand("3♠ 4♠ 5♠ 7♣ 7♦ 9♠ 9♣ 9♦ K♠ A♦"));
  expect(mixed.groups.map((g) => g.type)).toEqual(["STRAIGHT", "TRIPLE", "PAIR", "SINGLE", "SINGLE"]);
});

test("trong cùng loại: hạng bắt đầu thấp trước; cùng hạng bắt đầu thì nhóm dài trước", () => {
  const out = groupHand(hand("9♠ 9♣ K♠ K♣ 4♠ 4♣ 6♦ A♠ 2♥"));
  expect(show(out)).toBe("4♠ 4♣ | 9♠ 9♣ | K♠ K♣ | 6♦ | A♠ | 2♥");
});

// --- Tính chất chung (tay ngẫu nhiên) ------------------------------------------------------------------------------

const isSameRank = (ids: readonly number[]) => ids.every((c) => rankOf(c) === rankOf(ids[0]!));
const consecutive = (ranks: number[]) => ranks.every((r, i) => i === 0 || r === ranks[i - 1]! + 1);

/** Kiểm tra nhóm hợp lệ viết độc lập, theo đúng luật của `classify` trong engine. */
function validShape(ids: readonly number[]): boolean {
  const n = ids.length;
  if (n === 0 || new Set(ids).size !== n) return false;
  if (isSameRank(ids)) return n <= 4;
  const counts = new Map<number, number>();
  for (const c of ids) counts.set(rankOf(c), (counts.get(rankOf(c)) ?? 0) + 1);
  const ranks = [...counts.keys()].sort((a, b) => a - b);
  if (ranks.includes(12) || !consecutive(ranks)) return false;
  const values = [...counts.values()];
  if (n >= 3 && values.every((v) => v === 1)) return true; // sảnh
  return ranks.length >= 3 && values.every((v) => v === 2); // đôi thông
}

/** Số nhóm ít nhất tìm bằng vét cạn độc lập (không dùng bitmask-DP của bản cài đặt). */
function bruteForceMinGroups(ids: readonly number[]): number {
  const memo = new Map<string, number>();
  const go = (rest: number[]): number => {
    if (rest.length === 0) return 0;
    const key = rest.join(",");
    const hit = memo.get(key);
    if (hit !== undefined) return hit;
    const [first, ...others] = rest;
    let best = Infinity;
    for (let mask = 0; mask < 1 << others.length; mask++) {
      const group = [first!, ...others.filter((_, i) => mask & (1 << i))];
      if (!validShape(group)) continue;
      const remaining = others.filter((_, i) => !(mask & (1 << i)));
      best = Math.min(best, 1 + go(remaining));
    }
    memo.set(key, best);
    return best;
  };
  return go([...ids].sort((a, b) => a - b));
}

function randomHand(size: number, seed: number): number[] {
  return shuffled(Array.from({ length: 52 }, (_, i) => i), seed).slice(0, size);
}

test("tay ngẫu nhiên 13 lá: mỗi lá đúng một lần, mọi nhóm hợp lệ, đúng thứ tự loại, kết quả không phụ thuộc thứ tự vào", () => {
  const typeOrder = ["STRAIGHT", "FOUR_KIND", "PAIR_SEQ", "TRIPLE", "PAIR", "SINGLE"];
  for (let seed = 1; seed <= 300; seed++) {
    const ids = randomHand(13, seed);
    const out = groupHand(ids);
    expect([...out.order].sort((a, b) => a - b)).toEqual([...ids].sort((a, b) => a - b));
    expect(out.groups.every((g) => validShape(g.cards))).toBe(true);
    const types = out.groups.map((g) => typeOrder.indexOf(g.type));
    expect(types).toEqual([...types].sort((a, b) => a - b));
    for (const g of out.groups) expect([...g.cards]).toEqual([...g.cards].sort((a, b) => a - b)); // lá xếp theo hạng rồi chất
    expect(show(groupHand(shuffled(ids, seed + 1000)))).toBe(show(out));
  }
});

test("số nhóm đúng bằng số nhóm ít nhất tìm bằng vét cạn độc lập (tay 9 lá)", () => {
  for (let seed = 1; seed <= 60; seed++) {
    const ids = randomHand(9, seed);
    expect(groupHand(ids).groups.length).toBe(bruteForceMinGroups(ids));
  }
});

test("tay nhiều bài cùng hạng và liền hạng (khó nhất cho bộ chia): vẫn đúng và nhanh", () => {
  // 13 lá thuộc 5 hạng liên tiếp: nhiều cách chia hòa nhau (chỉ đo tốc độ, tính hợp lệ và bất biến thứ tự vào).
  const dense = hand("3♠ 3♣ 3♦ 4♠ 4♣ 4♥ 5♠ 5♦ 5♥ 6♠ 6♣ 7♦ 7♥");
  const started = performance.now();
  const out = groupHand(dense);
  expect(performance.now() - started).toBeLessThan(500);
  expect([...out.order].sort((a, b) => a - b)).toEqual([...dense].sort((a, b) => a - b));
  expect(out.groups.every((g) => validShape(g.cards))).toBe(true);
  expect(show(groupHand(shuffled(dense, 99)))).toBe(show(out));

  // Đối chiếu số nhóm với vét cạn trên một tay ít lá hơn (vét cạn 13 lá quá chậm) nhưng vẫn nhiều hạng trùng.
  const small = hand("3♠ 3♣ 3♦ 4♠ 4♣ 4♥ 5♠ 5♦ 6♠ 7♦");
  expect(groupHand(small).groups.length).toBe(bruteForceMinGroups(small));
});

// --- Cache và ghi nhớ chế độ ---------------------------------------------------------------------------------------

test("cache theo tập ID lá: cùng tập (kể cả đảo thứ tự) trả về đúng một đối tượng, tập khác thì tính lại", () => {
  const ids = hand("3♠ 4♠ 5♠ 9♦ K♣");
  const first = groupHand(ids);
  expect(groupHand(shuffled(ids, 3))).toBe(first);
  expect(groupHand(ids.slice(1))).not.toBe(first);
});

beforeEach(() => window.localStorage.clear());

test("ghi nhớ chế độ xếp bài đã chọn", () => {
  expect(loadSortKind()).toBe("card"); // mặc định: xếp theo lá
  saveSortKind("group");
  expect(window.localStorage.getItem("tlmn_hand_sort")).toBe("group");
  expect(loadSortKind()).toBe("group");
  window.localStorage.setItem("tlmn_hand_sort", "rác"); // giá trị lạ → về mặc định
  expect(loadSortKind()).toBe("card");
});

test("trình duyệt chặn localStorage: vẫn nhớ chế độ trong bộ nhớ, không báo lỗi", () => {
  const blocked = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  const blockedSet = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => saveSortKind("group")).not.toThrow();
  expect(loadSortKind()).toBe("group");
  blocked.mockRestore();
  blockedSet.mockRestore();
});
