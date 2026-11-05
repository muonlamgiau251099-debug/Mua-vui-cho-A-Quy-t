// Xếp bài trên tay (chỉ ảnh hưởng giao diện; kiểm tra nước đi và luật chặt vẫn do server / engine).
//
// Hai chế độ:
//  - "card"  : xếp theo lá — tăng dần theo hạng 3..A,2 rồi theo chất ♠ < ♣ < ♦ < ♥ (chính là thứ tự mã lá).
//  - "group" : xếp theo bộ — chia 13 lá thành các nhóm hợp lệ (sảnh, tứ quý, đôi thông, bộ ba, đôi, lá lẻ) theo cách
//              tốt nhất; hình dạng nhóm hợp lệ giống `classify` của engine (sảnh ≥ 3 lá, đôi thông ≥ 3 đôi,
//              đều không chứa lá 2).
//
// Cách chia tốt nhất: so lần lượt các tiêu chí (chỉ xét tiêu chí sau khi tiêu chí trước hòa)
//   1. ít nhóm nhất (mỗi lá lẻ là một nhóm);
//   2. nhiều bộ chặt hơn: số tứ quý, rồi số đôi thông theo độ dài giảm dần;
//   2b. (bổ sung, suy ra từ ca bắt buộc 17:37) ít sảnh hơn = giữ sảnh dài thay vì tách làm hai: 9 lá 3..J + 4 lá lẻ
//       thắng hai sảnh 5 lá + 3 lá lẻ dù tiêu chí 3 ngược lại, vì hai cách đều 5 nhóm;
//   3. ít lá lẻ nhất;
//   4. nhiều bộ cùng hạng hơn (đôi + bộ ba);
//   5. chỉ khác chất của lá đưa vào sảnh: hạng có đúng 2 lá → đưa lá chất nhỏ vào sảnh; đúng 3 lá → đưa lá chất lớn nhất;
//   6. còn hòa thì lấy kết quả đứng trước theo thứ tự hiển thị → đầu ra luôn ổn định.
// Tiêu chí 1–4 cộng dồn được nên dùng quy hoạch động theo bitmask (≤ 13 lá → ≤ 8192 trạng thái); tiêu chí 5–6 chọn
// trong số các cách chia tối ưu của tiêu chí 1–4.

import { rankOf } from "./cards";

export type SortKind = "card" | "group";
export type GroupType = "STRAIGHT" | "FOUR_KIND" | "PAIR_SEQ" | "TRIPLE" | "PAIR" | "SINGLE";
export type HandGroup = { readonly type: GroupType; readonly cards: readonly number[] };
export type GroupedHand = { readonly groups: readonly HandGroup[]; readonly order: readonly number[] };

const TWO_RANK = 12; // lá 2 không nằm trong sảnh / đôi thông
const LAST_RUN_RANK = 11; // A
const MAX_PAIR_SEQ = 12; // đôi thông dài nhất có thể (3..A)
const MAX_BITS = 24; // bitmask 32-bit; tay bài thật chỉ có ≤ 13 lá
const CACHE_LIMIT = 64;

// Thứ tự hiển thị từ trái sang phải: Sảnh → Tứ quý → Đôi thông → Bộ ba → Đôi → Lá lẻ.
const TYPE_ORDER: Record<GroupType, number> = {
  STRAIGHT: 0,
  FOUR_KIND: 1,
  PAIR_SEQ: 2,
  TRIPLE: 3,
  PAIR: 4,
  SINGLE: 5,
};

const suitOf = (card: number) => card % 4;

/** Xếp theo lá: hạng 3..A,2 rồi chất ♠ < ♣ < ♦ < ♥ (mã lá = hạng × 4 + chất). */
export function sortByCard(ids: readonly number[]): number[] {
  return [...ids].sort((a, b) => a - b);
}

// --- Vector điểm (càng lớn càng tốt, so từ trái sang phải) ---------------------------------------------------------
// [ -số nhóm, số tứ quý, số đôi thông dài 12 … ngắn 3, -số sảnh, -số lá lẻ, số bộ cùng hạng (đôi + bộ ba) ]
const V_GROUPS = 0;
const V_FOUR = 1;
const V_PAIR_SEQ = 2; // + (MAX_PAIR_SEQ - độ dài): đôi thông dài hơn đứng trước
const V_STRAIGHTS = V_PAIR_SEQ + (MAX_PAIR_SEQ - 2); // -số sảnh (tiêu chí bổ sung 2b)
const V_SINGLES = V_STRAIGHTS + 1;
const V_SAME_RANK = V_SINGLES + 1;
const VEC_LEN = V_SAME_RANK + 1;

type Candidate = {
  mask: number;
  type: GroupType;
  start: number; // hạng thấp nhất trong nhóm
  ids: number[]; // đã xếp tăng dần
  vec: number[];
};

const ZERO = new Array<number>(VEC_LEN).fill(0);
const addVec = (a: number[], b: number[]) => a.map((x, i) => x + b[i]!);

