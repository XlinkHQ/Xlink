import { apiFetch } from "./core";

export type RoleScope = 0 | 1 | 2;

export type AdminRole = {
  id: string;
  name: string;
  description: string;
  permissions: Record<string, Record<string, RoleScope>>;
  limits: Record<string, number | null>;
};

export type RoleCatalogue = {
  resources: Record<string, string[]>;
  limits: string[];
  scopes: Record<string, number>;
};

export type AdminRoleInput = Omit<AdminRole, "id">;

export function roleCatalogue() {
  return apiFetch<RoleCatalogue>("/admin-roles/catalogue");
}

export function listAdminRoles() {
  return apiFetch<AdminRole[]>("/admin-roles");
}

export function createAdminRole(body: AdminRoleInput) {
  return apiFetch<AdminRole>("/admin-roles", { method: "POST", body: JSON.stringify(body) });
}

export function updateAdminRole(id: string, body: Partial<AdminRoleInput>) {
  return apiFetch<AdminRole>(`/admin-roles/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteAdminRole(id: string) {
  return apiFetch<void>(`/admin-roles/${id}`, { method: "DELETE" });
}

export type TemplateFormat = "clash" | "mihomo" | "singbox";

export type ClientTemplate = {
  id: string;
  name: string;
  format: TemplateFormat;
  content: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export function listClientTemplates() {
  return apiFetch<ClientTemplate[]>("/client-templates");
}

export function createClientTemplate(body: {
  name: string;
  format: TemplateFormat;
  content: string;
  is_default: boolean;
}) {
  return apiFetch<ClientTemplate>("/client-templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateClientTemplate(
  id: string,
  body: { name?: string; content?: string; is_default?: boolean },
) {
  return apiFetch<ClientTemplate>(`/client-templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteClientTemplate(id: string) {
  return apiFetch<void>(`/client-templates/${id}`, { method: "DELETE" });
}
