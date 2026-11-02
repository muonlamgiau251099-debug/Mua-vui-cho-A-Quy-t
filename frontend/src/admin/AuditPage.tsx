import { useInfiniteQuery } from "@tanstack/react-query";
import { errorMessage } from "../api/client";
import { rulesApi, type AuditItem } from "../api/rules";

const ACTION_LABEL: Record<string, string> = {
  SEED: "Khởi tạo luật v1",
  LOGIN: "Đăng nhập",
  LOGIN_FAILED: "Đăng nhập thất bại",
  LOGOUT: "Đăng xuất",
  CREATE_DRAFT: "Tạo bản nháp",
  UPDATE_DRAFT: "Lưu bản nháp",
  DISCARD_DRAFT: "Hủy bản nháp",
  PUBLISH: "Xuất bản",
  ROLLBACK: "Quay lại phiên bản",
};

function summary(item: AuditItem): string {
  const d = item.detail ?? {};
  const parts: string[] = [];
  if (typeof d.version === "number") parts.push(`v${d.version}`);
  if (typeof d.targetVersion === "number") parts.push(`từ nội dung v${d.targetVersion}`);
  if (item.diff?.length) parts.push(`${item.diff.length} thay đổi: ${item.diff.map((c) => c.label).join(", ")}`);
  if (typeof d.note === "string") parts.push(`“${d.note}”`);
  if (typeof d.username === "string") parts.push(`tên: ${d.username}`);
  return parts.join(" · ");
}

export function AuditPage() {
  const audit = useInfiniteQuery({
    queryKey: ["admin", "audit"],
    queryFn: ({ pageParam }) => rulesApi.audit(pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.nextBefore ?? undefined,
  });

  if (audit.isLoading) return <p>Đang tải…</p>;
  if (audit.error) return <p role="alert">{errorMessage(audit.error)}</p>;
  const items = audit.data!.pages.flatMap((p) => p.items);

  return (
    <section>
      <h1>Nhật ký thao tác</h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>Admin</th>
            <th>Thao tác</th>
            <th>Chi tiết</th>
            <th>IP</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{new Date(item.createdAt).toLocaleString("vi-VN")}</td>
              <td>{item.admin ?? "—"}</td>
              <td>{ACTION_LABEL[item.action] ?? item.action}</td>
              <td>{summary(item)}</td>
              <td>{item.ip ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {audit.hasNextPage && (
        <button onClick={() => void audit.fetchNextPage()} disabled={audit.isFetchingNextPage}>
          Tải thêm
        </button>
      )}
    </section>
  );
}
