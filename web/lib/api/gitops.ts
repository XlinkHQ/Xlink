import { apiFetch } from "./core";
import { query } from "./internal";

export type GitOpsRecordRead = {
  id: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  actor: string | null;
  message: string | null;
  snapshot: Record<string, unknown>;
  diff: { added?: Record<string, unknown>; changed?: Record<string, unknown>; removed?: Record<string, unknown> };
  created_at: string;
};
export function gitopsRecords(limit = 100) {
  return apiFetch<GitOpsRecordRead[]>(`/gitops/records${query({ limit })}`);
}
