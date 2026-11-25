import { afterEach, vi } from "vitest";
import { newRequestId } from "./id";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

afterEach(() => vi.unstubAllGlobals());

test("dùng crypto.randomUUID khi có", () => {
  expect(newRequestId()).toMatch(UUID_V4);
});

test("vẫn tạo UUID v4 hợp lệ khi trang mở qua HTTP bằng IP LAN (không có randomUUID)", () => {
  const getRandomValues = (arr: Uint8Array) => {
    arr.fill(0xff);
    return arr;
  };
  vi.stubGlobal("crypto", { getRandomValues });
  const id = newRequestId();
  expect(id).toMatch(UUID_V4);
  expect(id).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
});
