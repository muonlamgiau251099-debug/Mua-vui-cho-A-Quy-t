import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { tokenStore } from "../api/guest";
import { renderWithProviders } from "../test-utils";
import { LobbyPage } from "./LobbyPage";

beforeEach(() => tokenStore.set("token-cu"));
afterEach(() => vi.unstubAllGlobals());

type Call = { url: string; method: string; body: unknown };

function stubApi(profile: { nickname: string; currentRoom: unknown }, renameStatus = 200) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const json = (status: number, body: unknown) =>
        Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
      if (url === "/api/guests/me" && method === "PATCH") {
        if (renameStatus !== 200) return json(renameStatus, { code: "NICKNAME_INVALID", title: "Tên phải dài 2–20 ký tự" });
        profile = { ...profile, nickname: String(calls.at(-1)!.body && (calls.at(-1)!.body as { nickname: string }).nickname) };
      }
      if (url === "/api/guests/me") return json(200, { guestId: "g1", ...profile });
      if (url.startsWith("/api/guests/me/sessions")) return json(200, { items: [] });
      return json(404, {});
    }),
  );
  return calls;
}

test("đổi tên ở sảnh: bấm Đổi tên, nhập tên mới, Lưu → gửi PATCH và hiện tên mới", async () => {
  const calls = stubApi({ nickname: "Lan", currentRoom: null });
  renderWithProviders(<LobbyPage />, "/lobby");
  expect(await screen.findByText("Lan")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Đổi tên/ }));
  const input = screen.getByLabelText("Tên hiển thị mới");
  expect(screen.getByRole("button", { name: "Lưu" })).toBeDisabled(); // chưa đổi gì
  fireEvent.change(input, { target: { value: "Minh Anh" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

  expect(await screen.findByText("Minh Anh")).toBeInTheDocument();
  expect(screen.queryByLabelText("Tên hiển thị mới")).not.toBeInTheDocument();
  const patch = calls.find((c) => c.method === "PATCH");
  expect(patch).toMatchObject({ url: "/api/guests/me", body: { nickname: "Minh Anh" } });
});

test("đổi tên: tên không hợp lệ thì hiện lỗi và giữ ô nhập; Hủy thì đóng", async () => {
  stubApi({ nickname: "Lan", currentRoom: null }, 422);
  renderWithProviders(<LobbyPage />, "/lobby");
  await screen.findByText("Lan");
  fireEvent.click(screen.getByRole("button", { name: /Đổi tên/ }));
  fireEvent.change(screen.getByLabelText("Tên hiển thị mới"), { target: { value: "!!" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Tên phải dài 2–20 ký tự");
  expect(screen.getByLabelText("Tên hiển thị mới")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
  await waitFor(() => expect(screen.queryByLabelText("Tên hiển thị mới")).not.toBeInTheDocument());
});

test("đang ngồi trong phòng thì không cho đổi tên", async () => {
  stubApi({ nickname: "Lan", currentRoom: { roomId: "r1", code: "K7QX2M", seatNo: 0 } });
  renderWithProviders(<LobbyPage />, "/lobby");
  await screen.findByText("Lan");
  expect(screen.queryByRole("button", { name: /Đổi tên/ })).not.toBeInTheDocument();
});
