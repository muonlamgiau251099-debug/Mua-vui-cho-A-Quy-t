import type { FieldSpec } from "../api/rules";

// Đọc / ghi giá trị trong config lồng nhau theo đường dẫn "a.b.c" (không sửa object gốc).

export function getPath(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => {
    if (node && typeof node === "object" && key in node) return (node as Record<string, unknown>)[key];
    return undefined;
  }, obj);
}

export function setPath<T extends Record<string, unknown>>(obj: T, path: string, value: unknown): T {
  const [head, ...rest] = path.split(".");
  if (head === undefined) return obj;
  const child = obj[head];
  const next =
    rest.length === 0 ? value : setPath((child && typeof child === "object" ? child : {}) as Record<string, unknown>, rest.join("."), value);
  return { ...obj, [head]: next };
}

export function formatValue(spec: FieldSpec | undefined, value: unknown): string {
  if (typeof value === "boolean") return value ? "Bật" : "Tắt";
  const label = (v: unknown) => spec?.options.find((o) => o.value === v)?.label ?? String(v);
  if (Array.isArray(value)) return value.map(label).join(" > ");
  if (spec?.kind === "enum") return label(value);
  return value === undefined || value === null ? "—" : String(value);
}
