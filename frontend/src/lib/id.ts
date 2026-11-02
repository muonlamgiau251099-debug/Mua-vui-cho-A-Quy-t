/**
 * Mã requestId dạng UUID v4.
 *
 * crypto.randomUUID() chỉ có trong "secure context" (HTTPS hoặc localhost). Khi mở trang qua HTTP bằng IP
 * mạng LAN (vd điện thoại vào http://192.168.1.x:8080) hàm này không tồn tại, nên tự tạo UUID v4 từ
 * crypto.getRandomValues() — hàm này dùng được ở mọi trang.
 */
export function newRequestId(): string {
  const c = globalThis.crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  const bytes = c.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40; // phiên bản 4
  bytes[8] = (bytes[8]! & 0x3f) | 0x80; // biến thể RFC 4122
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
