import { afterEach, vi } from "vitest";
import { tokenStore } from "./guest";

afterEach(() => {
  vi.restoreAllMocks();
  tokenStore.set(null);
});

test("tokenStore lưu và xóa token", () => {
  tokenStore.set("abc");
  expect(tokenStore.get()).toBe("abc");
  tokenStore.set(null);
  expect(tokenStore.get()).toBeNull();
});

test("tokenStore vẫn hoạt động khi localStorage bị chặn", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  tokenStore.set("xyz");
  expect(tokenStore.get()).toBe("xyz");
});
