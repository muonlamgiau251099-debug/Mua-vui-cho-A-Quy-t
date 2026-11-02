// Chat trong phòng: câu có sẵn + chữ tự do ngắn.
// Mã câu (id) phải khớp backend/src/app/realtime/chat.py — server từ chối mã lạ.

export const CHAT_PHRASES = [
  { id: "duty", text: "Trách nhiệm lên !" },
  { id: "hurry", text: "Lẹ lên cha" },
  { id: "doomed", text: "Toang rồi" },
  { id: "redeal", text: "Chia lại bài đi !" },
  { id: "top1", text: "Xin cái top 1" },
  { id: "clan", text: "Lại tồng tộc rồi" },
  { id: "spare", text: "Xin đừng nhốt em" },
  { id: "think", text: "Cho mình nghĩ tí" },
  { id: "spade3", text: "Xin cây 3 bích" },
  { id: "mistake", text: "Ơ a có đánh nhầm không?" },
  { id: "undo", text: "Cho e đánh lại được không" },
] as const;

/** Mỗi người chỉ chat 1 lần / 10 giây (server cũng kiểm tra, đây chỉ để khóa nút cho người dùng thấy). */
export const CHAT_COOLDOWN_MS = 10_000;
/** Bong bóng hiện khoảng 4 giây. */
export const CHAT_SHOW_MS = 4_000;
/** Số ký tự tối đa của chữ tự do (khớp CHAT_MAX_LENGTH ở backend). */
export const CHAT_MAX_LENGTH = 60;

export const chatText = (id: string): string | null => CHAT_PHRASES.find((p) => p.id === id)?.text ?? null;

/**
 * Làm sạch chữ tự do giống server: ký tự điều khiển / định dạng → khoảng trắng (trừ ZWJ của emoji ghép),
 * gộp khoảng trắng, cắt bớt cho vừa giới hạn. Server vẫn kiểm tra lại; đây để hiển thị đúng và khóa nút Gửi.
 */
export function cleanChatText(raw: string): string {
  const spaced = raw.replace(/[\p{C}]/gu, (ch) => (ch === "‍" ? ch : " "));
  return Array.from(spaced.split(/\s+/).filter(Boolean).join(" "))
    .slice(0, CHAT_MAX_LENGTH)
    .join("");
}

/** Nội dung gửi lên server: đúng một trong hai. */
export type ChatOutgoing = { phrase: string } | { text: string };

/** `key` tăng dần để cùng một nội dung gửi lại vẫn chạy lại animation. `text` đã là chữ hiển thị. */
export type ChatBubbleData = { text: string; key: number };
export type ChatBubbles = Partial<Record<number, ChatBubbleData>>;
