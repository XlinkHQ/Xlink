"use client";

import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import {
  adminUsage,
  ApiError,
  createAdmin,
  type GroupRead,
  listGroups,
  type UserRead,
  updateAdmin,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { bytes } from "@/lib/format";
import { Field } from "../parts";

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
  const editing = !!admin;
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const groups = (groupsQ.data ?? []) as GroupRead[];
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
  // New admins default to NON-sudo (safe default); editing keeps the real value.
  const [sudo, setSudo] = useState(admin?.is_sudo ?? false);
  const [allServices, setAllServices] = useState(admin?.all_groups_access ?? true);
  const [userLimit, setUserLimit] = useState(admin?.admin_user_limit?.toString() ?? "");
  const [trafficLimitGib, setTrafficLimitGib] = useState(
    admin?.admin_traffic_limit_bytes ? (admin.admin_traffic_limit_bytes / 1024 ** 3).toString() : "",
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
            : Math.round(Number(trafficLimitGib) * 1024 ** 3),
      };
      if (editing && admin) {
        await updateAdmin(admin.id, { ...(password ? { password } : {}), ...shared });
        toast("success", `Admin “${admin.username}” updated.`);
      } else {
        await createAdmin({ username: username.trim(), password, ...shared });
        toast("success", `Admin “${username.trim()}” created.`);
      }
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  const usernameValid = editing || /^[a-zA-Z0-9_]{3,64}$/.test(username.trim());
  const passwordValid = editing ? password.length === 0 || passwordStrong(password) : passwordStrong(password);

  return (
    <Modal
      title={editing ? "Edit Admin" : "Create Admin"}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !usernameValid || !passwordValid}
          >
            {busy ? "Saving…" : editing ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">Login information</p>
      <Field label="Username" hint="3–64 chars · letters, numbers, _">
        <Input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus={!editing}
          disabled={editing}
          autoComplete="off"
        />
      </Field>
      <Field label="Password" hint={editing ? "Leave blank to keep" : "12+ characters"}>
        <div className="warp-dlg-pw">
          <input
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder={editing ? "Leave blank to keep" : ""}
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            title={show ? "Hide" : "Show"}
            className="warp-dlg-pw-icon"
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
          <button
            type="button"
            title="Generate password"
            className="warp-dlg-pw-icon"
            onClick={() => {
              setPassword(randomPassword());
              setShow(true);
            }}
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </Field>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">Account details</p>
      <Field label="Subscription URL prefix" hint="Optional">
        <Input
          value={subPrefix}
          onChange={(e) => setSubPrefix(e.target.value)}
          placeholder="https://sub.example.com"
          autoComplete="off"
        />
      </Field>
      {!sudo ? (
        <div className="warp-dlg-2col">
          <Field label="Max users" hint="Reseller cap · blank = unlimited">
            <Input
              type="number"
              min="0"
              value={userLimit}
              onChange={(e) => setUserLimit(e.target.value)}
              placeholder="unlimited"
            />
          </Field>
          <Field label="Traffic budget (GiB)" hint="Total across their users">
            <Input
              type="number"
              min="0"
              step="0.1"
              value={trafficLimitGib}
              onChange={(e) => setTrafficLimitGib(e.target.value)}
              placeholder="unlimited"
            />
          </Field>
        </div>
      ) : null}
      {!sudo && editing && usage ? (
        <div className="warp-reseller-usage">
          <div className="warp-ru-row">
            <span className="warp-ru-label">Users</span>
            <span className="warp-ru-value">
              {usage.users_count}
              {usage.users_limit != null ? ` / ${usage.users_limit}` : " / ∞"}
            </span>
          </div>
          <div className="warp-ru-row">
            <span className="warp-ru-label">Traffic allocated</span>
            <span className="warp-ru-value">
              {bytes(usage.traffic_allocated_bytes)}
              {usage.traffic_budget_bytes != null ? ` / ${bytes(usage.traffic_budget_bytes)}` : " / ∞"}
            </span>
          </div>
          <div className="warp-ru-row">
            <span className="warp-ru-label">Traffic used</span>
            <span className="warp-ru-value">{bytes(usage.traffic_used_bytes)}</span>
          </div>
        </div>
      ) : null}

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">Permissions</p>
      <SwitchRow
        label="Enabled"
        hint="Admin can sign in."
        checked={enabled}
        onChange={setEnabled}
      />
      <SwitchRow
        label="Sudo privilege"
        hint="Full panel access."
        checked={sudo}
        onChange={setSudo}
      />
      {!sudo ? (
        <SwitchRow label="Modify users access" checked={canModify} onChange={setCanModify} />
      ) : null}
      <SwitchRow label="All services access" checked={allServices} onChange={setAllServices} />

      {!allServices ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">Access</p>
          <Field label="Services" hint={`${groups.length} available`}>
            <div className="warp-dlg-chipbox">
              {groups.length === 0 ? (
                <span className="text-[11px] text-fg-muted">No services yet.</span>
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