function compareVec(a: number[], b: number[]): number {
  for (let i = 0; i < VEC_LEN; i++) if (a[i] !== b[i]) return a[i]! - b[i]!;
  return 0;
}

function candidateVec(type: GroupType, pairs: number): number[] {
  const v = new Array<number>(VEC_LEN).fill(0);
  v[V_GROUPS] = -1;
  if (type === "FOUR_KIND") v[V_FOUR] = 1;
  if (type === "PAIR_SEQ") v[V_PAIR_SEQ + (MAX_PAIR_SEQ - Math.min(pairs, MAX_PAIR_SEQ))] = 1;
  if (type === "STRAIGHT") v[V_STRAIGHTS] = -1;
  if (type === "SINGLE") v[V_SINGLES] = -1;
  if (type === "PAIR" || type === "TRIPLE") v[V_SAME_RANK] = 1;
  return v;
}

/** Sinh mọi nhóm hợp lệ có thể lập từ tay bài (một lần cho mỗi tay), chia theo vị trí bit thấp nhất. */
function buildCandidates(ids: number[]): Candidate[][] {
  const byRank: number[][] = Array.from({ length: TWO_RANK + 1 }, () => []);
  ids.forEach((id, i) => byRank[rankOf(id)]!.push(i));

  const lowest: Candidate[][] = ids.map(() => []);
  const add = (idx: number[], type: GroupType, pairs = 0) => {
    const sorted = [...idx].sort((a, b) => a - b);
    const cand: Candidate = {
      mask: sorted.reduce((m, i) => m | (1 << i), 0),
      type,
      start: rankOf(ids[sorted[0]!]!),
      ids: sorted.map((i) => ids[i]!),
      vec: candidateVec(type, pairs),
    };
    lowest[sorted[0]!]!.push(cand);
  };

  for (let r = 0; r <= TWO_RANK; r++) {
    const idx = byRank[r]!;
    idx.forEach((a) => add([a], "SINGLE"));
    for (let i = 0; i < idx.length; i++) {
      for (let j = i + 1; j < idx.length; j++) {
        add([idx[i]!, idx[j]!], "PAIR");
        for (let k = j + 1; k < idx.length; k++) add([idx[i]!, idx[j]!, idx[k]!], "TRIPLE");
      }
    }
    if (idx.length === 4) add(idx, "FOUR_KIND");
  }

  // Sảnh: mỗi hạng một lá, ≥ 3 hạng liên tiếp, không có lá 2.
  const straight = (r: number, chosen: number[]) => {
    for (const idx of byRank[r]!) {
      chosen.push(idx);
      if (chosen.length >= 3) add(chosen, "STRAIGHT");
      if (r + 1 <= LAST_RUN_RANK && byRank[r + 1]!.length > 0) straight(r + 1, chosen);
      chosen.pop();
    }
  };
  // Đôi thông: mỗi hạng đủ hai lá, ≥ 3 hạng liên tiếp, không có lá 2.
  const pairSeq = (r: number, chosen: number[]) => {
    const idx = byRank[r]!;
    for (let i = 0; i < idx.length; i++) {
      for (let j = i + 1; j < idx.length; j++) {
        chosen.push(idx[i]!, idx[j]!);
        if (chosen.length >= 6) add(chosen, "PAIR_SEQ", chosen.length / 2);
        if (r + 1 <= LAST_RUN_RANK && byRank[r + 1]!.length >= 2) pairSeq(r + 1, chosen);
        chosen.pop();
        chosen.pop();
      }
    }
  };
  for (let r = 0; r <= LAST_RUN_RANK; r++) {
    if (byRank[r]!.length >= 1) straight(r, []);
    if (byRank[r]!.length >= 2) pairSeq(r, []);
  }
  return lowest;
}

// --- Chọn cách chia ------------------------------------------------------------------------------------------------

function compareNumbers(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return a[i]! - b[i]!;
  return a.length - b.length;
}

/** Thứ tự hiển thị của các nhóm: loại → hạng bắt đầu thấp trước → nhóm dài trước → từng lá. */
function compareGroupsForDisplay(a: Candidate, b: Candidate): number {
  return (
    TYPE_ORDER[a.type] - TYPE_ORDER[b.type] ||
    a.start - b.start ||
    b.ids.length - a.ids.length ||
    compareNumbers(a.ids, b.ids)
  );
}

type Scored = { groups: Candidate[]; structure: number[]; suitCost: number[]; cardKey: number[] };

