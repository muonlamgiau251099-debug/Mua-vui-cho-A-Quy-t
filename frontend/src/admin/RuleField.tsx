import type { FieldSpec, Issue } from "../api/rules";
import { formatValue } from "../lib/config";

type Props = {
  spec: FieldSpec;
  value: unknown;
  activeValue: unknown;
  disabled: boolean;
  issues: Issue[];
  describe: (excelId: number) => string | undefined;
  onChange: (value: unknown) => void;
};

// Một ô chỉnh luật: toggle / số / chọn / danh sách thứ tự, kèm Excel ID và mô tả từ file Excel.
export function RuleField({ spec, value, activeValue, disabled, issues, describe, onChange }: Props) {
  const changed = JSON.stringify(value) !== JSON.stringify(activeValue);
  const inputId = `field-${spec.path}`;
  const help = spec.excelIds
    .map((id) => (describe(id) ? `ID ${id}: ${describe(id)}` : `ID ${id}`))
    .join("\n");

  return (
    <div className={`rule-field${changed ? " changed" : ""}${issues.length ? " has-issue" : ""}`}>
      <div className="rule-field-head">
        <label htmlFor={inputId} title={help || undefined}>
          {spec.label}
        </label>
        <span className="excel-ids">
          {spec.excelIds.length ? spec.excelIds.map((id) => `#${id}`).join(" ") : "ngoài Excel"}
        </span>
      </div>
      <div className="rule-field-input">{renderInput()}</div>
      {changed && (
        <div className="rule-field-note">Đang áp dụng: {formatValue(spec, activeValue)}</div>
      )}
      {issues.map((i) => (
        <div key={i.code + i.message} className={`issue issue-${i.level}`}>
          {i.code}: {i.message}
        </div>
      ))}
    </div>
  );

  function renderInput() {
    switch (spec.kind) {
      case "bool":
        return (
          <label className="toggle">
            <input
              id={inputId}
              type="checkbox"
              checked={value === true}
              disabled={disabled}
              onChange={(e) => onChange(e.target.checked)}
            />
            <span>{value === true ? "Bật" : "Tắt"}</span>
          </label>
        );
      case "int":
        return (
          <input
            id={inputId}
            type="number"
            step={1}
            min={spec.min ?? undefined}
            max={spec.max ?? undefined}
            value={typeof value === "number" ? value : ""}
            disabled={disabled}
            onChange={(e) => {
              if (e.target.value !== "") onChange(Math.trunc(Number(e.target.value)));
            }}
          />
        );
      case "enum":
        return (
          <select id={inputId} value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
            {spec.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        );
      case "order": {
        const items = Array.isArray(value) ? (value as string[]) : [];
        const move = (from: number, to: number) => {
          const next = [...items];
          const [item] = next.splice(from, 1);
          if (item !== undefined) next.splice(to, 0, item);
          onChange(next);
        };
        return (
          <ol id={inputId} className="order-list">
            {items.map((item, index) => (
              <li key={item}>
                <span>{spec.options.find((o) => o.value === item)?.label ?? item}</span>
                <button
                  type="button"
                  aria-label={`Đưa ${item} lên`}
                  disabled={disabled || index === 0}
                  onClick={() => move(index, index - 1)}
                >
                  ▲
                </button>
                <button
                  type="button"
                  aria-label={`Đưa ${item} xuống`}
                  disabled={disabled || index === items.length - 1}
                  onClick={() => move(index, index + 1)}
                >
                  ▼
                </button>
              </li>
            ))}
          </ol>
        );
      }
    }
  }
}
