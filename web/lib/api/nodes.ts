import { apiFetch, type CursorPage } from "./core";
import { query } from "./internal";

export type NodeRead = {
  id: string;
  name: string;
  slug: string;
  host: string;
  port: number;
  status: string;
  last_seen_at: string | null;
  max_users: number;
  current_users: number;
  usage_coefficient: number;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
};

export function listNodes(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<NodeRead>>(
    `/nodes${query({ size: opts.size ?? 100, cursor: opts.cursor })}`,
  );
}

export function createNode(body: Record<string, unknown>) {
  return apiFetch<NodeRead>("/nodes", { method: "POST", body: JSON.stringify(body) });
}

export function updateNode(id: string, body: Record<string, unknown>) {
  return apiFetch<NodeRead>(`/nodes/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteNode(id: string) {
  return apiFetch<void>(`/nodes/${id}`, { method: "DELETE" });
}

export function disableNode(id: string) {
  return apiFetch<NodeRead>(`/nodes/${id}/disable`, { method: "POST" });
}

export function restartNodeCore(id: string) {
  return apiFetch<NodeRead>(`/nodes/${id}/restart-core`, { method: "POST" });
}

export function setNodeStatus(id: string, status: string) {
  return apiFetch<NodeRead>(`/nodes/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export function xrayVersions() {
  return apiFetch<string[]>(`/nodes/xray-versions`);
}

export function provisionAgentToken(id: string) {
  return apiFetch<{ node_id: string; agent_token: string }>(`/nodes/${id}/agent-token`, {
    method: "POST",
  });
}

export type CoreHealthRead = {
  provider_name: string;
  status: string;
  latency_ms: number | null;
  detail: string | null;
  checked_at: string;
};
export function nodeCores(nodeId: string) {
  return apiFetch<CoreHealthRead[]>(`/nodes/${nodeId}/cores`);
}
