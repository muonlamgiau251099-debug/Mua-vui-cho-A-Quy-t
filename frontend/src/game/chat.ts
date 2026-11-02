// Chat nhanh bằng câu có sẵn. Mã câu (id) phải khớp backend/src/app/realtime/chat.py — server từ chối mã lạ.

export const CHAT_PHRASES = [
  { id: "duty", text: "Trách nhiệm lên !" },
  { id: "hurry", text: "Lẹ lên cha" },
  { id: "doomed", text: "Toang rồi" },
  { id: "redeal", text: "Chia lại bài đi !" },
  { id: "top1", text: "Xin cái top 1" },
  { id: "clan", text: "Lại tồng tộc rồi" },
  { id: "spare", text: "Xin đừng nhốt em" },
  { id: "think", text: "Cho mình nghĩ tí" },
] as const;

/** Mỗi người chỉ chat 1 lần / 10 giây (server cũng kiểm tra, đây chỉ để khóa nút cho người dùng thấy). */
export const CHAT_COOLDOWN_MS = 10_000;
/** Bong bóng hiện khoảng 4 giây. */
export const CHAT_SHOW_MS = 4_000;

export const chatText = (id: string): string | null => CHAT_PHRASES.find((p) => p.id === id)?.text ?? null;

/** `key` tăng dần để cùng một câu gửi lại vẫn chạy lại animation. */
export type ChatBubbleData = { phrase: string; key: number };
export type ChatBubbles = Partial<Record<number, ChatBubbleData>>;
