import { ApiError, apiFetch, apiFetchRaw, type CursorPage } from "./core";
import { fetchAllPages, query } from "./internal";

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
  on_hold_duration_seconds: number | null;
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

export function listAllUsers(opts: { role?: string; includeRemoved?: boolean } = {}) {
  return fetchAllPages(
    (cursor) => listUsers({ ...opts, size: 100, cursor }),
    "listAllUsers",
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

export function createUserTemplate(body: Partial<UserTemplateRead>) {
  return apiFetch<UserTemplateRead>("/user-templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteUserTemplate(id: string) {
  return apiFetch<void>(`/user-templates/${id}`, { method: "DELETE" });
}

export function currentUser() {
  return apiFetch<UserRead>("/users/me");
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

export async function downloadUsersCsv(): Promise<void> {
  const res = await apiFetchRaw(`/users/export.csv`);
  if (!res.ok) throw new ApiError("Export failed.", res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `xlink-users-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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

export function deleteUser(id: string) {
  return apiFetch<void>(`/users/${id}`, { method: "DELETE" });
}