function score(partition: Candidate[], rankCount: number[]): Scored {
  const groups = [...partition].sort(compareGroupsForDisplay);
  const structure: number[] = [];
  const suitCost: number[] = [];
  const cardKey: number[] = [];
  for (const g of groups) {
    structure.push(TYPE_ORDER[g.type], g.start, -g.ids.length); // hình dạng nhóm, chưa tính chất
    cardKey.push(...g.ids, -1);
    if (g.type !== "STRAIGHT") continue;
    for (const id of g.ids) {
      const count = rankCount[rankOf(id)]!;
      // Tiêu chí 5: hạng có 2 lá → lá chất nhỏ vào sảnh; hạng có 3 lá → lá chất lớn nhất vào sảnh.
      suitCost.push(count === 2 ? suitOf(id) : count === 3 ? 3 - suitOf(id) : 0);
    }
  }
  return { groups, structure, suitCost, cardKey };
}

const compareScored = (a: Scored, b: Scored) =>
  compareNumbers(a.structure, b.structure) || compareNumbers(a.suitCost, b.suitCost) || compareNumbers(a.cardKey, b.cardKey);

const MAX_TIES = 4096; // chặn trường hợp cực đoan; tay 13 lá thực tế chỉ có vài chục cách chia hòa nhau

function solve(sortedIds: number[]): GroupedHand {
  const n = sortedIds.length;
  if (n === 0) return { groups: [], order: [] };
  if (n > MAX_BITS) {
    return { groups: sortedIds.map((id) => ({ type: "SINGLE", cards: [id] })), order: sortedIds };
  }

  const candidates = buildCandidates(sortedIds);
  const lowBit = (mask: number) => 31 - Math.clz32(mask & -mask);
  const memo = new Map<number, number[]>();

  // Điểm tốt nhất của các lá còn lại trong `mask`: chọn lá đầu tiên còn lại và thử mọi nhóm hợp lệ chứa nó.
  const best = (mask: number): number[] => {
    if (mask === 0) return ZERO;
    const cached = memo.get(mask);
    if (cached) return cached;
    let top: number[] | null = null;
    for (const c of candidates[lowBit(mask)]!) {
      if ((c.mask & mask) !== c.mask) continue;
      const v = addVec(c.vec, best(mask ^ c.mask));
      if (!top || compareVec(v, top) > 0) top = v;
    }
    memo.set(mask, top!); // luôn có ít nhất nhóm "lá lẻ"
    return top!;
  };

  // Liệt kê mọi cách chia đạt điểm tối ưu (tiêu chí 1–4) để áp tiêu chí 5–6.
  const optimal: Candidate[][] = [];
  const walk = (mask: number, acc: Candidate[]) => {
    if (optimal.length >= MAX_TIES) return;
    if (mask === 0) {
      optimal.push([...acc]);
      return;
    }
    const target = best(mask);
    for (const c of candidates[lowBit(mask)]!) {
      if ((c.mask & mask) !== c.mask) continue;
      if (compareVec(addVec(c.vec, best(mask ^ c.mask)), target) !== 0) continue;
      acc.push(c);
      walk(mask ^ c.mask, acc);
      acc.pop();
    }
  };
  walk((1 << n) - 1, []);

  const rankCount = new Array<number>(TWO_RANK + 1).fill(0);
  for (const id of sortedIds) rankCount[rankOf(id)]!++;
  let chosen: Scored | null = null;
  for (const partition of optimal) {
    const s = score(partition, rankCount);
    if (!chosen || compareScored(s, chosen) < 0) chosen = s;
  }

  const groups: HandGroup[] = chosen!.groups.map((g) => ({ type: g.type, cards: g.ids }));
  return { groups, order: groups.flatMap((g) => g.cards) };
}

const cache = new Map<string, GroupedHand>();

/**
 * Xếp theo bộ. Kết quả chỉ phụ thuộc tập ID lá (không phụ thuộc thứ tự đầu vào) và được cache theo tập đó:
 * chỉ tính lại khi các lá trên tay thay đổi. Mỗi lá xuất hiện đúng một lần ở đầu ra.
 */
export function groupHand(ids: readonly number[]): GroupedHand {
  const sorted = [...new Set(ids)].sort((a, b) => a - b);
  const key = sorted.join(",");
  const hit = cache.get(key);
  if (hit) return hit;
  const result = solve(sorted);
  cache.set(key, result);
  if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
  return result;
}

// --- Ghi nhớ chế độ đã chọn (qua lượt, ván tiếp theo và lần tải lại trang) --------------------------------------------

const STORAGE_KEY = "tlmn_hand_sort";
let remembered: SortKind = "card"; // dự phòng khi trình duyệt chặn localStorage (vd chế độ riêng tư)

export function loadSortKind(): SortKind {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "card" || stored === "group" ? stored : "card"; // chưa chọn (hoặc giá trị lạ): xếp theo lá
  } catch {
    return remembered; // localStorage bị chặn: dùng giá trị đã nhớ trong bộ nhớ
  }
}

export function saveSortKind(kind: SortKind): void {
  remembered = kind;
  try {
    window.localStorage.setItem(STORAGE_KEY, kind);
  } catch {
    /* bỏ qua: vẫn nhớ trong bộ nhớ cho tới khi tải lại trang */
  }
}
