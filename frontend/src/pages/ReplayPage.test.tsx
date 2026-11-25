import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, vi } from "vitest";
import type { GameReplay } from "../api/guest";
import type { GameView } from "../game/types";
import { ReplayPage } from "./ReplayPage";

afterEach(() => vi.unstubAllGlobals());

function view(hands: number[][], extra: Partial<GameView> = {}): GameView & { hands: number[][] } {
  return {
    phase: "PLAYING",
    openingMode: "THREE_CLUBS",
    current: 0,
    turnDeadline: null,
    firstMovePending: false,
    trick: { leader: 0, top: null, topCombo: null, topSeat: null, topIsChop: false, passed: [], chainValue: 0 },
    players: [0, 1, 2, 3].map((seat) => ({ seat, cardCount: hands[seat]!.length, playedCount: 0, status: "ACTIVE", rank: null })),
    finishOrder: [],
    endType: null,
    transfers: [],
    net: [0, 0, 0, 0],
    hands,
    ...extra,
  };
}

const replay: GameReplay = {
  gameId: "g1",
  gameNo: 3,
  sessionId: "s1",
  roomCode: "K7QX2M",
  status: "FINISHED",
  endType: "NORMAL",
  ruleVersion: 1,
  deckCommitment: "abcdef0123456789",
  deckSalt: "salt",
  verified: true,
  players: ["Lan", "Huy", "Minh", "Đức"].map((nickname, seat) => ({ seat, nickname })),
  initial: view([[1, 30], [4], [8], [12]]),
  steps: [
    {
      seq: 1,
      kind: "PLAY",
      seat: 0,
      events: [{ type: "PLAYED", seat: 0, cards: [1], chop: false, interrupt: false, auto: false }],
      view: view([[30], [4], [8], [12]], {
        current: 1,
        trick: { leader: 0, top: [1], topCombo: "SINGLE", topSeat: 0, topIsChop: false, passed: [], chainValue: 0 },
      }),
    },
  ],
};

test("xem lại: bắt đầu từ lúc chia bài, bấm Tới để xem nước đi kế tiếp", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(replay) }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/replay/g1"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/replay/:gameId" element={<ReplayPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Xem lại ván #3 · phòng K7QX2M")).toBeInTheDocument();
  expect(screen.getByText("Vừa chia bài.")).toBeInTheDocument();
  expect(screen.getByText(/Log khớp/)).toBeInTheDocument();
  expect(screen.getAllByText("3♣")).toHaveLength(1); // trên tay Lan
  fireEvent.click(screen.getByRole("button", { name: "Tới ▶" }));
  expect(screen.getByText("Lan đánh 3♣")).toBeInTheDocument();
  expect(screen.getByText("Rác của Lan")).toBeInTheDocument();
  expect(screen.getByText("Bước 1/1")).toBeInTheDocument();
});
