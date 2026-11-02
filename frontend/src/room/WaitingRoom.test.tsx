import { fireEvent, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { RoomState } from "../api/guest";
import { renderWithProviders } from "../test-utils";
import { WaitingRoom } from "./WaitingRoom";

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
  expect(screen.getByRole("link", { name: "Luật v2" })).toHaveAttribute("href", "/rules");
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
