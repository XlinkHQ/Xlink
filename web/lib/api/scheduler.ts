import { apiFetch } from "./core";

export type NodeScoreRead = { node_id: string; score: number; reasons: string[] };
export type SchedulerDecisionRead = {
  node_id: string;
  profile_id: string;
  policy: string;
  dry_run: boolean;
  score: number;
  candidates: NodeScoreRead[];
};

export function schedulerPolicies() {
  return apiFetch<string[]>("/scheduler/policies");
}

export function schedulerRun(body: { profile_id: string; policy: string; dry_run: boolean }) {
  return apiFetch<SchedulerDecisionRead>("/scheduler/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
