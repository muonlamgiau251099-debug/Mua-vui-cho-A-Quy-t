import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { errorMessage } from "../api/client";
import { rulesApi } from "../api/rules";

const STATUS_LABEL: Record<string, string> = { ACTIVE: "Đang áp dụng", SUPERSEDED: "Đã thay thế" };

export function VersionsPage() {
  const queryClient = useQueryClient();
  const versions = useQuery({ queryKey: ["admin", "versions"], queryFn: rulesApi.versions });
  const [target, setTarget] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const active = versions.data?.items.find((v) => v.status === "ACTIVE");

  const rollback = useMutation({
    mutationFn: () =>
      rulesApi.rollback({ targetVersion: target!, expectedActiveVersion: active!.version!, note: note.trim() }),
    onSuccess: async () => {
      setTarget(null);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  if (versions.isLoading) return <p>Đang tải…</p>;
  if (versions.error) return <p role="alert">{errorMessage(versions.error)}</p>;

  return (
    <section>
      <h1>Lịch sử phiên bản luật</h1>
      <p className="hint">Quay lại phiên bản cũ sẽ tạo một phiên bản mới có cùng nội dung; lịch sử không bị xóa.</p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Phiên bản</th>
            <th>Trạng thái</th>
            <th>Xuất bản lúc</th>
            <th>Ghi chú</th>
            <th>Mã</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {versions.data!.items.map((v) => (
            <tr key={v.version}>
              <td>v{v.version}</td>
              <td>{STATUS_LABEL[v.status] ?? v.status}</td>
              <td>{v.publishedAt ? new Date(v.publishedAt).toLocaleString("vi-VN") : "—"}</td>
              <td>{v.note}</td>
              <td>
                <code>{v.configHash.slice(0, 8)}</code>
              </td>
              <td>
                {v.status !== "ACTIVE" && (
                  <button onClick={() => setTarget(v.version)}>Quay lại phiên bản này</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {target !== null && (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="rollback-title">
          <div className="dialog">
            <h2 id="rollback-title">
              Quay lại nội dung v{target} (tạo v{(active?.version ?? 0) + 1})
            </h2>
            <label htmlFor="rollback-note">Lý do (bắt buộc)</label>
            <textarea id="rollback-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
            {rollback.error && <p role="alert" className="error">{errorMessage(rollback.error)}</p>}
            <div className="dialog-actions">
              <button onClick={() => setTarget(null)}>Hủy</button>
              <button
                className="primary"
                disabled={note.trim().length < 3 || rollback.isPending}
                onClick={() => rollback.mutate()}
              >
                Xác nhận
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
