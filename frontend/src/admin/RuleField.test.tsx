import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { FieldSpec } from "../api/rules";
import { RuleField } from "./RuleField";

const base = { group: "g", groupLabel: "G", min: null, max: null, options: [] };

test("ô bật/tắt gọi onChange và hiển thị giá trị đang áp dụng khi khác", () => {
  const spec: FieldSpec = { ...base, path: "chop.allowChain", label: "Cho phép chặt chồng", kind: "bool", excelIds: [41] };
  const onChange = vi.fn();
  render(
    <RuleField
      spec={spec}
      value={false}
      activeValue={true}
      disabled={false}
      issues={[]}
      describe={() => "Cho phép tiếp tục chặt bộ vừa chặt"}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByLabelText("Cho phép chặt chồng"));
  expect(onChange).toHaveBeenCalledWith(true);
  expect(screen.getByText("Đang áp dụng: Bật")).toBeInTheDocument();
  expect(screen.getByText("#41")).toBeInTheDocument();
});

test("danh sách thứ tự đổi vị trí khi bấm nút lên", () => {
  const spec: FieldSpec = {
    ...base,
    path: "instantWin.priorityOrder",
    label: "Ưu tiên tới trắng",
    kind: "order",
    excelIds: [62],
    options: [
      { value: "FOUR_TWOS", label: "4 heo" },
      { value: "DRAGON", label: "Sảnh rồng" },
      { value: "SIX_PAIRS", label: "6 đôi" },
    ],
  };
  const onChange = vi.fn();
  const order = ["FOUR_TWOS", "DRAGON", "SIX_PAIRS"];
  render(
    <RuleField spec={spec} value={order} activeValue={order} disabled={false} issues={[]} describe={() => undefined} onChange={onChange} />,
  );
  fireEvent.click(screen.getByLabelText("Đưa SIX_PAIRS lên"));
  expect(onChange).toHaveBeenCalledWith(["FOUR_TWOS", "SIX_PAIRS", "DRAGON"]);
});

test("ô bị khóa khi chưa có bản nháp", () => {
  const spec: FieldSpec = { ...base, path: "turn.timeLimitSeconds", label: "Thời gian", kind: "int", excelIds: [141], min: 10, max: 120 };
  render(<RuleField spec={spec} value={30} activeValue={30} disabled issues={[]} describe={() => undefined} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Thời gian")).toBeDisabled();
});
