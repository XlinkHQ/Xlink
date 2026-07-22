import { ApiError, apiFetch, apiFetchRaw } from "./core";
import { query } from "./internal";

export type AuditEntry = {
  id: string;
  actor_id: string | null;
  actor_username: string;
  method: string;
  path: string;
  action: string;
  status_code: number;
  ip_address: string;
  created_at: string;
};

export function listAudit(
  opts: { limit?: number; actor?: string; dateFrom?: string; dateTo?: string } = {},
) {
  return apiFetch<AuditEntry[]>(
    `/audit${query({
      limit: opts.limit,
      actor: opts.actor,
      date_from: opts.dateFrom,
      date_to: opts.dateTo,
    })}`,
  );
}

export async function downloadAuditCsv(
  opts: { actor?: string; dateFrom?: string; dateTo?: string } = {},
): Promise<void> {
  const qs = query({ actor: opts.actor, date_from: opts.dateFrom, date_to: opts.dateTo });
  const res = await apiFetchRaw(`/audit/export.csv${qs}`);
  if (!res.ok) throw new ApiError("Export failed.", res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `xlink-audit-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
