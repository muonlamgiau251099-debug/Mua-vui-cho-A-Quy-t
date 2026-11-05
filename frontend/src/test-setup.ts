import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// Mỗi test bắt đầu với bộ nhớ trình duyệt sạch (vd chế độ xếp bài đã nhớ ở test trước).
afterEach(() => window.localStorage.clear());

// jsdom chưa có PointerEvent nên fireEvent.pointerDown(...) sẽ mất clientX/clientY/pointerType.
// Bản tối thiểu này đủ cho test cử chỉ kéo thả bài.
if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: PointerEventPolyfill, configurable: true });
}
