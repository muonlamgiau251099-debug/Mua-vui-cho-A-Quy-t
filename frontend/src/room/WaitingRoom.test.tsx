import { fireEvent, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import type { RoomState } from "../api/guest";
import { renderWithProviders } from "../test-utils";
import { WaitingRoom } from "./WaitingRoom";

// Nội dung luật gọi API; ở đây chỉ cần biết popup có mở / đóng đúng.
vi.mock("../pages/RulesView", () => ({ RulesView: () => <p>Nội dung luật giả lập</p> }));

const room: RoomState = {
  roomId: "r1",
  code: "K7QX2M",
  status: "WAITING",
  version: 3,
  ownerSeat: 0,
  allReady: false,
  rules: { version: 2, configHash: "abc" },
  seats: [
    { seatNo: 0, occupied: true, nickname: "Lan", ready: true, connected: true, holdUntil: null },
    { seatNo: 1, occupied: true, nickname: "Huy", ready: false, connected: true, holdUntil: null },
    {
      seatNo: 2,
      occupied: true,
      nickname: "Minh",
      ready: false,
      connected: false,
      holdUntil: new Date(Date.now() + 90_000).toISOString(),
    },
    { seatNo: 3, occupied: false, nickname: null, ready: false, connected: false, holdUntil: null },
  ],
};

function renderRoom(yourSeat: number, onReady = vi.fn()) {
  renderWithProviders(
    <WaitingRoom
      room={room}
      yourSeat={yourSeat}
      canAct
      inviteUrl="http://localhost/r/K7QX2M"
      onReady={onReady}
      onLeave={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  return onReady;
}

test("hiển thị 4 ghế với trạng thái sẵn sàng, mất kết nối và ghế trống", () => {
  renderRoom(1);
  expect(screen.getByText("✓ Sẵn sàng")).toBeInTheDocument();
  expect(screen.getByText(/Mất kết nối · giữ ghế (89|90)s/)).toBeInTheDocument();
  expect(screen.getByText("Ghế trống")).toBeInTheDocument();
  expect(screen.getByText("3/4 người · 1 sẵn sàng", { exact: false })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Luật v2" })).toBeInTheDocument(); // mở popup, không rời phòng
});

test("người chơi chưa sẵn sàng bấm Sẵn sàng", () => {
  const onReady = renderRoom(1);
  fireEvent.click(screen.getByRole("button", { name: "Sẵn sàng" }));
  expect(onReady).toHaveBeenCalledWith(true);
  expect(screen.queryByRole("button", { name: "Đóng phòng" })).not.toBeInTheDocument(); // không phải chủ phòng
});

test("chủ phòng đã sẵn sàng thấy nút Hủy sẵn sàng và Đóng phòng", () => {
  const onReady = renderRoom(0);
  fireEvent.click(screen.getByRole("button", { name: "Hủy sẵn sàng" }));
  expect(onReady).toHaveBeenCalledWith(false);
  expect(screen.getByRole("button", { name: "Đóng phòng" })).toBeInTheDocument();
  expect(screen.getByText("Lan (bạn)")).toBeInTheDocument();
});

test("chủ phòng có phiên đang chạy thấy nút bắt đầu phiên mới", () => {
  const onRestart = vi.fn();
  renderWithProviders(
    <WaitingRoom
      room={{ ...room, session: { sessionId: "s1", sessionNo: 1, gamesPlayed: 2, scores: [] } }}
      yourSeat={0}
      canAct
      inviteUrl="http://localhost/r/K7QX2M"
      onReady={vi.fn()}
      onLeave={vi.fn()}
      onClose={vi.fn()}
      onRestartSession={onRestart}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Bắt đầu phiên mới" }));
  expect(onRestart).toHaveBeenCalled();
});

test("sao chép link mời vẫn chạy khi không có navigator.clipboard (HTTP qua IP LAN)", async () => {
  const { copyText } = await import("./WaitingRoom");
  vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
  const exec = vi.fn().mockReturnValue(true);
  Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
  expect(await copyText("http://192.168.1.54:8080/r/K7QX2M")).toBe(true);
  expect(exec).toHaveBeenCalledWith("copy");
  vi.unstubAllGlobals();
});

function renderOwnerRoom(extra: Partial<React.ComponentProps<typeof WaitingRoom>> = {}) {
  return renderWithProviders(
    <WaitingRoom
      room={room}
      yourSeat={0}
      canAct
      inviteUrl="http://localhost/r/K7QX2M"
      onReady={vi.fn()}
      onLeave={vi.fn()}
      onClose={vi.fn()}
      {...extra}
    />,
  );
}

test("nút Sao chép link mời nằm cạnh mã phòng (không còn nút cũ bên ngoài) và chép đúng link mời", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  const { container } = renderOwnerRoom();
  expect(screen.getAllByRole("button", { name: "Sao chép link mời" })).toHaveLength(1);
  expect(screen.queryByText("http://localhost/r/K7QX2M")).not.toBeInTheDocument(); // không còn hiện URL dài
  const row = container.querySelector<HTMLElement>(".room-code-row")!;
  expect(within(row).getByText("K7QX2M")).toBeInTheDocument();
  fireEvent.click(within(row).getByRole("button", { name: "Sao chép link mời" }));
  expect(writeText).toHaveBeenCalledWith("http://localhost/r/K7QX2M");
  expect(await screen.findByText("Đã sao chép link mời")).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("thông tin phòng, Sẵn sàng, Rời phòng, Đóng phòng đều nằm trong bàn", () => {
  const { container } = renderOwnerRoom();
  const table = container.querySelector<HTMLElement>(".waiting-table")!;
  expect(within(table).getByText(/3\/4 người · 1 sẵn sàng/)).toBeInTheDocument();
  expect(within(table).getByRole("button", { name: "Luật v2" })).toBeInTheDocument();
  expect(within(table).getByRole("button", { name: "Hủy sẵn sàng" })).toHaveClass("ready-btn", "is-ready");
  expect(within(table).getByRole("button", { name: "Rời phòng" })).toHaveClass("leave-btn");
  expect(within(table).getByRole("button", { name: "Đóng phòng" })).toHaveClass("close-btn");
  expect(container.querySelector(".room-head")).toBeNull();
});

test("người không phải chủ phòng không có nút Đóng phòng; chưa sẵn sàng thì nút là 'Sẵn sàng'", () => {
  renderOwnerRoom({ yourSeat: 1 });
  expect(screen.queryByRole("button", { name: "Đóng phòng" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sẵn sàng" })).not.toHaveClass("is-ready");
});

test("điện thoại: có nút Thông tin mở popup điểm phiên; máy tính thì không", () => {
  const matchMedia = (matches: boolean) =>
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({ matches, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
  matchMedia(false);
  const desktop = renderOwnerRoom({ info: <p>Bảng điểm phiên</p> });
  expect(screen.queryByRole("button", { name: /Thông tin/ })).not.toBeInTheDocument();
  desktop.unmount();

  matchMedia(true);
  renderOwnerRoom({ info: <p>Bảng điểm phiên</p> });
  fireEvent.click(screen.getByRole("button", { name: /Thông tin/ }));
  expect(screen.getByRole("dialog", { name: "Thông tin" })).toHaveTextContent("Bảng điểm phiên");
  fireEvent.click(screen.getByRole("button", { name: "Đóng" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("bấm Luật mở popup luật ngay trong phòng; đóng bằng X (hoặc bấm ra ngoài / Esc) mà vẫn ở trong phòng", () => {
  const onLeave = vi.fn();
  renderOwnerRoom({ onLeave });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Luật v2" }));
  const dialog = screen.getByRole("dialog", { name: "Luật đang áp dụng" });
  expect(dialog).toHaveTextContent("Nội dung luật giả lập");

  fireEvent.click(within(dialog).getByRole("button", { name: "Đóng" })); // nút X
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hủy sẵn sàng" })).toBeInTheDocument(); // vẫn thấy phòng

  fireEvent.click(screen.getByRole("button", { name: "Luật v2" }));
  fireEvent.click(screen.getByRole("presentation")); // bấm ra ngoài
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Luật v2" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(onLeave).not.toHaveBeenCalled(); // không rời phòng
});
