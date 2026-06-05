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

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg;
    if (typeof body?.message === "string") return body.message;
  } catch {
    // body is not JSON
  }
  return response.statusText || `Request failed (${response.status})`;
}

const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/register"];

async function rawFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(`/api/v1${path}`, { ...init, headers });
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
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

  if (!response.ok) {
    if (response.status === 401) {
      clearTokens();
      onAuthLost?.();
    }
    throw new ApiError(await readError(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(identifier: string, password: string): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ identifier, password }),
  });
  setTokens(data.tokens);
  return data;
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
  return apiFetch<CursorPage<NodeRead>>(
    `/nodes${query({ size: opts.size ?? 50, cursor: opts.cursor })}`,
  );
}

export function listAssignments(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<AssignmentRead>>(
    `/assignments${query({ size: opts.size ?? 50, cursor: opts.cursor })}`,
  );
}

export function listProfiles(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<ProfileRead>>(
    `/profiles${query({ size: opts.size ?? 50, cursor: opts.cursor })}`,
  );
}

export function listUsers(opts: { size?: number; cursor?: string } = {}) {
  return apiFetch<CursorPage<UserRead>>(
    `/users/cursor${query({ size: opts.size ?? 50, cursor: opts.cursor })}`,
  );
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

export function disableNode(id: string) {
  return apiFetch<NodeRead>(`/nodes/${id}/disable`, { method: "POST" });
}

export function createProfile(body: Record<string, unknown>) {
  return apiFetch<ProfileRead>("/profiles", { method: "POST", body: JSON.stringify(body) });
}

export function updateProfile(id: string, body: Record<string, unknown>) {
  return apiFetch<ProfileRead>(`/profiles/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function disableProfile(id: string) {
  return apiFetch<ProfileRead>(`/profiles/${id}/disable`, { method: "POST" });
}

export function createAssignment(body: Record<string, unknown>) {
  return apiFetch<AssignmentRead>("/assignments", { method: "POST", body: JSON.stringify(body) });
}

export function updateAssignment(id: string, body: Record<string, unknown>) {
  return apiFetch<AssignmentRead>(`/assignments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function disableAssignment(id: string) {
  return apiFetch<AssignmentRead>(`/assignments/${id}/disable`, { method: "POST" });
}

export function deleteAssignment(id: string) {
  return apiFetch<void>(`/assignments/${id}`, { method: "DELETE" });
}

export function updateCurrentUser(body: Record<string, unknown>) {
  return apiFetch<UserRead>("/users/me", { method: "PATCH", body: JSON.stringify(body) });
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

export function assignmentTraffic(assignmentId: string) {
  return apiFetch<{
    assignment_id: string;
    upload_bytes: number;
    download_bytes: number;
    total_bytes: number;
    sample_count: number;
  }>(`/traffic/assignments/${assignmentId}`);
}

export function monitoringSummary() {
  return apiFetch<MetricsSnapshotRead>("/monitoring/summary");
}

export function schedulerPolicies() {
  return apiFetch<string[]>("/scheduler/policies");
}

export function runScheduler(body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/scheduler/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function planFailover(body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/failover/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function executeFailover(plan: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/failover/execute", {
    method: "POST",
    body: JSON.stringify(plan),
  });
}

export function exportBackup(body: Record<string, unknown> = {}) {
  return apiFetch<Record<string, unknown>>("/backup/export", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function restoreBackup(body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/backup/restore", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function gitopsDiff(body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/gitops/diff", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function gitopsCommit(body: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/gitops/commit", {
    method: "POST",
    body: JSON.stringify(body),
  });
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
