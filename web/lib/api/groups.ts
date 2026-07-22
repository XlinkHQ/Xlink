import { apiFetch } from "./core";

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
