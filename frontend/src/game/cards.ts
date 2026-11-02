// Mã lá bài giống engine: id = rank * 4 + suit; rank 3→0 … A→11, 2→12; suit ♠0 ♣1 ♦2 ♥3.

const RANKS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"];
const SUITS = ["♠", "♣", "♦", "♥"];

export const rankOf = (card: number) => Math.floor(card / 4);
export const suitOf = (card: number) => card % 4;
export const isRed = (card: number) => suitOf(card) >= 2;
export const cardLabel = (card: number) => `${RANKS[rankOf(card)]}${SUITS[suitOf(card)]}`;
export const cardsLabel = (cards: number[]) => [...cards].sort((a, b) => a - b).map(cardLabel).join(" ");

export type SortMode = "rank" | "suit";

export function sortHand(cards: number[], mode: SortMode): number[] {
  const copy = [...cards];
  return mode === "rank" ? copy.sort((a, b) => a - b) : copy.sort((a, b) => suitOf(a) - suitOf(b) || a - b);
}

const COMBO_LABEL: Record<string, string> = {
  SINGLE: "Rác",
  PAIR: "Đôi",
  TRIPLE: "Sám",
  FOUR_KIND: "Tứ quý",
  STRAIGHT: "Sảnh",
  PAIR_SEQ: "Đôi thông",
};
export const comboLabel = (combo: string | null) => (combo ? (COMBO_LABEL[combo] ?? combo) : "");

const REASON_LABEL: Record<string, string> = {
  RANK: "Điểm hạng",
  CONG: "Cóng",
  CHOP_CHAIN: "Chặt",
  INSTANT_WIN: "Tới trắng",
  BLIND_THREE_SPADES: "Đút mù 3♠",
  TRAPPED_THREE_SPADES: "Bị nhốt 3♠",
  ROT_BLACK_TWO: "Thối heo đen",
  ROT_RED_TWO: "Thối heo đỏ",
  ROT_FOUR_KIND: "Thối tứ quý",
  ROT_THREE_PAIR_SEQ: "Thối 3 đôi thông",
  ROT_FOUR_PAIR_SEQ: "Thối 4 đôi thông",
};
export const reasonLabel = (reason: string) => REASON_LABEL[reason] ?? reason;

const ERROR_LABEL: Record<string, string> = {
  NOT_YOUR_TURN: "Chưa đến lượt bạn",
  CANNOT_BEAT: "Bài chưa đủ lớn để chặn",
  INVALID_COMBINATION: "Bộ bài không hợp lệ",
  MUST_INCLUDE_THREE_CLUBS: "Nước đầu phải có 3♣",
  LEADER_CANNOT_PASS: "Bạn đang mở vòng, không được bỏ lượt",
  STALE_STATE: "Bàn vừa thay đổi, hãy thử lại",
};
export const errorLabel = (code: string, fallback: string) => ERROR_LABEL[code] ?? fallback;

/** Chuyển lá ở vị trí `from` sang vị trí `to` (tính trên danh sách sau khi đã bỏ lá đó ra). Không sửa mảng gốc. */
export function moveCard(order: number[], from: number, to: number): number[] {
  if (from < 0 || from >= order.length) return order;
  const rest = order.filter((_, i) => i !== from);
  const clamped = Math.max(0, Math.min(rest.length, to));
  return [...rest.slice(0, clamped), order[from]!, ...rest.slice(clamped)];
}

/**
 * Vị trí chèn khi kéo lá `skip` tới tọa độ x: bằng số lá còn lại có tâm nằm bên trái x.
 * `centers` là tọa độ tâm các lá tại thời điểm bắt đầu kéo (theo thứ tự trên tay).
 */
export function insertionIndex(centers: number[], skip: number, x: number): number {
  return centers.reduce((count, c, i) => (i !== skip && c < x ? count + 1 : count), 0);
}

/** Tách nhãn lá bài thành số và chất, để vẽ mặt bài (số trên, chất dưới). */
export const rankLabel = (card: number) => RANKS[rankOf(card)]!;
export const suitSymbol = (card: number) => SUITS[suitOf(card)]!;
