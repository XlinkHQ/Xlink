import { apiFetch } from "./core";

export type FailoverPlanItemRead = {
  assignment_id: string;
  source_node_id: string;
  target_node_id: string;
  profile_id: string;
  user_id: string;
};
export type FailoverPlanRead = {
  plan_id: string;
  source_node_id: string;
  dry_run: boolean;
  items: FailoverPlanItemRead[];
};
export type FailoverResultRead = {
  plan_id: string;
  migrated: number;
  skipped: number;
  dry_run: boolean;
};
export function failoverPlan(sourceNodeId: string, dryRun = true) {
  return apiFetch<FailoverPlanRead>("/failover/plan", {
    method: "POST",
    body: JSON.stringify({ source_node_id: sourceNodeId, dry_run: dryRun, policy: "balanced" }),
  });
}
export function failoverExecute(plan: FailoverPlanRead) {
  return apiFetch<FailoverResultRead>("/failover/execute", { method: "POST", body: JSON.stringify(plan) });
}
