import { apiFetch } from "./core";

export type RoutingRuleRead = {
  id: string;
  name: string;
  match_type: string;
  match_values: string;
  outbound: string;
  enabled: boolean;
  priority: number;
};

export function listRoutingRules() {
  return apiFetch<RoutingRuleRead[]>("/routing/rules");
}

export function createRoutingRule(body: Partial<RoutingRuleRead>) {
  return apiFetch<RoutingRuleRead>("/routing/rules", { method: "POST", body: JSON.stringify(body) });
}

export function updateRoutingRule(id: string, body: Partial<RoutingRuleRead>) {
  return apiFetch<RoutingRuleRead>(`/routing/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRoutingRule(id: string) {
  return apiFetch<void>(`/routing/rules/${id}`, { method: "DELETE" });
}

export type OutboundRead = {
  id: string;
  tag: string;
  type: string;
  settings: Record<string, unknown>;
  enabled: boolean;
};

export function listOutbounds() {
  return apiFetch<OutboundRead[]>("/routing/outbounds");
}

export function createOutbound(body: {
  tag: string;
  type: string;
  settings?: Record<string, unknown>;
  enabled?: boolean;
}) {
  return apiFetch<OutboundRead>("/routing/outbounds", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateOutbound(id: string, body: Partial<Omit<OutboundRead, "id">>) {
  return apiFetch<OutboundRead>(`/routing/outbounds/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteOutbound(id: string) {
  return apiFetch<void>(`/routing/outbounds/${id}`, { method: "DELETE" });
}

export function importOutbound(text: string) {
  return apiFetch<{ type: string; settings: Record<string, unknown> }>(
    "/routing/outbounds/import",
    { method: "POST", body: JSON.stringify({ text }) },
  );
}

export type PingResult = { ok: boolean; latency_ms: number | null; detail: string };

export function pingOutbound(address: string) {
  return apiFetch<PingResult>(
    "/routing/outbounds/ping",
    { method: "POST", body: JSON.stringify({ address }) },
  );
}

export function pingOutboundById(id: string) {
  return apiFetch<PingResult>(`/routing/outbounds/${id}/ping`, { method: "POST" });
}
