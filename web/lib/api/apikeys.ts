import { apiFetch } from "./core";
import { query } from "./internal";

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
