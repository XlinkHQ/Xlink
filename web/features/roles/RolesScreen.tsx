"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Modal } from "@/components/ui/modal";
import { Input, Select } from "@/components/ui/input";
import { Field } from "@/shared/parts";
import {
  type AdminRole,
  ApiError,
  createAdminRole,
  deleteAdminRole,
  listAdminRoles,
  type RoleCatalogue,
  type RoleScope,
  roleCatalogue,
  updateAdminRole,
} from "@/lib/api";
import {
  WarpButton,
  WarpEmpty,
  WarpError,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { DgAddUser } from "@/components/console/dg-icons";
import { type MessageKey, useT } from "@/lib/i18n";
import { fromGiB, toGiB } from "@/lib/format";

const SCOPE_KEYS: Record<RoleScope, MessageKey> = {
  0: "roles.scopeNone",
  1: "roles.scopeOwn",
  2: "roles.scopeAll",
};

const BYTE_LIMITS = new Set(["data_limit_min", "data_limit_max"]);

function summary(role: AdminRole): string {
  const actions = Object.values(role.permissions).reduce(
    (n, acts) => n + Object.values(acts).filter((s) => s > 0).length,
    0,
  );
  return String(actions);
}

export function RolesScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-roles"], queryFn: () => listAdminRoles() });
  const catQ = useQuery({ queryKey: ["admin-roles-catalogue"], queryFn: () => roleCatalogue() });
  const roles = (q.data ?? []) as AdminRole[];
  const [editing, setEditing] = useState<AdminRole | "new" | null>(null);

  const reload = () => qc.invalidateQueries({ queryKey: ["admin-roles"] });

  const remove = async (r: AdminRole) => {
    if (
      !(await confirmDialog({
        title: t("roles.deleteTitle", { name: r.name }),
        message: t("roles.deleteMessage"),
        confirmLabel: t("action.delete"),
        danger: true,
      }))
    )
      return;
    try {
      await deleteAdminRole(r.id);
      toast("success", t("roles.deleted"));
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("nav.roles")}</span>
        <div className="right">
          <WarpButton primary onClick={() => catQ.data && setEditing("new")}>
            <DgAddUser size={16} /> {t("roles.add")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("roles.actionsAllowed"), t("roles.description")]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : roles.length === 0 ? (
          <WarpEmpty>{t("roles.empty")}</WarpEmpty>
        ) : (
          roles.map((r) => (
            <WarpRow
              key={r.id}
              onClick={() => setEditing(r)}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setEditing(r) },
                { label: t("action.delete"), icon: "trash", danger: true, onClick: () => remove(r) },
              ]}
              cells={[
                <span className="font-medium">{r.name}</span>,
                <span className="text-fg-muted">{summary(r)}</span>,
                <span className="text-fg-muted">{r.description || "—"}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {editing && catQ.data ? (
        <RoleDialog
          role={editing === "new" ? null : editing}
          catalogue={catQ.data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
    </div>
  );
}

function RoleDialog({
  role,
  catalogue,
  onClose,
  onSaved,
}: {
  role: AdminRole | null;
  catalogue: RoleCatalogue;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [perms, setPerms] = useState<Record<string, Record<string, RoleScope>>>(
    () => structuredClone(role?.permissions ?? {}),
  );
  const [limits, setLimits] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const k of catalogue.limits) {
      const v = role?.limits?.[k];
      out[k] = v == null ? "" : BYTE_LIMITS.has(k) ? String(toGiB(v)) : String(v);
    }
    return out;
  });
  const [busy, setBusy] = useState(false);

  const setScope = (resource: string, action: string, scope: RoleScope) =>
    setPerms((p) => ({ ...p, [resource]: { ...(p[resource] ?? {}), [action]: scope } }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const parsedLimits: Record<string, number | null> = {};
    for (const [k, v] of Object.entries(limits)) {
      const n = Number(v);
      parsedLimits[k] = v.trim() === "" || Number.isNaN(n) ? null : BYTE_LIMITS.has(k) ? fromGiB(n) : n;
    }
    const body = { name: name.trim(), description, permissions: perms, limits: parsedLimits };
    try {
      if (role) await updateAdminRole(role.id, body);
      else await createAdminRole(body);
      toast("success", t("roles.saved"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={role ? t("roles.edit") : t("roles.add")}
      onClose={onClose}
      onSubmit={submit}
      width="sm:w-[40rem]"
      footer={
        <>
          <button type="button" className="warp-tb-button" onClick={onClose} disabled={busy}>
            {t("action.cancel")}
          </button>
          <button
            type="submit"
            className="warp-tb-button warp-tb-button-primary"
            disabled={busy || !name.trim()}
          >
            {busy ? t("common.saving") : t("action.save")}
          </button>
        </>
      }
    >
      <div className="warp-dlg-2col">
        <Field label={t("common.name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="off" />
        </Field>
        <Field label={t("roles.description")} hint={t("common.optional")}>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} autoComplete="off" />
        </Field>
      </div>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">{t("roles.permissions")}</p>
      <p className="text-[11px] text-fg-muted">{t("roles.permissionsHint")}</p>
      {Object.entries(catalogue.resources).map(([resource, actions]) => (
        <div key={resource} className="warp-dlg-2col">
          {actions.map((action) => (
            <Field key={action} label={`${resource}.${action}`}>
              <Select
                value={String(perms[resource]?.[action] ?? 0)}
                onChange={(e) => setScope(resource, action, Number(e.target.value) as RoleScope)}
              >
                {([0, 1, 2] as RoleScope[]).map((s) => (
                  <option key={s} value={s}>
                    {t(SCOPE_KEYS[s])}
                  </option>
                ))}
              </Select>
            </Field>
          ))}
        </div>
      ))}

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">{t("roles.limits")}</p>
      <div className="warp-dlg-2col">
        {catalogue.limits.map((k) => (
          <Field
            key={k}
            label={t(`roles.limit.${k}` as MessageKey)}
            hint={BYTE_LIMITS.has(k) ? "GiB" : undefined}
          >
            <Input
              type="number"
              min="0"
              value={limits[k] ?? ""}
              onChange={(e) => setLimits((l) => ({ ...l, [k]: e.target.value }))}
              placeholder={t("admins.unlimited")}
            />
          </Field>
        ))}
      </div>
    </Modal>
  );
}
