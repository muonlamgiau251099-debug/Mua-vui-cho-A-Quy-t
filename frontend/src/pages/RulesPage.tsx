import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import { rulesApi, type CatalogRule, type FieldSpec } from "../api/rules";
import { formatValue, getPath } from "../lib/config";

// Trang xem luật cho người chơi: chỉ đọc (ID 134, 138). Nhóm theo đúng các nhóm trong file Excel.
export function RulesPage() {
  const catalog = useQuery({ queryKey: ["rules", "catalog"], queryFn: rulesApi.catalog, staleTime: Infinity });
  const schema = useQuery({ queryKey: ["rules", "schema"], queryFn: rulesApi.schema, staleTime: Infinity });
  const active = useQuery({ queryKey: ["rules", "active"], queryFn: rulesApi.publicActive });

  const fieldsByExcelId = useMemo(() => {
    const map = new Map<number, FieldSpec[]>();
    for (const f of schema.data?.fields ?? []) for (const id of f.excelIds) map.set(id, [...(map.get(id) ?? []), f]);
    return map;
  }, [schema.data]);

  const groups = useMemo(() => {
    const map = new Map<string, CatalogRule[]>();
    for (const r of catalog.data?.rules ?? []) map.set(r.group, [...(map.get(r.group) ?? []), r]);
    return [...map.entries()];
  }, [catalog.data]);

  const error = catalog.error ?? schema.error ?? active.error;
  if (error) return <main className="app"><p role="alert">{errorMessage(error)}</p></main>;
  if (!catalog.data || !schema.data || !active.data) return <main className="app"><p>Đang tải…</p></main>;

  const currentValue = (rule: CatalogRule): string => {
    const fields = rule.excelId === null ? [] : (fieldsByExcelId.get(rule.excelId) ?? []);
    if (fields.length === 0) return rule.default;
    return fields.map((f) => `${fields.length > 1 ? `${f.label}: ` : ""}${formatValue(f, getPath(active.data.config, f.path))}`).join("; ");
  };

  return (
    <main className="app wide">
      <p>
        <Link to="/">← Trang chủ</Link>
      </p>
      <h1>Luật đang áp dụng</h1>
      <p>
        Phiên bản <strong>v{active.data.version}</strong> · mã <code>{active.data.configHash.slice(0, 8)}</code>. Luật do
        Admin hệ thống quản lý và áp dụng cho mọi phòng; người chơi chỉ xem.
      </p>
      {groups.map(([group, rules]) => (
        <section key={group}>
          <h2>{group}</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Luật</th>
                <th>Mô tả</th>
                <th>Giá trị</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.excelId}>
                  <td>{r.excelId}</td>
                  <td>{r.name}</td>
                  <td>{r.description}</td>
                  <td>{currentValue(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </main>
  );
}
