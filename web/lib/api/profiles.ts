import { apiFetch, type CursorPage } from "./core";
import { query } from "./internal";

export type ProfileRead = {
  id: string;
  name: string;
  slug: string;
  provider_kind: string;
  node_id: string;
  protocol: string;
  settings: Record<string, unknown>;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

export function listProfiles(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<ProfileRead>>(
    `/profiles${query({ size: opts.size ?? 100, cursor: opts.cursor })}`,
  );
}

export function createProfile(body: Record<string, unknown>) {
  return apiFetch<ProfileRead>("/profiles", { method: "POST", body: JSON.stringify(body) });
}

export function generateProfileKeys(protocol: string, security: string, amnezia = false) {
  return apiFetch<Record<string, string>>("/profiles/keys", {
    method: "POST",
    body: JSON.stringify({ protocol, security, amnezia }),
  });
}

export function updateProfile(id: string, body: Record<string, unknown>) {
  return apiFetch<ProfileRead>(`/profiles/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function disableProfile(id: string) {
  return apiFetch<ProfileRead>(`/profiles/${id}/disable`, { method: "POST" });
}

export function deleteProfile(id: string) {
  return apiFetch<void>(`/profiles/${id}`, { method: "DELETE" });
}

export type InboundHostRead = {
  id: string;
  profile_id: string | null;
  remark: string;
  address: string | null;
  port: number | null;
  sni: string | null;
  host: string | null;
  path: string | null;
  alpn: string | null;
  fingerprint: string | null;
  security: string | null;
  network: string | null;
  fragment: string | null;
  noise: string | null;
  mux: boolean;
  allow_insecure: boolean;
  weight: number;
  is_universal: boolean;
  is_disabled: boolean;
  chain_target_id: string | null;
  created_at: string;
  updated_at: string;
};

export function listInboundHosts(profileId?: string) {
  return apiFetch<InboundHostRead[]>(`/inbound-hosts${query({ profile_id: profileId })}`);
}

export function createInboundHost(body: Record<string, unknown>) {
  return apiFetch<InboundHostRead>("/inbound-hosts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateInboundHost(id: string, body: Record<string, unknown>) {
  return apiFetch<InboundHostRead>(`/inbound-hosts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteInboundHost(id: string) {
  return apiFetch<void>(`/inbound-hosts/${id}`, { method: "DELETE" });
}

export type RealityScanItem = {
  target: string;
  port: number;
  ip: string | null;
  ok: boolean;
  tls13: boolean;
  h2: boolean;
  x25519: boolean | null;
  cert_valid: boolean;
  latency_ms: number | null;
  issuer: string | null;
  problems: string[];
};

export function scanRealityTargets(targets: string[]) {
  return apiFetch<RealityScanItem[]>("/reality/scan", {
    method: "POST",
    body: JSON.stringify({ targets }),
  });
}

export function scanRealityFromNode(nodeId: string, targets: string[]) {
  return apiFetch<{ command_id: string }>(`/reality/scan/node/${nodeId}`, {
    method: "POST",
    body: JSON.stringify({ targets }),
  });
}

export function realityNodeScanStatus(commandId: string) {
  return apiFetch<{ status: string; results: RealityScanItem[]; error: string | null }>(
    `/reality/scan/commands/${commandId}`,
  );
}

/** Queue a scan on the node and wait for the agent to report (it picks
 * commands up on its next poll). */
export async function scanRealityOnNode(
  nodeId: string,
  targets: string[],
  { timeoutMs = 90_000, intervalMs = 2_000 } = {},
): Promise<RealityScanItem[]> {
  const { command_id } = await scanRealityFromNode(nodeId, targets);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const s = await realityNodeScanStatus(command_id);
    if (s.status === "succeeded") return s.results;
    if (s.status === "failed" || s.status === "expired" || s.status === "cancelled") {
      throw new Error(s.error || s.status);
    }
  }
  throw new Error("timeout");
}
