import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import type { SeatState } from "../api/guest";
import { newerGame } from "../realtime/useRoomSocket";
import { cardLabel, cardsLabel, insertionIndex, moveCard } from "./cards";
import { CHAT_MAX_LENGTH, cleanChatText } from "./chat";
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

test("nhãn lá bài", () => {
  expect([1, 30, 51].map(cardLabel)).toEqual(["3♣", "10♦", "2♥"]);
  expect(cardsLabel([51, 1])).toBe("3♣ 2♥");
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

const chatProps = { seats, canAct: true, error: null, onPlay: vi.fn(), onPass: vi.fn() };
const openChat = () => fireEvent.click(screen.getByRole("button", { name: "💬 Chat" }));
const chatSheet = () => screen.getByRole("dialog", { name: "Chat" });

test("chat: bấm nút Chat mở card kéo lên với ô nhập, nút gửi (icon) và 11 câu có sẵn", () => {
  render(<GameTable game={live(view())} {...chatProps} onChat={vi.fn()} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  openChat();
  const sheet = chatSheet();
  expect(within(sheet).getByRole("textbox", { name: "Tin nhắn" })).toHaveAttribute("maxlength", "60");
  expect(within(sheet).getByRole("button", { name: "Gửi" })).toBeDisabled(); // chưa nhập gì
  const presets = within(within(sheet).getByRole("group", { name: "Câu chat có sẵn" })).getAllByRole("button");
  expect(presets).toHaveLength(11);
  for (const text of ["Xin cây 3 bích", "Ơ a có đánh nhầm không?", "Cho e đánh lại được không"]) {
    expect(within(sheet).getByRole("button", { name: text })).toBeInTheDocument();
  }
});

test("chat: chọn câu có sẵn thì gửi mã câu và đóng card; nút chat vẫn bấm được trong lúc chờ 4 giây", () => {
  vi.useFakeTimers();
  const onChat = vi.fn(() => true);
  render(<GameTable game={live(view())} {...chatProps} onChat={onChat} />);
  openChat();
  fireEvent.click(within(chatSheet()).getByRole("button", { name: "Lẹ lên cha" }));
  expect(onChat).toHaveBeenCalledWith({ phrase: "hurry" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  // Đang chờ: nút chat hiện số giây còn lại nhưng KHÔNG bị khóa, vẫn mở được card.
  expect(screen.getByRole("button", { name: "💬 4s" })).toBeEnabled();
  vi.useRealTimers();
});

test("chat: trong lúc chờ vẫn nhập sẵn được; nút gửi và câu có sẵn khóa tới đủ 4 giây rồi mới gửi", () => {
  vi.useFakeTimers();
  const onChat = vi.fn(() => true);
  render(<GameTable game={live(view())} {...chatProps} onChat={onChat} />);
  openChat();
  fireEvent.click(within(chatSheet()).getByRole("button", { name: "Toang rồi" })); // gửi lần 1
  expect(onChat).toHaveBeenCalledTimes(1);

  act(() => void vi.advanceTimersByTime(1_000)); // còn khoảng 3 giây
  fireEvent.click(screen.getByRole("button", { name: /💬/ })); // mở lại card ngay trong lúc chờ
  const sheet = chatSheet();
  const input = within(sheet).getByRole("textbox", { name: "Tin nhắn" });
  expect(input).toBeEnabled();
  fireEvent.change(input, { target: { value: "Cho e đánh lại" } }); // nhập sẵn
  expect(input).toHaveValue("Cho e đánh lại");
  expect(within(sheet).getByRole("button", { name: "Gửi" })).toBeDisabled();
  expect(within(sheet).getByRole("button", { name: "Lẹ lên cha" })).toBeDisabled(); // câu có sẵn cũng khóa
  expect(within(sheet).getByRole("status")).toHaveTextContent(/Chờ \d giây/);
  fireEvent.submit(input.closest("form")!); // Enter trong lúc chờ: không gửi, giữ nguyên chữ
  expect(onChat).toHaveBeenCalledTimes(1);
  expect(input).toHaveValue("Cho e đánh lại");

  act(() => void vi.advanceTimersByTime(3_200)); // đủ 4 giây kể từ lần gửi trước
  expect(within(chatSheet()).getByRole("button", { name: "Gửi" })).toBeEnabled();
  expect(within(chatSheet()).getByRole("button", { name: "Lẹ lên cha" })).toBeEnabled();
  fireEvent.click(within(chatSheet()).getByRole("button", { name: "Gửi" }));
  expect(onChat).toHaveBeenCalledTimes(2);
  expect(onChat).toHaveBeenLastCalledWith({ text: "Cho e đánh lại" });
  vi.useRealTimers();
});


test("chat: nhập chữ tự do rồi bấm Gửi (hoặc Enter) → gửi chữ đã làm sạch", () => {
  const onChat = vi.fn(() => true);
  render(<GameTable game={live(view())} {...chatProps} onChat={onChat} />);
  openChat();
  const input = within(chatSheet()).getByRole("textbox", { name: "Tin nhắn" });
  fireEvent.change(input, { target: { value: "   " } });
  expect(within(chatSheet()).getByRole("button", { name: "Gửi" })).toBeDisabled(); // chỉ có khoảng trắng
  fireEvent.change(input, { target: { value: "  Cho e   đánh\tlại  " } });
  expect(within(chatSheet()).getByRole("button", { name: "Gửi" })).toBeEnabled();
  fireEvent.submit(input.closest("form")!); // Enter trên bàn phím ảo
  expect(onChat).toHaveBeenCalledWith({ text: "Cho e đánh lại" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("chat: bấm ra ngoài card hoặc Esc thì đóng, không gửi gì", () => {
  const onChat = vi.fn();
  render(<GameTable game={live(view())} {...chatProps} onChat={onChat} />);
  openChat();
  fireEvent.click(screen.getByRole("presentation")); // vùng mờ phía sau card
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  openChat();
  fireEvent.click(within(chatSheet()).getByRole("textbox", { name: "Tin nhắn" })); // bấm trong card không đóng
  expect(chatSheet()).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(onChat).not.toHaveBeenCalled();
});

test("chat: gửi không được (mất kết nối) thì không bị khóa nút và card vẫn mở để thử lại", () => {
  const onChat = vi.fn(() => false);
  render(<GameTable game={live(view())} {...chatProps} onChat={onChat} />);
  openChat();
  fireEvent.click(within(chatSheet()).getByRole("button", { name: "Toang rồi" }));
  expect(onChat).toHaveBeenCalledWith({ phrase: "doomed" });
  expect(chatSheet()).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.getByRole("button", { name: "💬 Chat" })).toBeEnabled();
});

test("chat: cleanChatText làm sạch và giới hạn độ dài", () => {
  expect(cleanChatText("  a \n\t b   c ")).toBe("a b c");
  expect(cleanChatText("x\u202Ey\u0007z")).toBe("x y z"); // đảo chiều chữ, ký tự chuông → khoảng trắng
  expect(cleanChatText("\u202E\u0007")).toBe("");
  expect(cleanChatText("a".repeat(100))).toHaveLength(CHAT_MAX_LENGTH);
  expect(cleanChatText("👨‍👩‍👧")).toBe("👨‍👩‍👧"); // emoji ghép không bị vỡ
});

test("chat: bong bóng hiện ở người gửi (đối thủ và chính mình), cả câu có sẵn lẫn chữ tự do", () => {
  render(
    <GameTable
      game={live(view())}
      {...chatProps}
      chats={{ 1: { text: "Cho mình nghĩ tí", key: 1 }, 0: { text: "Ơ a có đánh nhầm không?", key: 2 } }}
    />,
  );
  expect(screen.getByText("Cho mình nghĩ tí")).toHaveClass("chat-bubble");
  expect(screen.getByText("Ơ a có đánh nhầm không?")).toHaveClass("chat-bubble");
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
        0: { text: "Trách nhiệm lên !", key: 1 },
        1: { text: "Lẹ lên cha", key: 2 },
        2: { text: "Toang rồi", key: 3 },
        3: { text: "Cho mình nghĩ tí", key: 4 },
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

afterEach(() => vi.unstubAllGlobals());

// Bài trên tay (đã xếp theo số): 3♣, 4♠, 10♦, 2♥. jsdom không có layout nên gán tọa độ cho từng lá:
// lá thứ i rộng 56px, đè lên nhau mỗi lá cách 20px.
function stubCardRects(container: HTMLElement) {
  container.querySelectorAll<HTMLElement>("[data-card-idx]").forEach((el) => {
    const i = Number(el.dataset.cardIdx);
    el.getBoundingClientRect = () =>
      ({ left: i * 20, right: i * 20 + 56, top: 100, bottom: 180, width: 56, height: 80, x: i * 20, y: 100 }) as DOMRect;
  });
}
const handLabels = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLElement>("[data-card-idx]")).map((el) => el.textContent);

const baseProps = { seats, canAct: true, error: null, onPlay: vi.fn(), onPass: vi.fn() };

test("moveCard và insertionIndex", () => {
  expect(moveCard([1, 4, 30, 51], 0, 3)).toEqual([4, 30, 51, 1]);
  expect(moveCard([1, 4, 30, 51], 3, 0)).toEqual([51, 1, 4, 30]);
  expect(moveCard([1, 4, 30, 51], 1, 1)).toEqual([1, 4, 30, 51]);
  expect(moveCard([1, 4, 30, 51], 9, 0)).toEqual([1, 4, 30, 51]); // vị trí không có thật: giữ nguyên
  expect(insertionIndex([28, 48, 68, 88], 0, 200)).toBe(3); // thả sau cùng
  expect(insertionIndex([28, 48, 68, 88], 3, 10)).toBe(0); // thả đầu tiên
  expect(insertionIndex([28, 48, 68, 88], 1, 60)).toBe(1); // thả giữa lá 0 và 2
});

test("kéo thả một lá sang vị trí khác để tự xếp bài; không làm lá đó bị chọn", () => {
  const { container } = render(<GameTable game={live(view())} {...baseProps} />);
  stubCardRects(container);
  expect(handLabels(container)).toEqual(["3♣", "4♠", "10♦", "2♥"]);
  const first = screen.getByRole("button", { name: "3♣" });
  fireEvent.pointerDown(first, { pointerType: "mouse", button: 0, buttons: 1, clientX: 28, clientY: 140 });
  fireEvent.pointerMove(first, { pointerType: "mouse", buttons: 1, clientX: 200, clientY: 140 });
  expect(document.querySelector(".drag-ghost")).not.toBeNull(); // đang cầm lá (vẽ qua portal)
  fireEvent.pointerUp(first, { pointerType: "mouse" });
  expect(document.querySelector(".drag-ghost")).toBeNull();
  expect(handLabels(container)).toEqual(["4♠", "10♦", "2♥", "3♣"]);
  expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
});

test("kéo nhẹ (dưới 6px) vẫn chỉ là một cú bấm để chọn lá", () => {
  const { container } = render(<GameTable game={live(view())} {...baseProps} />);
  stubCardRects(container);
  const first = screen.getByRole("button", { name: "3♣" });
  fireEvent.pointerDown(first, { pointerType: "mouse", button: 0, buttons: 1, clientX: 28, clientY: 140 });
  fireEvent.pointerMove(first, { pointerType: "mouse", buttons: 1, clientX: 30, clientY: 141 });
  fireEvent.pointerUp(first, { pointerType: "mouse" });
  fireEvent.click(first);
  expect(handLabels(container)).toEqual(["3♣", "4♠", "10♦", "2♥"]);
  expect(first).toHaveAttribute("aria-pressed", "true");
});

const RANKS_FOR_TEST = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"];
const SUITS_FOR_TEST = ["♠", "♣", "♦", "♥"];
const sortToggle = () => screen.getByRole("button", { name: /Đổi cách xếp bài/ });
const handWith = (labels: string[]) =>
  live(view({ yourHand: labels.map((l) => RANKS_FOR_TEST.indexOf(l.slice(0, -1)) * 4 + SUITS_FOR_TEST.indexOf(l.slice(-1))) }));

test("bấm ⇄ sau khi tự kéo thả thì bỏ thứ tự tự xếp và xếp lại theo chế độ mới", () => {
  const { container } = render(<GameTable game={live(view())} {...baseProps} />);
  stubCardRects(container);
  const first = screen.getByRole("button", { name: "3♣" });
  fireEvent.pointerDown(first, { pointerType: "mouse", button: 0, buttons: 1, clientX: 28, clientY: 140 });
  fireEvent.pointerMove(first, { pointerType: "mouse", buttons: 1, clientX: 200, clientY: 140 });
  fireEvent.pointerUp(first, { pointerType: "mouse" });
  expect(handLabels(container)).toEqual(["4♠", "10♦", "2♥", "3♣"]);
  fireEvent.click(sortToggle());
  expect(handLabels(container)).toEqual(["3♣", "4♠", "10♦", "2♥"]); // 4 lá rời rạc: toàn lá lẻ, xếp theo hạng
  expect(sortToggle()).toHaveAttribute("aria-label", expect.stringContaining("đang xếp theo bộ"));
});

test("⇄ chuyển giữa xếp theo lá và xếp theo bộ; chế độ được nhớ cho ván / lượt sau", () => {
  // 3♠ 4♠ 5♠ là sảnh, 9♦ và 2♥ lẻ; xếp theo lá cho cùng thứ tự nhưng không có khoảng ngắt nhóm.
  const game = handWith(["2♥", "9♦", "5♠", "3♠", "4♠"]);
  const first = render(<GameTable game={game} {...baseProps} />);
  expect(handLabels(first.container)).toEqual(["3♠", "4♠", "5♠", "9♦", "2♥"]);
  expect(sortToggle()).toHaveAttribute("aria-label", expect.stringContaining("đang xếp theo lá"));
  expect(first.container.querySelectorAll(".group-start")).toHaveLength(0);

  fireEvent.click(sortToggle());
  expect(sortToggle()).toHaveAttribute("aria-label", expect.stringContaining("đang xếp theo bộ"));
  expect(handLabels(first.container)).toEqual(["3♠", "4♠", "5♠", "9♦", "2♥"]);
  // Nhóm: [3♠ 4♠ 5♠] [9♦] [2♥] → lá đầu của nhóm 2 và 3 có khoảng ngắt.
  expect(Array.from(first.container.querySelectorAll(".group-start")).map((e) => e.textContent)).toEqual(["9♦", "2♥"]);
  expect(first.container.querySelector<HTMLElement>(".my-hand")!.style.getPropertyValue("--g")).toBe("2");

  first.unmount(); // sang ván / lượt sau: component dựng lại nhưng vẫn giữ chế độ đã chọn
  const next = render(<GameTable game={game} {...baseProps} />);
  expect(sortToggle()).toHaveAttribute("aria-label", expect.stringContaining("đang xếp theo bộ"));
  expect(next.container.querySelectorAll(".group-start")).toHaveLength(2);
});

test("xếp theo bộ: nhóm khác loại cách nhau; đổi chế độ khi đang chọn lá vẫn giữ lá đã chọn (theo ID)", () => {
  // Đôi 7, bộ ba 9, sảnh 3-4-5 và 2 lá lẻ.
  const game = handWith(["K♠", "9♠", "9♣", "9♦", "7♣", "7♦", "3♠", "4♠", "5♠", "A♦"]);
  const { container } = render(<GameTable game={game} {...baseProps} />);
  fireEvent.click(sortToggle());
  // Sảnh | bộ ba | đôi | lá lẻ (đúng thứ tự hiển thị).
  expect(handLabels(container)).toEqual(["3♠", "4♠", "5♠", "9♠", "9♣", "9♦", "7♣", "7♦", "K♠", "A♦"]);
  expect(Array.from(container.querySelectorAll(".group-start")).map((e) => e.textContent)).toEqual(["9♠", "7♣", "K♠", "A♦"]);

  fireEvent.click(screen.getByRole("button", { name: "9♣" }));
  fireEvent.click(screen.getByRole("button", { name: "K♠" }));
  fireEvent.click(sortToggle()); // sang xếp theo lá
  expect(screen.getByRole("button", { name: "9♣" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "K♠" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "Đánh (2)" })).toBeInTheDocument();
  fireEvent.click(sortToggle()); // và quay lại xếp theo bộ
  expect(screen.getByRole("button", { name: "Đánh (2)" })).toBeInTheDocument();
});

test("thứ tự lá không đổi khi chạm chọn hoặc khi server gửi lại trạng thái với cùng các lá", () => {
  const { container, rerender } = render(<GameTable game={handWith(["9♦", "3♠", "4♠", "5♠", "K♣"])} {...baseProps} />);
  fireEvent.click(sortToggle());
  const before = handLabels(container);
  fireEvent.click(screen.getByRole("button", { name: "K♣" }));
  expect(handLabels(container)).toEqual(before); // chạm chọn không đổi thứ tự
  // Bản cập nhật mới của server: mảng bài mới (đảo thứ tự) nhưng cùng tập lá, ví dụ người khác vừa đánh.
  rerender(<GameTable game={handWith(["K♣", "5♠", "9♦", "4♠", "3♠"])} {...baseProps} />);
  expect(handLabels(container)).toEqual(before);
  expect(screen.getByRole("button", { name: "K♣" })).toHaveAttribute("aria-pressed", "true");
});

test("xếp theo bộ cập nhật khi các lá trên tay thay đổi (sau khi mình đánh bài)", () => {
  const { container, rerender } = render(<GameTable game={handWith(["3♠", "4♠", "5♠", "9♦", "K♣"])} {...baseProps} />);
  fireEvent.click(sortToggle());
  expect(container.querySelectorAll(".group-start")).toHaveLength(2); // sảnh | 9♦ | K♣
  rerender(<GameTable game={handWith(["9♦", "K♣"])} {...baseProps} />); // đã đánh cả sảnh
  expect(handLabels(container)).toEqual(["9♦", "K♣"]);
  expect(container.querySelectorAll(".group-start")).toHaveLength(1);
});

test("quét ngang trên vùng trống phía trên hàng bài để chọn cả dải, rồi đánh cùng lúc", () => {
  const onPlay = vi.fn();
  const { container } = render(<GameTable game={live(view())} {...baseProps} onPlay={onPlay} />);
  stubCardRects(container);
  const hand = container.querySelector<HTMLElement>(".my-hand")!;
  fireEvent.pointerDown(hand, { pointerType: "mouse", button: 0, buttons: 1, clientX: 10, clientY: 90 });
  fireEvent.pointerMove(hand, { pointerType: "mouse", buttons: 1, clientX: 50, clientY: 90 });
  fireEvent.pointerUp(hand, { pointerType: "mouse" });
  fireEvent.click(screen.getByRole("button", { name: "Đánh (3)" }));
  expect(onPlay).toHaveBeenCalledWith(expect.arrayContaining([1, 4, 30]));
});

test("điện thoại: nút Thông tin mở popup, đóng bằng X, bấm ra ngoài hoặc Esc", () => {
  stubMatchMedia(true);
  render(<GameTable game={live(view())} {...baseProps} info={<p>Bảng điểm phiên</p>} onLeave={vi.fn()} />);
  const open = () => fireEvent.click(screen.getByRole("button", { name: /Thông tin/ }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  open();
  expect(screen.getByRole("dialog", { name: "Thông tin" })).toBeInTheDocument();
  expect(screen.getByText("Bảng điểm phiên")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  open();
  fireEvent.click(screen.getByRole("presentation")); // bấm ra ngoài
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  open();
  fireEvent.click(screen.getByText("Bảng điểm phiên")); // bấm trong popup thì không đóng
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("điện thoại: nút Rời phòng đỏ hiện popup xác nhận; chỉ rời khi xác nhận", () => {
  stubMatchMedia(true);
  const onLeave = vi.fn();
  render(<GameTable game={live(view())} {...baseProps} onLeave={onLeave} />);
  expect(screen.getByRole("button", { name: "Rời phòng" })).toHaveClass("danger");

  fireEvent.click(screen.getByRole("button", { name: "Rời phòng" }));
  let dialog = screen.getByRole("dialog", { name: "Rời phòng?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Ở lại" }));
  expect(onLeave).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Rời phòng" }));
  dialog = screen.getByRole("dialog", { name: "Rời phòng?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Rời phòng" }));
  expect(onLeave).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("máy tính: không có nút Thông tin / Rời phòng trong bàn (vẫn dùng bảng điểm và nút bên ngoài)", () => {
  stubMatchMedia(false);
  render(<GameTable game={live(view())} {...baseProps} info={<p>Bảng điểm phiên</p>} onLeave={vi.fn()} />);
  expect(screen.queryByRole("button", { name: /Thông tin/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Rời phòng" })).not.toBeInTheDocument();
});

// --- Ván 3 người -------------------------------------------------------------------------------------------------

const threePlayers = (overrides: Partial<GameView> = {}) =>
  view({
    players: [0, 1, 2].map((seat) => ({ seat, cardCount: 13, playedCount: 0, status: "ACTIVE", rank: null })),
    ...overrides,
  });

test("3 người: chỉ có hai đối thủ (trái và phải), không có ghế đối diện ở trên", () => {
  const { container } = render(<GameTable game={live(threePlayers())} {...baseProps} />);
  expect(container.querySelectorAll(".opponent")).toHaveLength(2);
  expect(container.querySelector(".opponent.pos-left")).not.toBeNull();
  expect(container.querySelector(".opponent.pos-right")).not.toBeNull();
  expect(container.querySelector(".opponent.pos-top")).toBeNull();
  // Ghế kế tiếp của mình (ghế 1) ở bên trái, ghế 2 ở bên phải.
  expect(container.querySelector(".opponent.pos-left")).toHaveTextContent("Huy");
  expect(container.querySelector(".opponent.pos-right")).toHaveTextContent("Minh");
});

test("3 người: bài người ghế 2 đánh bay vào từ bên phải, người ghế 1 từ bên trái", () => {
  const trick = (seat: number) => ({
    leader: seat,
    top: [44, 47],
    topCombo: "PAIR",
    topSeat: seat,
    topIsChop: false,
    passed: [],
    chainValue: 0,
  });
  const fromSeat2 = render(<GameTable game={live(threePlayers({ trick: trick(2), firstMovePending: false }))} {...baseProps} />);
  expect(fromSeat2.container.querySelector(".trick-cards")).toHaveClass("from-right");
  fromSeat2.unmount();
  const fromSeat1 = render(<GameTable game={live(threePlayers({ trick: trick(1), firstMovePending: false }))} {...baseProps} />);
  expect(fromSeat1.container.querySelector(".trick-cards")).toHaveClass("from-left");
});

test("lá mở ván lấy từ server: hiện 3♦ khi 3♣ không được chia, mặc định vẫn là 3♣", () => {
  const threeDiamonds = 2; // 3♦
  const { rerender } = render(<GameTable game={live(threePlayers({ openingCard: threeDiamonds }))} {...baseProps} />);
  expect(screen.getByText("Bạn mở vòng (phải có 3♦)")).toBeInTheDocument();
  rerender(<GameTable game={live(threePlayers())} {...baseProps} />); // server cũ không gửi openingCard
  expect(screen.getByText("Bạn mở vòng (phải có 3♣)")).toBeInTheDocument();
});

test("3 người: bong bóng chat của người ngồi bên phải có đuôi bên phải", () => {
  const { container } = render(
    <GameTable game={live(threePlayers())} {...baseProps} chats={{ 2: { text: "Toang rồi", key: 1 } }} />,
  );
  expect(container.querySelector(".opponent.pos-right .chat-bubble")).toHaveClass("tail-right");
});

test("bảng kết quả ván 3 người: 3 dòng, tổng điểm của 3 người", () => {
  const result: GameResult = {
    gameId: "g3",
    rules: { version: 1, hash: "h" },
    deckCommitment: "abcdef0123456789",
    deckReveal: null,
    result: {
      ...threePlayers({ phase: "FINISHED", endType: "NORMAL", current: null, yourSeat: 0 }),
      players: [
        { seat: 0, cardCount: 0, playedCount: 13, status: "FINISHED", rank: 1 },
        { seat: 1, cardCount: 0, playedCount: 13, status: "FINISHED", rank: 2 },
        { seat: 2, cardCount: 3, playedCount: 10, status: "FINISHED", rank: 3 },
      ],
      net: [300, -100, -200],
      transfers: [],
    },
  };
  render(<GameResultPanel result={result} seats={seats} yourSeat={0} onReady={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getAllByRole("row")).toHaveLength(4); // tiêu đề + 3 người
  expect(screen.getByText("+300")).toBeInTheDocument();
  expect(screen.getByText(/Tổng điểm 3 người: 0/)).toBeInTheDocument();
});
