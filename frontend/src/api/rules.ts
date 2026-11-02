import { ApiError, api } from "./client";

export type RuleConfig = Record<string, unknown>;

export type FieldSpec = {
  path: string;
  group: string;
  groupLabel: string;
  label: string;
  kind: "bool" | "int" | "enum" | "order";
  excelIds: number[];
  min: number | null;
  max: number | null;
  options: { value: string; label: string }[];
};

export type RuleSchema = {
  schemaVersion: number;
  groups: { key: string; label: string }[];
  fields: FieldSpec[];
  invariants: Record<string, unknown>;
};

export type RuleVersion = {
  version: number | null;
  status: "DRAFT" | "ACTIVE" | "SUPERSEDED" | "DISCARDED";
  configHash: string;
  basedOnVersion: number | null;
  note: string | null;
  createdAt: string | null;
  publishedAt: string | null;
  config?: RuleConfig;
};

export type Draft = RuleVersion & { config: RuleConfig; lockVersion: number; updatedAt: string | null };

export type Issue = { code: string; level: "error" | "warning" | "info"; path: string; excelIds: number[]; message: string };

export type ValidationReport = {
  ok: boolean;
  errors: Issue[];
  warnings: Issue[];
  infos: Issue[];
  configHash: string | null;
};

export type Change = { path: string; label: string; before: unknown; after: unknown; excelIds: number[] };

export type CatalogRule = {
  excelId: number | null;
  group: string;
  name: string;
  description: string | null;
  excelValue: string | null;
  ruleKey: string;
  class: string;
  default: string;
  status: string;
  source?: string;
};

export type Catalog = { ruleCount: number; rules: CatalogRule[]; extensions: CatalogRule[] };

export type AuditItem = {
  id: number;
  action: string;
  admin: string | null;
  ruleVersionId: number | null;
  diff: Change[] | null;
  detail: Record<string, unknown> | null;
  ip: string | null;
  createdAt: string;
};

export type PublicRules = { version: number; configHash: string; config: RuleConfig; publishedAt: string | null };

export const rulesApi = {
  schema: () => api<RuleSchema>("/api/rules/schema"),
  catalog: () => api<Catalog>("/api/rules/catalog"),
  publicActive: () => api<PublicRules>("/api/rules/active"),

  me: () => api<{ admin: { username: string } }>("/api/admin/me"),
  login: (username: string, password: string) =>
    api<{ admin: { username: string } }>("/api/admin/login", { method: "POST", body: { username, password } }),
  logout: () => api<void>("/api/admin/logout", { method: "POST" }),

  active: () => api<RuleVersion & { config: RuleConfig }>("/api/admin/rules/active"),
  versions: () => api<{ items: RuleVersion[] }>("/api/admin/rules/versions"),
  draft: async (): Promise<Draft | null> => {
    try {
      return await api<Draft>("/api/admin/rules/draft");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  createDraft: (fromVersion?: number) =>
    api<Draft>("/api/admin/rules/draft", { method: "POST", body: fromVersion ? { fromVersion } : {} }),
  saveDraft: (lockVersion: number, config: RuleConfig) =>
    api<Draft>("/api/admin/rules/draft", {
      method: "PUT",
      body: { config },
      headers: { "If-Match": `"${lockVersion}"` },
    }),
  discardDraft: (lockVersion: number) =>
    api<void>("/api/admin/rules/draft", { method: "DELETE", headers: { "If-Match": `"${lockVersion}"` } }),
  validate: () => api<ValidationReport>("/api/admin/rules/draft/validate", { method: "POST" }),
  diff: () => api<{ againstVersion: number; changes: Change[] }>("/api/admin/rules/draft/diff"),
  publish: (body: { expectedHash: string; expectedActiveVersion: number; note: string; acknowledgedWarnings: string[] }) =>
    api<RuleVersion>("/api/admin/rules/draft/publish", { method: "POST", body }),
  rollback: (body: { targetVersion: number; expectedActiveVersion: number; note: string }) =>
    api<RuleVersion>("/api/admin/rules/rollback", { method: "POST", body }),
  audit: (before?: number) =>
    api<{ items: AuditItem[]; nextBefore: number | null }>(`/api/admin/audit${before ? `?before=${before}` : ""}`),
};
