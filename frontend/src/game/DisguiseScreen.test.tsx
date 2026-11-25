import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DisguiseScreen, setDisguiseTurn } from "./DisguiseScreen";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  act(() => setDisguiseTurn({ myTurn: false, deadline: null, clockOffset: 0 }));
});

describe("DisguiseScreen", () => {
  it("↓ bật, ↑ tắt", () => {
    render(<DisguiseScreen />);
    expect(screen.queryByTestId("disguise")).toBeNull();
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(screen.getByTestId("disguise")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(screen.queryByTestId("disguise")).toBeNull();
  });

  it("không bật khi đang gõ chữ", () => {
    render(
      <>
        <input aria-label="chat" />
        <DisguiseScreen />
      </>,
    );
    fireEvent.keyDown(screen.getByLabelText("chat"), { key: "ArrowDown" });
    expect(screen.queryByTestId("disguise")).toBeNull();
  });

  it("không bật trên điện thoại (màn nhỏ)", () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    render(<DisguiseScreen />);
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(screen.queryByTestId("disguise")).toBeNull();
  });

  it("chưa tới lượt: giữ số 1649 màu xanh", () => {
    render(<DisguiseScreen />);
    fireEvent.keyDown(window, { key: "ArrowDown" });
    const badges = screen.getAllByTestId("ol-badge");
    expect(badges).toHaveLength(2);
    badges.forEach((b) => {
      expect(b).toHaveTextContent("1649");
      expect(b).not.toHaveClass("ol-turn");
    });
  });

  it("tới lượt mình: đếm ngược giây và nhấp nháy đỏ, hết lượt thì về 1649", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000_000_000);
    render(<DisguiseScreen />);
    act(() => {
      setDisguiseTurn({ myTurn: true, deadline: 1_000_000_000 + 25, clockOffset: 0 });
      fireEvent.keyDown(window, { key: "ArrowDown" });
    });
    expect(screen.getAllByTestId("ol-badge")[0]).toHaveTextContent("25");
    expect(screen.getAllByTestId("ol-badge")[0]).toHaveClass("ol-turn");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getAllByTestId("ol-badge")[0]).toHaveTextContent("20");
    act(() => setDisguiseTurn({ myTurn: false, deadline: null, clockOffset: 0 }));
    expect(screen.getAllByTestId("ol-badge")[0]).toHaveTextContent("1649");
  });
});
