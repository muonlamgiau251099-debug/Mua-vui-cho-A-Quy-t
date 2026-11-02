import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { errorMessage } from "../api/client";
import { rulesApi, type FieldSpec, type ValidationReport } from "../api/rules";
import { formatValue } from "../lib/config";
import { IssueList } from "./IssueList";

type Props = {
  report: ValidationReport;
  activeVersion: number;
  specs: Map<string, FieldSpec>;
  onClose: () => void;
};

export function PublishDialog({ report, activeVersion, specs, onClose }: Props) {
  const queryClient = useQueryClient();
  const diff = useQuery({ queryKey: ["admin", "diff"], queryFn: rulesApi.diff });
  const [note, setNote] = useState("");
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const warningCodes = [...new Set(report.warnings.map((w) => w.code))];

  const publish = useMutation({
    mutationFn: () =>
      rulesApi.publish({
        expectedHash: report.configHash ?? "",
        expectedActiveVersion: activeVersion,
        note: note.trim(),
        acknowledgedWarnings: acknowledged,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });

  const canPublish =
    report.ok && note.trim().length >= 3 && warningCodes.every((c) => acknowledged.includes(c)) && !publish.isPending;

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-labelledby="publish-title">
      <div className="dialog">
        <h2 id="publish-title">Xuất bản luật v{activeVersion + 1}</h2>
        <p>Luật mới áp dụng cho <strong>ván tiếp theo của mọi phòng</strong>. Ván đang chơi vẫn dùng luật cũ.</p>

        <h3>Thay đổi so với v{activeVersion}</h3>
        {diff.isLoading && <p>Đang tải…</p>}
        {diff.data && (
          <table className="diff-table">
            <thead>
              <tr>
                <th>Luật</th>
                <th>Đang áp dụng</th>
                <th>Mới</th>
              </tr>
            </thead>
            <tbody>
              {diff.data.changes.map((c) => (
                <tr key={c.path}>
                  <td>
                    {c.label} <span className="excel-ids">{c.excelIds.map((id) => `#${id}`).join(" ")}</span>
                  </td>
                  <td>{formatValue(specs.get(c.path), c.before)}</td>
                  <td>{formatValue(specs.get(c.path), c.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3>Kiểm tra</h3>
        <IssueList report={report} />
        {warningCodes.map((code) => (
          <label key={code} className="ack">
            <input
              type="checkbox"
              checked={acknowledged.includes(code)}
              onChange={(e) =>
                setAcknowledged((prev) => (e.target.checked ? [...prev, code] : prev.filter((c) => c !== code)))
              }
            />
            Tôi đã đọc cảnh báo {code}
          </label>
        ))}

        <label htmlFor="publish-note">Ghi chú (bắt buộc)</label>
        <textarea id="publish-note" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />

        {publish.error && <p role="alert" className="error">{errorMessage(publish.error)}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="button" className="primary" disabled={!canPublish} onClick={() => publish.mutate()}>
            Xuất bản
          </button>
        </div>
      </div>
    </div>
  );
}
