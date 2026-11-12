import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, vi } from "vitest";
import type { SessionDetail } from "../api/guest";
import { SessionScoreboard } from "../room/SessionScoreboard";
import { renderWithProviders } from "../test-utils";
import { HistoryPage } from "./HistoryPage";

afterEach(() => vi.unstubAllGlobals());

const detail: SessionDetail = {
  sessionId: "s1",
  roomCode: "K7QX2M",
  sessionNo: 2,
  status: "ACTIVE",
  endReason: null,
  startedAt: "2026-10-30T10:00:00Z",
  endedAt: null,
  players: ["Lan", "Huy", "Minh", "Đức"].map((nickname, seat) => ({ seat, nickname })),
  standings: [
    { seat: 1, nickname: "Huy", total: 300, gamesCounted: 2, place: 1 },
    { seat: 0, nickname: "Lan", total: 100, gamesCounted: 2, place: 2 },
    { seat: 2, nickname: "Minh", total: -100, gamesCounted: 2, place: 3 },
    { seat: 3, nickname: "Đức", total: -300, gamesCounted: 2, place: 4 },
  ],
  games: [
    {
      gameId: "g1",
      gameNo: 1,
      status: "FINISHED",
      endType: "NORMAL",
      cancelReason: null,
      ruleVersion: 1,
      startedAt: "",
      endedAt: "",
      ranks: [2, 1, 3, 4],
      net: [100, 200, -100, -200],
      cumulative: [100, 200, -100, -200],
      transfers: [{ from: 3, to: 1, amount: 200, reason: "RANK" }],
    },
    {
      gameId: "g2",
      gameNo: 2,
      status: "CANCELLED",
      endType: "CANCELLED",
      cancelReason: "ADMIN",
      ruleVersion: 1,
      startedAt: "",
      endedAt: "",
      ranks: null,
      net: null,
      cumulative: null,
      transfers: [],
    },
  ],
};

test("trang lịch sử: tổng kết, điểm từng ván, ván bị hủy và chi tiết khoản điểm", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(detail) }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/history/s1"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/history/:sessionId" element={<HistoryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Phiên 2 · phòng K7QX2M")).toBeInTheDocument();
  expect(screen.getByText("+300")).toBeInTheDocument();
  expect(screen.getByText("Bị hủy (Admin hủy) — không tính điểm")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Chi tiết" }));
  expect(screen.getByText(/Đức trả Huy/)).toHaveTextContent("Đức trả Huy 200 — Điểm hạng");
});

test("bảng điểm phiên xếp theo điểm và đánh dấu người chơi hiện tại", () => {
  renderWithProviders(
    <SessionScoreboard
      yourSeat={0}
      session={{
        sessionId: "s1",
        sessionNo: 1,
        gamesPlayed: 3,
        scores: [
          { seat: 0, nickname: "Lan", total: -100 },
          { seat: 1, nickname: "Huy", total: 400 },
          { seat: 2, nickname: "Minh", total: 0 },
          { seat: 3, nickname: "Đức", total: -300 },
        ],
      }}
    />,
  );
  const items = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(items).toEqual(["Huy+400", "Minh0", "Lan (bạn)-100", "Đức-300"]);
  expect(screen.getByRole("link", { name: "Lịch sử" })).toHaveAttribute("href", "/history/s1");
});

test("chưa có phiên thì báo điểm bắt đầu từ 0", () => {
  renderWithProviders(<SessionScoreboard session={null} yourSeat={0} />);
  expect(screen.getByText(/bắt đầu từ 0/)).toBeInTheDocument();
});
