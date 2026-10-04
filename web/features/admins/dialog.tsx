"use client";

import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import {
  type AdminRole,
  adminUsage,
  ApiError,
  listAdminRoles,
  createAdmin,
  type GroupRead,
  listGroups,
  type UserRead,
  updateAdmin,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { bytes, fromGiB, toGiB } from "@/lib/format";
import { Field } from "@/shared/parts";
import { type TranslateFn, useT } from "@/lib/i18n";

const PW_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ";
const PW_LOWER = "abcdefghijkmnopqrstuvwxyz";
const PW_DIGIT = "23456789";
const PW_SPECIAL = "!@#$%^&*";

function passwordStrong(p: string): boolean {
  const u = (p.match(/[A-Z]/g) || []).length;
  const l = (p.match(/[a-z]/g) || []).length;
  const d = (p.match(/[0-9]/g) || []).length;
  const s = (p.match(/[^A-Za-z0-9]/g) || []).length;
  return p.length >= 12 && u >= 2 && l >= 2 && d >= 2 && s >= 1;
}

function randomPassword(len = 18): string {
  const all = PW_UPPER + PW_LOWER + PW_DIGIT + PW_SPECIAL;
  const pick = (set: string, n: number): string[] => {
    const arr = new Uint32Array(n);
    crypto.getRandomValues(arr);
    return Array.from(arr, (x) => set[x % set.length]);
  };
  const forced = [
    ...pick(PW_UPPER, 2),
    ...pick(PW_LOWER, 2),
    ...pick(PW_DIGIT, 2),
    ...pick(PW_SPECIAL, 1),
  ];
  const rest = pick(all, Math.max(0, len - forced.length));
  const out = [...forced, ...rest];
  const order = new Uint32Array(out.length);
  crypto.getRandomValues(order);
  for (let i = out.length - 1; i > 0; i--) {
    const j = order[i] % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out.join("");
}

export function AdminDialog({
  admin,
  onClose,
  onSaved,
}: {
  admin?: UserRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const editing = !!admin;
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const groups = (groupsQ.data ?? []) as GroupRead[];
  const rolesQ = useQuery({ queryKey: ["admin-roles"], queryFn: () => listAdminRoles() });
  const roles = (rolesQ.data ?? []) as AdminRole[];
  const [roleId, setRoleId] = useState(admin?.admin_role_id ?? "");
  const usageQ = useQuery({
    queryKey: ["admin-usage", admin?.id],
    queryFn: () => adminUsage(admin!.id),
    enabled: !!admin && !admin.is_sudo,
  });
  const usage = usageQ.data;

  const [username, setUsername] = useState(admin?.username ?? "");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [subPrefix, setSubPrefix] = useState(admin?.subscription_url_prefix ?? "");
  const [enabled, setEnabled] = useState(admin?.is_active ?? true);
  const [canModify, setCanModify] = useState(admin?.modify_users_access ?? true);
  const [sudo, setSudo] = useState(admin?.is_sudo ?? false);
  const [allServices, setAllServices] = useState(admin?.all_groups_access ?? true);
  const [userLimit, setUserLimit] = useState(admin?.admin_user_limit?.toString() ?? "");
  const [trafficLimitGib, setTrafficLimitGib] = useState(
    admin?.admin_traffic_limit_bytes ? toGiB(admin.admin_traffic_limit_bytes).toString() : "",
  );
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const shared = {
        is_active: enabled,
        is_sudo: sudo,
        modify_users_access: sudo ? true : canModify,
        all_groups_access: allServices,
        subscription_url_prefix: subPrefix.trim() || null,
        admin_user_limit:
          sudo || !userLimit || Number.isNaN(Number(userLimit)) ? null : Number(userLimit),
        admin_traffic_limit_bytes:
          sudo || !trafficLimitGib || Number.isNaN(Number(trafficLimitGib))
            ? null
            : fromGiB(Number(trafficLimitGib)),
      };
      const admin_role_id = sudo || !roleId ? null : roleId;
      if (editing && admin) {
        await updateAdmin(admin.id, {
          ...(password ? { password } : {}),
          ...shared,
          admin_role_id,
        });
        toast("success", t("admins.updatedToast", { username: admin.username }));
      } else {
        const created = await createAdmin({ username: username.trim(), password, ...shared });
        // The role is assigned on update only (sudo-gated on the API side).
        if (admin_role_id) await updateAdmin(created.id, { admin_role_id });
        toast("success", t("admins.createdToast", { username: username.trim() }));
      }
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const usernameValid = editing || /^[a-zA-Z0-9_]{3,64}$/.test(username.trim());
  const passwordValid = editing ? password.length === 0 || passwordStrong(password) : passwordStrong(password);

  return (
    <Modal
      title={editing ? t("admins.editAdmin") : t("admins.createAdmin")}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !usernameValid || !passwordValid}
          >
            {busy ? t("common.saving") : editing ? t("action.save") : t("action.create")}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">{t("admins.loginInformation")}</p>
      <Field label={t("admins.username")} hint={t("admins.usernameHint")}>
        <Input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus={!editing}
          disabled={editing}
          autoComplete="off"
        />
      </Field>
      <Field label={t("admins.password")} hint={editing ? t("admins.leaveBlankToKeep") : t("admins.passwordHint")}>
        <div className="warp-dlg-pw">
          <input
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder={editing ? t("admins.leaveBlankToKeep") : ""}
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            title={show ? t("admins.hide") : t("admins.show")}
            aria-label={show ? t("admins.hidePassword") : t("admins.showPassword")}
            className="warp-dlg-pw-icon"
          >
            {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
          </button>
          <button
            type="button"
            title={t("admins.generatePassword")}
            aria-label={t("admins.generatePassword")}
            className="warp-dlg-pw-icon"
            onClick={() => {
              setPassword(randomPassword());
              setShow(true);
            }}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </Field>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">{t("admins.accountDetails")}</p>
      <Field label={t("admins.subscriptionUrlPrefix")} hint={t("common.optional")}>
        <Input
          value={subPrefix}
          onChange={(e) => setSubPrefix(e.target.value)}
          placeholder="https://sub.example.com"
          autoComplete="off"
        />
      </Field>
      {!sudo ? (
        <div className="warp-dlg-2col">
          <Field label={t("admins.maxUsers")} hint={t("admins.maxUsersHint")}>
            <Input
              type="number"
              min="0"
              value={userLimit}
              onChange={(e) => setUserLimit(e.target.value)}
              placeholder={t("admins.unlimited")}
            />
          </Field>
          <Field label={t("admins.trafficBudget")} hint={t("admins.trafficBudgetHint")}>
            <Input
              type="number"
              min="0"
              step="0.1"
              value={trafficLimitGib}
              onChange={(e) => setTrafficLimitGib(e.target.value)}
              placeholder={t("admins.unlimited")}
            />
          </Field>
        </div>
      ) : null}
      {!sudo && editing && usage ? (
        <div className="warp-reseller-usage">
          <div className="warp-ru-row">
            <span className="warp-ru-label">{t("admins.users")}</span>
            <span className="warp-ru-value">
              {usage.users_count}
              {usage.users_limit != null ? ` / ${usage.users_limit}` : " / ∞"}
            </span>
          </div>
          <div className="warp-ru-row">
            <span className="warp-ru-label">{t("admins.trafficAllocated")}</span>
            <span className="warp-ru-value">
              {bytes(usage.traffic_allocated_bytes)}
              {usage.traffic_budget_bytes != null ? ` / ${bytes(usage.traffic_budget_bytes)}` : " / ∞"}
            </span>
          </div>
          <div className="warp-ru-row">
            <span className="warp-ru-label">{t("admins.trafficUsed")}</span>
            <span className="warp-ru-value">{bytes(usage.traffic_used_bytes)}</span>
          </div>
        </div>
      ) : null}

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">{t("admins.permissions")}</p>
      <SwitchRow
        label={t("common.enabled")}
        hint={t("admins.enabledHint")}
        checked={enabled}
        onChange={setEnabled}
      />
      <SwitchRow
        label={t("admins.sudoPrivilege")}
        hint={t("admins.sudoPrivilegeHint")}
        checked={sudo}
        onChange={setSudo}
      />
      {!sudo ? (
        <SwitchRow label={t("admins.modifyUsersAccess")} checked={canModify} onChange={setCanModify} />
      ) : null}
      {!sudo ? (
        <Field label={t("roles.role")} hint={t("roles.roleHint")}>
          <Select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">{t("roles.none")}</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      <SwitchRow label={t("admins.allServicesAccess")} checked={allServices} onChange={setAllServices} />

      {!allServices ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">{t("admins.access")}</p>
          <Field label={t("admins.services")} hint={t("admins.servicesAvailable", { count: groups.length })}>
            <div className="warp-dlg-chipbox">
              {groups.length === 0 ? (
                <span className="text-[11px] text-fg-muted">{t("admins.noServices")}</span>
              ) : (
                groups.map((g) => (
                  <span key={g.id} className="warp-pin-chip">
                    {g.name}
                  </span>
                ))
              )}
            </div>
          </Field>
        </>
      ) : null}
    </Modal>
  );
}

function SwitchRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex flex-col text-sm font-medium text-fg">
        {label}
        {hint ? <span className="text-[11px] font-normal text-fg-muted">{hint}</span> : null}
      </span>
      <Switch checked={checked} onChange={onChange} />
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors",
        checked ? "bg-primary" : "bg-line",
      )}
    >
      <span className={cn("inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform", checked ? "translate-x-4" : "translate-x-0.5")} />
    </button>
  );
}
