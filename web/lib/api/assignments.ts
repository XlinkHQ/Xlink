import { apiFetch, type CursorPage } from "./core";
import { fetchAllPages, query } from "./internal";

export type AssignmentRead = {
  id: string;
  user_id: string;
  profile_id: string;
  node_id: string;
  provider_kind: string;
  provider_client_id: string | null;
  status: string;
  expires_at: string | null;
  traffic_limit_bytes: number | null;
  used_bytes: number;
  version: number;
  created_at: string;
  updated_at: string;
};

export function listAssignments(
  opts: { size?: number; cursor?: string; userId?: string; status?: string } = {},
) {
  return apiFetch<CursorPage<AssignmentRead>>(
    `/assignments${query({
      size: opts.size ?? 100,
      cursor: opts.cursor,
      user_id: opts.userId,
      status_filter: opts.status,
    })}`,
  );
}

export function listAllAssignments(opts: { userId?: string; status?: string } = {}) {
  return fetchAllPages(
    (cursor) => listAssignments({ ...opts, size: 100, cursor }),
    "listAllAssignments",
  );
}

export function createAssignment(body: Record<string, unknown>) {
  return apiFetch<AssignmentRead>("/assignments", { method: "POST", body: JSON.stringify(body) });
}

export function deleteAssignment(id: string) {
  return apiFetch<void>(`/assignments/${id}`, { method: "DELETE" });
}
