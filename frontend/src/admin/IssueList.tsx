import type { Issue, ValidationReport } from "../api/rules";

const LEVEL_LABEL: Record<Issue["level"], string> = { error: "Lỗi", warning: "Cảnh báo", info: "Ghi chú" };

export function IssueList({ report }: { report: ValidationReport }) {
  const issues = [...report.errors, ...report.warnings, ...report.infos];
  if (issues.length === 0) return <p className="ok">Không có lỗi hay cảnh báo.</p>;
  return (
    <ul className="issue-list">
      {issues.map((i) => (
        <li key={`${i.code}-${i.path}-${i.message}`} className={`issue issue-${i.level}`}>
          <strong>
            {LEVEL_LABEL[i.level]} {i.code}
          </strong>{" "}
          {i.message}
          {i.excelIds.length > 0 && <span className="excel-ids"> (Excel ID {i.excelIds.join(", ")})</span>}
        </li>
      ))}
    </ul>
  );
}
