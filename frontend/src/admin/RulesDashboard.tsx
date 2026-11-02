import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ApiError, errorMessage } from "../api/client";
import { rulesApi, type FieldSpec, type RuleConfig, type ValidationReport } from "../api/rules";
import { getPath, setPath } from "../lib/config";
import { IssueList } from "./IssueList";
import { PublishDialog } from "./PublishDialog";
import { RuleField } from "./RuleField";

export function RulesDashboard() {
  const queryClient = useQueryClient();
  const schema = useQuery({ queryKey: ["rules", "schema"], queryFn: rulesApi.schema, staleTime: Infinity });
  const catalog = useQuery({ queryKey: ["rules", "catalog"], queryFn: rulesApi.catalog, staleTime: Infinity });
  const active = useQuery({ queryKey: ["admin", "active"], queryFn: rulesApi.active });
  const draft = useQuery({ queryKey: ["admin", "draft"], queryFn: rulesApi.draft });

  const [group, setGroup] = useState("turn");
  const [edited, setEdited] = useState<RuleConfig | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Mỗi khi bản nháp trên server đổi (lockVersion mới) thì nạp lại bản đang sửa.
  const draftLock = draft.data?.lockVersion;
  useEffect(() => {
    setEdited(draft.data ? draft.data.config : null);
    setReport(null);
  }, [draft.data, draftLock]);

  const specs = useMemo(() => new Map((schema.data?.fields ?? []).map((f) => [f.path, f])), [schema.data]);
  const descriptions = useMemo(
    () => new Map((catalog.data?.rules ?? []).map((r) => [r.excelId, r.description ?? r.name])),
    [catalog.data],
  );

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });
  const onError = (e: unknown) => {
    if (e instanceof ApiError && e.code === "DRAFT_CHANGED") {
      setMessage("Bản nháp vừa được Admin khác sửa. Đã tải lại bản mới nhất.");
      void refresh();
    } else setMessage(errorMessage(e));
  };

  const create = useMutation({ mutationFn: () => rulesApi.createDraft(), onSuccess: refresh, onError });
  const save = useMutation({
    mutationFn: () => rulesApi.saveDraft(draft.data!.lockVersion, edited!),
    onSuccess: async () => {
      setMessage("Đã lưu bản nháp.");
      await refresh();
    },
    onError,
  });
  const discard = useMutation({
    mutationFn: () => rulesApi.discardDraft(draft.data!.lockVersion),
    onSuccess: refresh,
    onError,
  });
  const validate = useMutation({ mutationFn: rulesApi.validate, onSuccess: setReport, onError });

  if (schema.isLoading || active.isLoading || draft.isLoading) return <p>Đang tải…</p>;
  if (schema.error || active.error || draft.error)
    return <p role="alert">{errorMessage(schema.error ?? active.error ?? draft.error)}</p>;

  const activeConfig = active.data!.config;
  const config = edited ?? activeConfig;
  const editing = draft.data !== null && draft.data !== undefined;
  const dirty = editing && JSON.stringify(edited) !== JSON.stringify(draft.data!.config);
  const fields = (schema.data?.fields ?? []).filter((f) => f.group === group);
  const issuesFor = (spec: FieldSpec) =>
    report ? [...report.errors, ...report.warnings].filter((i) => i.path === spec.path || spec.path.startsWith(`${i.path}.`)) : [];

  return (
    <section>
      <header className="dashboard-head">
        <div>
          <h1>Luật toàn hệ thống</h1>
          <p>
            Đang áp dụng: <strong>v{active.data!.version}</strong> · mã {active.data!.configHash.slice(0, 8)}
            {editing && (
              <>
                {" "}
                · Bản nháp lần sửa {draft.data!.lockVersion}
                {dirty && <strong className="dirty"> · chưa lưu</strong>}
              </>
            )}
          </p>
        </div>
        <div className="actions">
          {!editing && (
            <button className="primary" onClick={() => create.mutate()} disabled={create.isPending}>
              Tạo bản nháp
            </button>
          )}
          {editing && (
            <>
              <button onClick={() => setEdited(draft.data!.config)} disabled={!dirty}>
                Bỏ thay đổi
              </button>
              <button className="primary" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
                Lưu nháp
              </button>
              <button onClick={() => validate.mutate()} disabled={dirty || validate.isPending}>
                Kiểm tra
              </button>
              <button
                className="primary"
                onClick={() => setPublishing(true)}
                disabled={dirty || !report?.ok}
                title={!report ? "Cần bấm Kiểm tra trước" : undefined}
              >
                Xuất bản…
              </button>
              <button
                className="danger"
                onClick={() => window.confirm("Hủy bản nháp này?") && discard.mutate()}
                disabled={discard.isPending}
              >
                Hủy bản nháp
              </button>
            </>
          )}
        </div>
      </header>

      {message && (
        <p className="message" role="status" onClick={() => setMessage(null)}>
          {message}
        </p>
      )}
      {report && (
        <div className="report">
          <IssueList report={report} />
        </div>
      )}
      {!editing && <p className="hint">Đang xem luật đang áp dụng (chỉ đọc). Bấm “Tạo bản nháp” để sửa.</p>}

      <nav className="tabs" aria-label="Nhóm luật">
        {schema.data!.groups.map((g) => (
          <button key={g.key} className={g.key === group ? "tab active" : "tab"} onClick={() => setGroup(g.key)}>
            {g.label}
          </button>
        ))}
      </nav>

      <div className="field-grid">
        {fields.map((spec) => (
          <RuleField
            key={spec.path}
            spec={spec}
            value={getPath(config, spec.path)}
            activeValue={getPath(activeConfig, spec.path)}
            disabled={!editing}
            issues={issuesFor(spec)}
            describe={(id) => descriptions.get(id) ?? undefined}
            onChange={(value) => {
              setEdited((prev) => setPath(prev ?? activeConfig, spec.path, value));
              setReport(null);
            }}
          />
        ))}
      </div>

      {publishing && report && (
        <PublishDialog
          report={report}
          activeVersion={active.data!.version!}
          specs={specs}
          onClose={() => setPublishing(false)}
        />
      )}
    </section>
  );
}
