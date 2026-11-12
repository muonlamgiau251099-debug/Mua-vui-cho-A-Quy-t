import { screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { tokenStore } from "../api/guest";
import { renderWithProviders } from "../test-utils";
import { HomePage, safeNext } from "./HomePage";

beforeEach(() => tokenStore.set(null));
afterEach(() => vi.unstubAllGlobals());

function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = routes[url];
      return body === undefined
        ? Promise.reject(new Error("offline"))
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    }),
  );
}

test("khách mới thấy ô nhập tên và trạng thái máy chủ", async () => {
  stubFetch({ "/api/health": { status: "ok", version: "0.1.0", ruleCatalogSize: 130 } });
  renderWithProviders(<HomePage />);
  expect(await screen.findByLabelText("Tên hiển thị của bạn")).toBeInTheDocument();
  expect(await screen.findByText(/130 luật/)).toBeInTheDocument();
});

test("khách đã có token và đang ngồi phòng thấy nút quay lại phòng", async () => {
  tokenStore.set("token-cu");
  stubFetch({
    "/api/health": { status: "ok", version: "0.1.0", ruleCatalogSize: 130 },
    "/api/guests/me": { guestId: "g1", nickname: "Lan", currentRoom: { roomId: "r1", code: "K7QX2M", seatNo: 1 } },
  });
  renderWithProviders(<HomePage />);
  expect(await screen.findByRole("button", { name: "Quay lại phòng K7QX2M" })).toBeInTheDocument();
  expect(screen.getByText("Lan")).toBeInTheDocument();
});

test("báo lỗi khi không kết nối được máy chủ", async () => {
  stubFetch({});
  renderWithProviders(<HomePage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
});

test("safeNext chỉ cho phép đường dẫn nội bộ", () => {
  expect(safeNext("/r/K7QX2M")).toBe("/r/K7QX2M");
  expect(safeNext("//evil.example")).toBe("/lobby");
  expect(safeNext("https://evil.example")).toBe("/lobby");
  expect(safeNext(null)).toBe("/lobby");
});
