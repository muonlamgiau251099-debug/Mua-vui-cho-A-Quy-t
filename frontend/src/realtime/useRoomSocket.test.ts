import type { RoomState } from "../api/guest";
import { closeReason, newerState, reconnectDelay } from "./useRoomSocket";

const state = (version: number, roomId = "r1"): RoomState => ({
  roomId,
  code: "K7QX2M",
  status: "WAITING",
  version,
  ownerSeat: 0,
  seats: [],
  allReady: false,
  rules: null,
});

test("kết nối lại với thời gian chờ tăng dần, tối đa 8 giây", () => {
  expect([1, 2, 3, 4, 5, 10].map(reconnectDelay)).toEqual([500, 1000, 2000, 4000, 8000, 8000]);
});

test("bỏ qua trạng thái phòng cũ đến trễ", () => {
  expect(newerState(state(5), state(4)).version).toBe(5);
  expect(newerState(state(5), state(6)).version).toBe(6);
  expect(newerState(state(9, "khac"), state(1)).version).toBe(1); // phòng khác → nhận
});

test("mã đóng cuối cùng thì không kết nối lại, mã khác thì có", () => {
  expect(closeReason(4409)).toMatch(/tab hoặc thiết bị khác/);
  expect(closeReason(4000)).toBe("Phòng đã đóng.");
  expect(closeReason(1006)).toBeNull(); // rớt mạng → tự kết nối lại
});
