import type { FieldSpec } from "../api/rules";
import { formatValue, getPath, setPath } from "./config";

const config = { turn: { timeLimitSeconds: 30 }, chop: { fourKind: { vsSingleTwo: true } } };

test("getPath đọc giá trị lồng nhau, trả undefined nếu không có", () => {
  expect(getPath(config, "chop.fourKind.vsSingleTwo")).toBe(true);
  expect(getPath(config, "chop.khongCo")).toBeUndefined();
});

test("setPath trả object mới và không sửa object gốc", () => {
  const next = setPath(config, "turn.timeLimitSeconds", 45);
  expect(getPath(next, "turn.timeLimitSeconds")).toBe(45);
  expect(config.turn.timeLimitSeconds).toBe(30);
  expect(next.chop).toBe(config.chop); // nhánh không đổi được giữ nguyên tham chiếu
});

test("formatValue hiển thị bool, enum và danh sách thứ tự bằng tiếng Việt", () => {
  const spec: FieldSpec = {
    path: "instantWin.priorityOrder",
    group: "instantWin",
    groupLabel: "Tới trắng",
    label: "Ưu tiên",
    kind: "order",
    excelIds: [62],
    min: null,
    max: null,
    options: [
      { value: "FOUR_TWOS", label: "4 heo" },
      { value: "DRAGON", label: "Sảnh rồng" },
    ],
  };
  expect(formatValue(spec, ["FOUR_TWOS", "DRAGON"])).toBe("4 heo > Sảnh rồng");
  expect(formatValue(undefined, false)).toBe("Tắt");
});
