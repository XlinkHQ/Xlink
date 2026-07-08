const TOKEN_KEY = "xlink.access_token";
const REFRESH_KEY = "xlink.refresh_token";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  role: string;
};

export type AuthResponse = {
  user: AuthUser;
  tokens: TokenPair;
};

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(tokens: TokenPair): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<string | null> | null = null;
let onAuthLost: (() => void) | null = null;

export function setAuthLostHandler(handler: (() => void) | null): void {
  onAuthLost = handler;
}

async function performRefresh(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const response = await fetch(`/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) {
      clearTokens();
      return null;
    }
    const tokens = (await response.json()) as TokenPair;
    setTokens(tokens);
    return tokens.access_token;
  } catch {
    return null;
  }
}

function refreshTokens(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function readError(response: Response): Promise<{ message: string; code?: string }> {
  try {
    const body = await response.json();
    const code = typeof body?.error?.code === "string" ? body.error.code : undefined;
    if (typeof body?.error?.message === "string") return { message: body.error.message, code };
    if (typeof body?.detail === "string") return { message: body.detail, code };
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      const d = body.detail[0];
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
      return { message: field ? `${field}: ${d.msg}` : d.msg, code };
    }
    if (typeof body?.message === "string") return { message: body.message, code };
  } catch {
    // body is not JSON
  }
  return { message: response.statusText || `Request failed (${response.status})` };
}

const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/register"];

const REQUEST_TIMEOUT_MS = 45000;

async function rawFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  // Abort on timeout so a hung backend call rejects instead of leaving mutation
  // dialogs stuck on their "Adding…"/"Saving…" spinner forever (busy only resets
  // in finally, which never runs if the promise never settles).
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`/api/v1${path}`, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timed out. Please try again.", 408, "timeout");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function ensureAuthed(path: string, init: RequestInit): Promise<Response> {
  let response = await rawFetch(path, init, getToken());

  if (
    response.status === 401 &&
    !NO_REFRESH_PATHS.some((p) => path.startsWith(p)) &&
    getRefreshToken()
  ) {
    const fresh = await refreshTokens();
    if (fresh) {
      response = await rawFetch(path, init, fresh);
    } else {
      clearTokens();
      onAuthLost?.();
      throw new ApiError("Session expired. Please sign in again.", 401);
    }
  }

  return response;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await ensureAuthed(path, init);

  if (!response.ok) {
    if (response.status === 401) {
      clearTokens();
      onAuthLost?.();
    }
    const e = await readError(response);
    throw new ApiError(e.message, response.status, e.code);
  }
  if (response.status === 204) {
    return undefined as unknown as T;
  }
  return (await response.json()) as T;
}

export async function login(
  identifier: string,
  password: string,
  totpCode?: string,
): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ identifier, password, totp_code: totpCode || null }),
  });
  setTokens(data.tokens);
  return data;
}

export function totpEnroll() {
  return apiFetch<{ secret: string; otpauth_uri: string }>("/auth/2fa/enroll", { method: "POST" });
}

export function totpConfirm(code: string) {
  return apiFetch<void>("/auth/2fa/confirm", { method: "POST", body: JSON.stringify({ code }) });
}

export function totpDisable(code: string) {
  return apiFetch<void>("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ code }) });
}

export async function logout(): Promise<void> {
  const refresh = typeof window !== "undefined" ? window.localStorage.getItem(REFRESH_KEY) : null;
  if (refresh) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
      // best-effort; tokens are cleared regardless
    }
  }
  clearTokens();
}

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  size: number;
};

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

export type UserRead = {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  data_limit_bytes: number | null;
  expire_at: string | null;
  data_reset_strategy: string;
  on_hold: boolean;
  expire_strategy: string;
  activation_deadline: string | null;
  device_limit: number | null;
  pinned_node_ids: string[];
  removed: boolean;
  is_sudo: boolean;
  all_groups_access: boolean;
  modify_users_access: boolean;
  totp_enabled: boolean;
  users_data_usage: number;
  owner_id: string | null;
  subscription_url_prefix: string | null;
  admin_user_limit?: number | null;
  admin_traffic_limit_bytes?: number | null;
  sub_updated_at: string | null;
  sub_last_user_agent: string | null;
  created_at: string;
  updated_at: string;
};

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function listNodes(opts: { size?: number; cursor?: string } = {}) {
  // Default matches the backend max_page_size clamp (100) so the requested size
  // isn't a silent lie. Callers that need >100 must page via cursor.
  return apiFetch<CursorPage<NodeRead>>(
    `/nodes${query({ size: opts.size ?? 100, cursor: opts.cursor })}`,
  );
}

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

export function listProfiles(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<ProfileRead>>(
    `/profiles${query({ size: opts.size ?? 100, cursor: opts.cursor })}`,
  );
}

export function listUsers(
  opts: { size?: number; cursor?: string; role?: string; includeRemoved?: boolean; sort?: string } = {},
) {
  return apiFetch<CursorPage<UserRead>>(
    `/users${query({
      size: opts.size ?? 100,
      cursor: opts.cursor,
      role: opts.role,
      include_removed: opts.includeRemoved ? "true" : undefined,
      sort: opts.sort,
    })}`,
  );
}

export function usersTotal(role = "user") {
  return apiFetch<{ items: UserRead[]; meta: { total: number } }>(
    `/users${query({ page: 1, size: 1, role })}`,
  );
}

export type UserTemplateRead = {
  id: string;
  name: string;
  data_limit_bytes: number | null;
  expire_days: number | null;
  data_reset_strategy: string;
  device_limit: number | null;
  username_prefix: string;
  created_at: string;
};

export function listUserTemplates() {
  return apiFetch<UserTemplateRead[]>("/user-templates");
}

export type WarpSettingsRead = {
  warp_enabled: boolean;
  warp_private_key: string;
  warp_public_key: string;
  warp_address: string;
  warp_endpoint: string;
  warp_reserved: string;
};

export function getWarpSettings() {
  return apiFetch<WarpSettingsRead>("/settings/warp");
}

export function updateWarpSettings(body: Partial<WarpSettingsRead>) {
  return apiFetch<WarpSettingsRead>("/settings/warp", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

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

export function createUserTemplate(body: Partial<UserTemplateRead>) {
  return apiFetch<UserTemplateRead>("/user-templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateUserTemplate(id: string, body: Partial<UserTemplateRead>) {
  return apiFetch<UserTemplateRead>(`/user-templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteUserTemplate(id: string) {
  return apiFetch<void>(`/user-templates/${id}`, { method: "DELETE" });
}

export function currentUser() {
  return apiFetch<UserRead>("/users/me");
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

export function createProfile(body: Record<string, unknown>) {
  return apiFetch<ProfileRead>("/profiles", { method: "POST", body: JSON.stringify(body) });
}

export function generateProfileKeys(protocol: string, security: string) {
  return apiFetch<Record<string, string>>("/profiles/keys", {
    method: "POST",
    body: JSON.stringify({ protocol, security }),
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

export type GroupRead = {
  id: string;
  name: string;
  slug: string;
  profile_ids: string[];
  version: number;
  created_at: string;
  updated_at: string;
};

export function listGroups() {
  return apiFetch<GroupRead[]>("/groups");
}

export function createGroup(body: Record<string, unknown>) {
  return apiFetch<GroupRead>("/groups", { method: "POST", body: JSON.stringify(body) });
}

export function updateGroup(id: string, body: Record<string, unknown>) {
  return apiFetch<GroupRead>(`/groups/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteGroup(id: string) {
  return apiFetch<void>(`/groups/${id}`, { method: "DELETE" });
}

export function createAssignment(body: Record<string, unknown>) {
  return apiFetch<AssignmentRead>("/assignments", { method: "POST", body: JSON.stringify(body) });
}



export function deleteAssignment(id: string) {
  return apiFetch<void>(`/assignments/${id}`, { method: "DELETE" });
}


export type TrafficTotals = {
  total_bytes: number;
  upload_bytes: number;
  download_bytes: number;
  record_count: number;
};

export type MetricRead = { name: string; value: number; labels: Record<string, string> };

export type MetricsSnapshotRead = {
  metrics: MetricRead[];
  collected_at: string;
};

export function trafficSummary() {
  return apiFetch<TrafficTotals>("/traffic/summary");
}

export function onlineUsers(windowSeconds = 45) {
  return apiFetch<{ user_ids: string[]; window_seconds: number }>(
    `/traffic/online${query({ window_seconds: windowSeconds })}`,
  );
}


export type SubscriptionRuleResult =
  | "links"
  | "base64"
  | "xray"
  | "singbox"
  | "clash"
  | "clash-meta"
  | "block";

export type SubscriptionRule = {
  pattern: string;
  result: SubscriptionRuleResult;
};

export type SubscriptionSettings = {
  profile_title: string;
  support_link: string;
  update_interval_hours: number;
  active_status_text: string;
  expired_status_text: string;
  limited_status_text: string;
  disabled_status_text: string;
  onhold_status_text: string;
  config_remark: string;
  shuffle_configs: boolean;
  placeholder_if_disabled: boolean;
  placeholder_remark: string;
  custom_page_html: string;
  rules: SubscriptionRule[];
};

export function getSubscriptionSettings() {
  return apiFetch<SubscriptionSettings>("/settings/subscription");
}

export function updateSubscriptionSettings(body: Partial<SubscriptionSettings>) {
  return apiFetch<SubscriptionSettings>("/settings/subscription", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

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

export type NodeMetricSample = { name: string; value: number; observed_at: string };

export function nodeMetricsRecent(nodeId: string, limit = 120) {
  return apiFetch<NodeMetricSample[]>(`/agent/nodes/${nodeId}/metrics/recent${query({ limit })}`);
}

export function getCoreTemplates() {
  return apiFetch<{ templates: Record<string, string> }>("/settings/core");
}

export function updateCoreTemplate(core: string, template: string) {
  return apiFetch<{ templates: Record<string, string> }>("/settings/core", {
    method: "PUT",
    body: JSON.stringify({ core, template }),
  });
}

export function assignmentTraffic(assignmentId: string) {
  return apiFetch<{
    assignment_id: string;
    upload_bytes: number;
    download_bytes: number;
    total_bytes: number;
    sample_count: number;
  }>(`/traffic/assignments/${assignmentId}`);
}

export function nodeTrafficUsage() {
  return apiFetch<{ node_id: string; total_bytes: number }[]>("/traffic/nodes");
}


export function userNodeUsage(userId: string) {
  return apiFetch<{ node_id: string; node_name: string; total_bytes: number }[]>(
    `/traffic/users/${userId}/nodes`,
  );
}

export function userUsageSeries(userId: string, days = 14) {
  return apiFetch<{ date: string; upload_bytes: number; download_bytes: number; total_bytes: number }[]>(
    `/traffic/users/${userId}/usage-series${query({ days })}`,
  );
}

export type UsageSeriesPoint = { ts: string; upload_bytes: number; download_bytes: number; total_bytes: number };

export function nodeUsageSeries(nodeId: string, hours = 24) {
  return apiFetch<UsageSeriesPoint[]>(`/traffic/nodes/${nodeId}/usage-series${query({ hours })}`);
}

export function profileUsageSeries(profileId: string, hours = 24) {
  return apiFetch<UsageSeriesPoint[]>(`/traffic/profiles/${profileId}/usage-series${query({ hours })}`);
}

export function profileUsageTotal(profileId: string) {
  return apiFetch<{ total_bytes: number }>(`/traffic/profiles/${profileId}/usage`);
}


export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type ApiKeyPage = {
  items: ApiKey[];
  total: number;
  next_offset: number | null;
};

export function listApiKeys(opts: { limit?: number; offset?: number } = {}) {
  return apiFetch<ApiKeyPage>(`/api-keys${query({ limit: opts.limit, offset: opts.offset })}`);
}

export function createApiKey(name: string) {
  return apiFetch<ApiKey & { token: string }>("/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(id: string) {
  return apiFetch<void>(`/api-keys/${id}`, { method: "DELETE" });
}

export function enableApiKey(id: string) {
  return apiFetch<ApiKey>(`/api-keys/${id}/enable`, { method: "POST" });
}

export function purgeApiKey(id: string) {
  return apiFetch<void>(`/api-keys/${id}/purge`, { method: "DELETE" });
}

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
  const res = await fetch(`/api/v1/audit/export.csv${qs}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError("Export failed.", res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `xlink-audit-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type SystemStatsRead = {
  cpu_percent: number;
  cpu_cores: number;
  ram_used_bytes: number;
  ram_total_bytes: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  uptime_seconds: number;
  load_avg_1: number;
  load_avg_5: number;
  load_avg_15: number;
  swap_used_bytes: number;
  swap_total_bytes: number;
  process_count: number;
  hostname: string;
  os_name: string;
  os_slug: string;
  kernel: string;
  arch: string;
  ip_address: string;
  ip6_address: string;
  mac_address: string;
  python_version: string;
  app_version: string;
};

export function systemStats() {
  return apiFetch<SystemStatsRead>("/monitoring/system");
}

export function restartPanel() {
  return apiFetch<{ status: string }>("/monitoring/restart", { method: "POST" });
}

export function nodeLogs(nodeId: string, limit = 100, source?: string) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (source) q.set("source", source);
  return apiFetch<Array<Record<string, unknown>>>(
    `/agent/nodes/${nodeId}/logs/recent?${q.toString()}`,
  );
}

export function exportBackup(body: Record<string, unknown> = {}) {
  return apiFetch<Record<string, unknown>>("/backup/export", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function importBackupDb(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/v1/backup/import-db", {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    body: form,
  });
  if (!res.ok) throw new ApiError(await res.text().catch(() => "Import failed"), res.status);
}

export async function downloadBackupDb(): Promise<void> {
  const res = await fetch("/api/v1/backup/export-db", {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(await res.text().catch(() => "Export failed"), res.status);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? "xlink-db.dump";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}




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

export function subscriptionFeed(
  scope: "assignments" | "profiles" | "users",
  id: string,
  format = "text",
) {
  return apiFetch<{ content: string; etag: string; content_hash: string }>(
    `/subscriptions/${scope}/${id}/feed${query({ format })}`,
  );
}

export type ProviderRead = {
  name: string;
  kind: string;
  version: string;
  capabilities: string[];
};

export function listProviders() {
  return apiFetch<ProviderRead[]>("/providers");
}

export function issueAgentCommand(nodeId: string, body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>(`/agent/nodes/${nodeId}/commands`, {
    method: "POST",
    body: JSON.stringify(body),
  });
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




export function createUser(body: {
  username: string;
  password?: string | null;
  email?: string | null;
  full_name?: string | null;
  data_limit_bytes?: number | null;
  expire_at?: string | null;
  data_reset_strategy?: string;
  device_limit?: number | null;
  expire_strategy?: string;
  on_hold?: boolean;
  on_hold_duration_seconds?: number | null;
}) {
  return apiFetch<UserRead>("/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateUser(
  id: string,
  body: {
    full_name?: string | null;
    data_limit_bytes?: number | null;
    expire_at?: string | null;
    data_reset_strategy?: string;
    on_hold?: boolean;
    on_hold_duration_seconds?: number | null;
    activation_deadline?: string | null;
    device_limit?: number | null;
    pinned_node_ids?: string[];
  },
) {
  return apiFetch<UserRead>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function restoreUser(id: string) {
  return apiFetch<UserRead>(`/users/${id}/restore`, { method: "POST" });
}

export function disableUser(id: string) {
  return apiFetch<UserRead>(`/users/${id}/disable`, { method: "POST" });
}

export function enableUser(id: string) {
  return apiFetch<UserRead>(`/users/${id}/enable`, { method: "POST" });
}

export function createAdmin(body: {
  username: string;
  password: string;
  email?: string | null;
  full_name?: string | null;
  is_active?: boolean;
  is_sudo?: boolean;
  all_groups_access?: boolean;
  modify_users_access?: boolean;
  subscription_url_prefix?: string | null;
  admin_user_limit?: number | null;
  admin_traffic_limit_bytes?: number | null;
}) {
  return apiFetch<UserRead>("/users/admins", { method: "POST", body: JSON.stringify(body) });
}

export function updateAdmin(
  id: string,
  body: {
    password?: string;
    email?: string | null;
    is_active?: boolean;
    is_sudo?: boolean;
    all_groups_access?: boolean;
    modify_users_access?: boolean;
    subscription_url_prefix?: string | null;
    admin_user_limit?: number | null;
    admin_traffic_limit_bytes?: number | null;
  },
) {
  return apiFetch<UserRead>(`/users/admins/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function enableAdminUsers(id: string) {
  return apiFetch<{ affected: number }>(`/users/admins/${id}/enable-users`, { method: "POST" });
}

export function disableAdminUsers(id: string) {
  return apiFetch<{ affected: number }>(`/users/admins/${id}/disable-users`, { method: "POST" });
}

export type AdminUsageRead = {
  users_count: number;
  users_limit: number | null;
  traffic_allocated_bytes: number;
  traffic_used_bytes: number;
  traffic_budget_bytes: number | null;
};

export function adminUsage(id: string) {
  return apiFetch<AdminUsageRead>(`/users/admins/${id}/usage`);
}

export function revokeSubscription(id: string) {
  return apiFetch<UserRead>(`/users/${id}/revoke-subscription`, { method: "POST" });
}


export function userSubscriptionUrl(userId: string) {
  return apiFetch<{ token: string; subscription_url: string }>(
    `/subscriptions/users/${userId}/token`,
  );
}

export function resetUserUsage(userId: string) {
  return apiFetch<{ reset_assignments: number }>(`/traffic/users/${userId}/reset`, {
    method: "POST",
  });
}

export type UserUsage = {
  user_id: string;
  used_bytes: number;
  limit_bytes: number;
  unlimited: boolean;
};

export async function downloadUsersCsv(): Promise<void> {
  const res = await fetch(`/api/v1/users/export.csv`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError("Export failed.", res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `xlink-users-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function usersUsage(userIds: string[]) {
  return apiFetch<UserUsage[]>("/traffic/users/usage", {
    method: "POST",
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export function usersLastSeen(userIds: string[]) {
  return apiFetch<{ user_id: string; last_seen_at: string }[]>("/traffic/users/last-seen", {
    method: "POST",
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export type UserDevice = {
  id: string;
  device_hash: string;
  user_agent: string;
  first_seen_at: string;
  last_seen_at: string;
};

export function listUserDevices(userId: string) {
  return apiFetch<UserDevice[]>(`/users/${userId}/devices`);
}

export function resetUserDevices(userId: string) {
  return apiFetch<void>(`/users/${userId}/devices`, { method: "DELETE" });
}

export function promoteUser(id: string) {
  return apiFetch<UserRead>(`/users/${id}/promote`, { method: "POST" });
}

export function demoteUser(id: string) {
  return apiFetch<UserRead>(`/users/${id}/demote`, { method: "POST" });
}

export type BulkAction =
  | "enable"
  | "disable"
  | "delete"
  | "reset_usage"
  | "set_data_limit"
  | "set_expiry"
  | "extend_expiry"
  | "set_reset_strategy";

export function bulkUserAction(
  action: BulkAction,
  userIds: string[],
  params?: {
    data_limit_bytes?: number | null;
    expire_at?: string | null;
    extend_days?: number;
    data_reset_strategy?: string;
  },
) {
  return apiFetch<{ ok: number; failed: number }>("/users/bulk", {
    method: "POST",
    body: JSON.stringify({ action, user_ids: userIds, ...params }),
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

export type RetentionRead = { enabled: boolean; retention_days: number; interval_seconds: number };
export function trafficRetention() {
  return apiFetch<RetentionRead>("/traffic/retention");
}
export function trafficCleanup(retentionDays: number) {
  return apiFetch<{ deleted: number; retention_days: number }>("/traffic/cleanup", {
    method: "POST",
    body: JSON.stringify({ retention_days: retentionDays }),
  });
}

export function deleteUser(id: string) {
  return apiFetch<void>(`/users/${id}`, { method: "DELETE" });
}

export function monitoringMetrics() {
  return apiFetch<MetricsSnapshotRead>("/monitoring/metrics");
}

export type CertificateEntryRead = {
  profile_id: string;
  profile_name: string;
  core: string;
  protocol: string;
  security: string;
  server_name: string | null;
  node_id: string;
  node_name: string;
  node_host: string;
  status: string;
};

export type CertificateNodeGroupRead = {
  node_id: string;
  node_name: string;
  node_host: string;
  secure_count: number;
  insecure_count: number;
  entries: CertificateEntryRead[];
};

export type CertificatesRead = {
  total: number;
  secure: number;
  reality: number;
  insecure: number;
  nodes: CertificateNodeGroupRead[];
};


export type ManagedCertificate = {
  id: string;
  domain: string;
  source: string;
  status: string;
  issuer: string;
  not_before: string | null;
  not_after: string | null;
  last_error: string;
  renewed_at: string | null;
  created_at: string;
};

export function listCertificates() {
  return apiFetch<ManagedCertificate[]>("/certificates");
}

export function importCertificate(body: { domain: string; cert_pem: string; key_pem: string }) {
  return apiFetch<ManagedCertificate>("/certificates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function requestAcmeCertificate(domain: string) {
  return apiFetch<ManagedCertificate>("/certificates/acme", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export function deleteCertificate(id: string) {
  return apiFetch<void>(`/certificates/${id}`, { method: "DELETE" });
}

export type NotificationSettingsRead = {
  notify_enabled: boolean;
  notify_expiring_days: number;
  notify_usage_percent: number;
  notify_node_down: boolean;
  webhook_address: string;
  discord_webhook_url: string;
  telegram_bot_token: string;
  telegram_chat_ids: string;
};

export function getNotificationSettings() {
  return apiFetch<NotificationSettingsRead>("/settings/notifications");
}

export function updateNotificationSettings(body: Partial<NotificationSettingsRead>) {
  return apiFetch<NotificationSettingsRead>("/settings/notifications", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function testNotificationSettings(body: Partial<NotificationSettingsRead>) {
  return apiFetch<{ status: string }>("/settings/notifications/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}


export function logoutAll() {
  return apiFetch<void>("/auth/logout-all", { method: "POST" });
}
