import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { SeatState } from "../api/guest";
import { newerGame } from "../realtime/useRoomSocket";
import { cardLabel, cardsLabel, sortHand } from "./cards";
import { GameResultPanel } from "./GameResultPanel";
import { describeEvent, GameTable, specialPlayLabel } from "./GameTable";
import type { GameResult, GameView, LiveGame } from "./types";

const seats: SeatState[] = ["Lan", "Huy", "Minh", "Đức"].map((nickname, seatNo) => ({
  seatNo,
  occupied: true,
  nickname,
  ready: false,
  connected: seatNo !== 2,
  holdUntil: null,
}));

function view(overrides: Partial<GameView> = {}): GameView {
  return {
    phase: "PLAYING",
    openingMode: "THREE_CLUBS",
    current: 0,
    turnDeadline: Date.now() / 1000 + 20,
    firstMovePending: true,
    trick: { leader: 0, top: null, topCombo: null, topSeat: null, topIsChop: false, passed: [], chainValue: 0 },
    players: [0, 1, 2, 3].map((seat) => ({ seat, cardCount: 13, playedCount: 0, status: "ACTIVE", rank: null })),
    finishOrder: [],
    endType: null,
    transfers: [],
    net: [0, 0, 0, 0],
    yourSeat: 0,
    yourHand: [1, 4, 30, 51],
    ...overrides,
  };
}

const live = (state: GameView, sequence = 0): LiveGame => ({
  gameId: "g1",
  rules: { version: 2, hash: "h" },
  deckCommitment: "abcdef0123456789",
  sequence,
  state,
  events: [],
});

test("nhãn lá bài và sắp xếp theo số / chất", () => {
  expect([1, 30, 51].map(cardLabel)).toEqual(["3♣", "10♦", "2♥"]);
  expect(cardsLabel([51, 1])).toBe("3♣ 2♥");
  expect(sortHand([51, 1, 4], "suit")).toEqual([4, 1, 51]); // ♠ trước ♣ trước ♥
});

