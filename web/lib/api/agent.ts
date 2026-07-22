import { apiFetch } from "./core";
import { query } from "./internal";

export type NodeMetricSample = { name: string; value: number; observed_at: string };

export function nodeMetricsRecent(nodeId: string, limit = 120) {
  return apiFetch<NodeMetricSample[]>(`/agent/nodes/${nodeId}/metrics/recent${query({ limit })}`);
}

export function nodeLogs(nodeId: string, limit = 100, source?: string) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (source) q.set("source", source);
  return apiFetch<Array<Record<string, unknown>>>(
    `/agent/nodes/${nodeId}/logs/recent?${q.toString()}`,
  );
}

export function issueAgentCommand(nodeId: string, body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>(`/agent/nodes/${nodeId}/commands`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
