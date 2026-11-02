import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import type { SeatState } from "../api/guest";
import { RankBanner } from "./RankBanner";
import type { GameEvent, GameResult, GameView, LiveGame } from "./types";

const seats: SeatState[] = ["Lan", "Huy", "Minh", "Đức"].map((nickname, seatNo) => ({
  seatNo,
  occupied: true,
  nickname,
  ready: true,
  connected: true,
  holdUntil: null,
}));

function view(net: number[], overrides: Partial<GameView> = {}): GameView {
  return {
    phase: "PLAYING",
    openingMode: "THREE_CLUBS",
    current: 1,
    turnDeadline: null,
    firstMovePending: false,
    trick: { leader: 1, top: null, topCombo: null, topSeat: null, topIsChop: false, passed: [], chainValue: 0 },
    players: [0, 1, 2, 3].map((seat) => ({ seat, cardCount: 5, playedCount: 3, status: "ACTIVE", rank: null })),
    finishOrder: [],
    endType: null,
    transfers: [],
    net,
    yourSeat: 0,
    yourHand: [],
    ...overrides,
  };
}

const live = (net: number[], events: GameEvent[], sequence: number): LiveGame => ({
  gameId: "g1",
  rules: { version: 1, hash: "h" },
  deckCommitment: "abcdef0123456789",
  sequence,
  state: view(net),
  events,
});

const ended = (endType: string, ranks: Array<[number, string]>, net: number[]): GameResult => ({
  gameId: "g1",
  rules: { version: 1, hash: "h" },
  deckCommitment: "abcdef0123456789",
  deckReveal: null,
  result: view(net, {
    phase: "FINISHED",
    endType,
    players: ranks.map(([rank, status], seat) => ({
      seat,
      cardCount: 0,
      playedCount: 13,
      status: status as GameView["players"][number]["status"],
      rank,
    })),
  }),
});

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("bản chụp đầu tiên (vào bàn / kết nối lại) không phát lại thông báo cũ", () => {
  render(
    <RankBanner
      game={live([0, 0, 0, 0], [{ type: "PLAYER_FINISHED", seat: 2, rank: 1 }], 5)}
      result={null}
      seats={seats}
    />,
  );
  expect(screen.queryByText("CHAMPION!")).not.toBeInTheDocument();
});

test("người hết bài giữa ván: hiện hạng Nhất kèm tên (không có điểm), tự tắt sau 3 giây", () => {
  const { rerender } = render(<RankBanner game={live([0, 0, 0, 0], [], 1)} result={null} seats={seats} />);
  rerender(
    <RankBanner
      game={live([100, 0, -100, 0], [{ type: "PLAYER_FINISHED", seat: 0, rank: 1 }], 2)}
      result={null}
      seats={seats}
    />,
  );
  expect(screen.getByText("CHAMPION!")).toBeInTheDocument();
  expect(screen.getByText("Lan")).toHaveClass("rb-pill");
  expect(screen.queryByText(/điểm/)).not.toBeInTheDocument(); // không hiện điểm cộng/trừ
  act(() => void vi.advanceTimersByTime(3100));
  expect(screen.queryByText("CHAMPION!")).not.toBeInTheDocument();
});

test("bấm Xác nhận để tắt sớm", () => {
  const { rerender } = render(<RankBanner game={live([0, 0, 0, 0], [], 1)} result={null} seats={seats} />);
  rerender(
    <RankBanner
      game={live([0, 0, -50, 0], [{ type: "PLAYER_FINISHED", seat: 1, rank: 2 }], 2)}
      result={null}
      seats={seats}
    />,
  );
  expect(screen.getByText("HẠNG NHÌ!", { exact: false })).toBeInTheDocument();
  expect(screen.getByText("Huy")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Xác nhận" }));
  expect(screen.queryByText("AMAZING!")).not.toBeInTheDocument();
});

test("hết ván: chỉ công bố Bét, không có thông báo hạng Ba", () => {
  const result = ended(
    "NORMAL",
    [
      [1, "FINISHED"],
      [2, "FINISHED"],
      [3, "FINISHED"],
      [4, "FINISHED"],
    ],
    [200, 100, -100, -200],
  );
  const { rerender } = render(<RankBanner game={null} result={null} seats={seats} />);
  rerender(<RankBanner game={null} result={result} seats={seats} />);
  expect(screen.queryByText("GREAT JOB!")).not.toBeInTheDocument();
  expect(screen.queryByText("Minh")).not.toBeInTheDocument(); // người về Ba không có thông báo
  expect(screen.getByText("HƠI ĐEN!")).toBeInTheDocument();
  expect(screen.getByText("Đức")).toBeInTheDocument();
});

test("người cóng cũng nhận thông báo Bét; ván tới trắng thì không hiện thông báo hạng", () => {
  const cong = ended(
    "NORMAL",
    [
      [1, "FINISHED"],
      [2, "CONG"],
      [3, "CONG"],
      [4, "CONG"],
    ],
    [600, -200, -200, -200],
  );
  const { rerender } = render(<RankBanner game={null} result={null} seats={seats} />);
  rerender(<RankBanner game={null} result={cong} seats={seats} />);
  expect(screen.getByText("HƠI ĐEN!")).toBeInTheDocument();

  const white = { ...cong, gameId: "g2", result: { ...cong.result, endType: "INSTANT_WIN" } };
  const other = render(<RankBanner game={null} result={null} seats={seats} />);
  other.rerender(<RankBanner game={null} result={white} seats={seats} />);
  expect(other.container.querySelector(".rank-banner")).toBeNull();
});