test("người mở vòng thấy bài của mình, không bỏ lượt được, chọn lá rồi đánh", () => {
  const onPlay = vi.fn();
  render(<GameTable game={live(view())} seats={seats} canAct error={null} onPlay={onPlay} onPass={vi.fn()} />);
  expect(screen.getByText("LƯỢT CỦA BẠN")).toBeInTheDocument();
  expect(screen.getByText("Bạn mở vòng (phải có 3♣)")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Bỏ lượt" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "3♣" }));
  fireEvent.click(screen.getByRole("button", { name: "Đánh (1)" }));
  expect(onPlay).toHaveBeenCalledWith([1]);
});

test("hiển thị số lá đối thủ, người mất kết nối và bài trên bàn", () => {
  const state = view({
    current: 1,
    firstMovePending: false,
    trick: { leader: 3, top: [44, 47], topCombo: "PAIR", topSeat: 3, topIsChop: false, passed: [2], chainValue: 0 },
    players: [0, 1, 2, 3].map((seat) => ({
      seat,
      cardCount: seat === 3 ? 1 : 10 + seat,
      playedCount: 3,
      status: "ACTIVE",
      rank: null,
    })),
  });
  render(<GameTable game={live(state)} seats={seats} canAct error={null} onPlay={vi.fn()} onPass={vi.fn()} />);
  expect(screen.queryByText(/🂠/)).not.toBeInTheDocument(); // không hiện số lá còn lại
  expect(screen.getAllByText("⚠ Còn 1 lá!")).toHaveLength(1); // chỉ cảnh báo người còn đúng 1 lá
  expect(screen.getByText(/Đã bỏ lượt · ⟳ mất kết nối/)).toBeInTheDocument();
  expect(screen.getByText("Đôi của Đức")).toBeInTheDocument();
  expect(screen.getByText("Lượt của Huy", { exact: false })).toBeInTheDocument();
});

test("tên hiển thị cho bài đặc biệt: heo, tứ quý, đôi thông", () => {
  expect(specialPlayLabel("FOUR_KIND", [0, 1, 2, 3])).toBe("Tứ quý");
  expect(specialPlayLabel("PAIR_SEQ", [0, 1, 4, 5, 8, 9])).toBe("3 đôi thông");
  expect(specialPlayLabel("PAIR_SEQ", [0, 1, 4, 5, 8, 9, 12, 13])).toBe("4 đôi thông");
  expect(specialPlayLabel("SINGLE", [51])).toBe("2 cơ"); // 2♥
  expect(specialPlayLabel("SINGLE", [48])).toBe("2 bích"); // 2♠
  expect(specialPlayLabel("PAIR", [48, 51])).toBe("Đôi 2");
  expect(specialPlayLabel("TRIPLE", [48, 49, 51])).toBe("3 con 2");
  expect(specialPlayLabel("PAIR", [44, 47])).toBeNull(); // đôi A: không đặc biệt
  expect(specialPlayLabel("SINGLE", [4])).toBeNull();
  expect(specialPlayLabel(null, [])).toBeNull();
});

test("chọn nhiều lá bằng cách kéo ngang qua bài, rồi đánh cùng lúc", () => {
  const onPlay = vi.fn();
  render(<GameTable game={live(view())} seats={seats} canAct error={null} onPlay={onPlay} onPass={vi.fn()} />);
  // Bài trên tay đã xếp theo số: 3♣, 4♠, 10♦, 2♥ → kéo từ 3♣ tới 10♦ chọn 3 lá.
  const cards = [1, 4, 30].map(
    (c) => screen.getAllByRole("button").find((b) => b.dataset.cardIdx !== undefined && b.textContent === cardLabel(c))!,
  );
  const at = (el: HTMLElement) => {
    document.elementFromPoint = () => el;
  };
  at(cards[0]!);
  fireEvent.pointerDown(cards[0]!, { pointerType: "mouse", button: 0, buttons: 1 });
  at(cards[2]!);
  fireEvent.pointerMove(cards[2]!, { pointerType: "mouse", buttons: 1 });
  fireEvent.pointerUp(cards[2]!, { pointerType: "mouse" });
  expect(screen.getByRole("button", { name: "Đánh (3)" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Đánh (3)" }));
  expect(onPlay).toHaveBeenCalledWith(expect.arrayContaining([1, 4, 30]));
});

test("hiện chữ 'nè !!!' khi đối thủ đánh tứ quý, không hiện với bài có sẵn lúc vào bàn", () => {
  const withTop = (top: number[] | null, combo: string | null) =>
    live(
      view({
        current: 0,
        firstMovePending: false,
        trick: { leader: 1, top, topCombo: combo, topSeat: top ? 1 : null, topIsChop: false, passed: [], chainValue: 0 },
      }),
    );
  const props = { seats, canAct: true, error: null, onPlay: vi.fn(), onPass: vi.fn() };
  const { rerender } = render(<GameTable game={withTop([0, 1, 2, 3], "FOUR_KIND")} {...props} />);
  expect(screen.queryByText(/Tứ quý nè/)).not.toBeInTheDocument(); // đã có sẵn trên bàn
  rerender(<GameTable game={withTop([8, 9, 10, 11], "FOUR_KIND")} {...props} />);
  expect(screen.getByText(/Huy: Tứ quý nè !!!/)).toBeInTheDocument();
});

test("mô tả diễn biến bằng tiếng Việt", () => {
  const name = (s: number) => ["Lan", "Huy", "Minh", "Đức"][s]!;
  expect(describeEvent({ type: "PLAYED", seat: 1, cards: [48, 51], chop: false, interrupt: false, auto: false }, name)).toBe(
    "Huy đánh 2♠ 2♥",
  );
  expect(describeEvent({ type: "PASSED", seat: 2, auto: true }, name)).toBe("Minh bỏ lượt (hết giờ)");
  expect(describeEvent({ type: "PLAYER_FINISHED", seat: 0, rank: 1 }, name)).toBe("Lan hết bài — về nhất");
  expect(describeEvent({ type: "TURN_STARTED", seat: 0 }, name)).toBeNull();
});

test("bảng kết quả hiển thị hạng, điểm và chi tiết từng khoản", () => {
  const result: GameResult = {
    gameId: "g1",
    rules: { version: 2, hash: "h" },
    deckCommitment: "c",
    deckReveal: { deck: [], salt: "1234567890" },
    result: view({
      phase: "FINISHED",
      endType: "NORMAL",
      players: [1, 3, 2, 4].map((rank, seat) => ({ seat, cardCount: 0, playedCount: 0, status: seat === 3 ? "CONG" : "FINISHED", rank })),
      transfers: [
        { from: 3, to: 0, amount: 200, reason: "CONG", detail: {} },
        { from: 1, to: 2, amount: 100, reason: "RANK", detail: {} },
      ],
      net: [200, -100, 100, -200],
      hands: [[], [5], [], [48]],
    }),
  };
  const onReady = vi.fn();
  render(<GameResultPanel result={result} seats={seats} yourSeat={0} onReady={onReady} onClose={vi.fn()} />);
  expect(screen.getByText("Bét (cóng)")).toBeInTheDocument();
  expect(screen.getByText("+200")).toBeInTheDocument();
  expect(screen.getByText(/Đức trả Bạn/)).toHaveTextContent("Đức trả Bạn 200 — Cóng");
  expect(screen.getByText(/Tổng điểm 4 người: 0/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sẵn sàng ván tiếp" }));
  expect(onReady).toHaveBeenCalled();
});

test("bỏ qua trạng thái ván đến trễ, nhận ván mới", () => {
  const a = live(view(), 5);
  expect(newerGame(a, live(view(), 4)).sequence).toBe(5);
  expect(newerGame(a, { ...live(view(), 0), gameId: "g2" }).gameId).toBe("g2");
});

test("người cóng luôn hiện là bét dù số hạng nội bộ là 2 hay 3 (D7)", () => {
  const result: GameResult = {
    gameId: "g1",
    rules: { version: 1, hash: "h" },
    deckCommitment: "c",
    deckReveal: null,
    result: view({
      phase: "FINISHED",
      endType: "NORMAL",
      players: [1, 2, 3, 4].map((rank, seat) => ({ seat, cardCount: 0, playedCount: 0, status: seat === 0 ? "FINISHED" : "CONG", rank })),
      net: [600, -200, -200, -200],
    }),
  };
  render(<GameResultPanel result={result} seats={seats} yourSeat={0} onReady={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getAllByText("Bét (cóng)")).toHaveLength(3);
  expect(screen.queryByText("Nhì")).not.toBeInTheDocument();
});

test("3 con cùng số là 'Hút thuốc', riêng 3 con 2 giữ nguyên", () => {
  expect(specialPlayLabel("TRIPLE", [0, 1, 2])).toBe("Hút thuốc"); // 3 con ba
  expect(specialPlayLabel("TRIPLE", [12, 13, 14])).toBe("Hút thuốc"); // 3 con 5
  expect(specialPlayLabel("TRIPLE", [48, 49, 50])).toBe("3 con 2");
});

test("chat: chọn câu có sẵn thì gửi mã câu và khóa nút trong 10 giây", () => {
  vi.useFakeTimers();
  const onChat = vi.fn(() => true);
  render(<GameTable game={live(view())} seats={seats} canAct error={null} onPlay={vi.fn()} onPass={vi.fn()} onChat={onChat} />);
  fireEvent.click(screen.getByRole("button", { name: "💬 Chat" }));
  expect(screen.getAllByRole("menuitem")).toHaveLength(8);
  fireEvent.click(screen.getByRole("menuitem", { name: "Lẹ lên cha" }));
  expect(onChat).toHaveBeenCalledWith("hurry");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "💬 10s" })).toBeDisabled();
  act(() => void vi.advanceTimersByTime(10_500));
  expect(screen.getByRole("button", { name: "💬 Chat" })).toBeEnabled();
  vi.useRealTimers();
});

test("chat: gửi không được (mất kết nối) thì không bị khóa nút", () => {
  const onChat = vi.fn(() => false);
  render(<GameTable game={live(view())} seats={seats} canAct error={null} onPlay={vi.fn()} onPass={vi.fn()} onChat={onChat} />);
  fireEvent.click(screen.getByRole("button", { name: "💬 Chat" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Toang rồi" }));
  expect(screen.getByRole("button", { name: "💬 Chat" })).toBeEnabled();
});

test("chat: bong bóng hiện ở người gửi (đối thủ và chính mình)", () => {
  render(
    <GameTable
      game={live(view())}
      seats={seats}
      canAct
      error={null}
      onPlay={vi.fn()}
      onPass={vi.fn()}
      chats={{ 1: { phrase: "think", key: 1 }, 0: { phrase: "doomed", key: 2 } }}
    />,
  );
  expect(screen.getByText("Cho mình nghĩ tí")).toHaveClass("chat-bubble");
  expect(screen.getByText("Toang rồi")).toHaveClass("chat-bubble");
});

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

test("chat: PC để nút chat sát avatar của mình, mobile chuyển xuống hàng nút hành động", () => {
  const props = { seats, canAct: true, error: null, onPlay: vi.fn(), onPass: vi.fn(), onChat: vi.fn() };

  stubMatchMedia(false);
  const desktop = render(<GameTable game={live(view())} {...props} />);
  expect(desktop.container.querySelector(".my-seat .chat-wrap")).not.toBeNull();
  expect(desktop.container.querySelector(".game-actions .chat-wrap")).toBeNull();
  desktop.unmount();

  stubMatchMedia(true);
  const mobile = render(<GameTable game={live(view())} {...props} />);
  expect(mobile.container.querySelector(".game-actions .chat-wrap")).not.toBeNull();
  expect(mobile.container.querySelector(".my-seat .chat-wrap")).toBeNull();
  expect(screen.getAllByRole("button", { name: "💬 Chat" })).toHaveLength(1);
  vi.unstubAllGlobals();
});

test("chat: bong bóng đặt đúng hướng đuôi theo vị trí người gửi", () => {
  // yourSeat = 0 → ghế 1 bên trái, ghế 2 ở trên, ghế 3 bên phải
  const { container } = render(
    <GameTable
      game={live(view())}
      seats={seats}
      canAct
      error={null}
      onPlay={vi.fn()}
      onPass={vi.fn()}
      chats={{
        0: { phrase: "duty", key: 1 },
        1: { phrase: "hurry", key: 2 },
        2: { phrase: "doomed", key: 3 },
        3: { phrase: "think", key: 4 },
      }}
    />,
  );
  const tail = (text: string) => screen.getByText(text).className;
  expect(tail("Trách nhiệm lên !")).toContain("tail-side"); // mình: bên phải avatar ở giữa phía dưới, đuôi chỉ sang trái
  expect(container.querySelector(".my-avatar .chat-bubble")).not.toBeNull();
  expect(tail("Lẹ lên cha")).toContain("tail-left"); // ghế bên trái
  expect(tail("Toang rồi")).toContain("tail-side"); // ghế ở trên: bên phải avatar, đuôi chỉ sang trái
  expect(tail("Cho mình nghĩ tí")).toContain("tail-right"); // ghế bên phải
  expect(container.querySelector(".opponent.pos-top .chat-bubble")).not.toBeNull();
});
