"use client";

import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createAdmin,
  type GroupRead,
  listGroups,
  type UserRead,
  updateAdmin,
} from "@/lib/api";
import { cn } from "@/lib/cn";

function randomPassword(len = 18): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*";
  const arr = new Uint32Array(len);
  crypto.getRandomValues(arr);
  return Array.from(arr, (n) => chars[n % chars.length]).join("");
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

  const [username, setUsername] = useState(admin?.username ?? "");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [subPrefix, setSubPrefix] = useState(admin?.subscription_url_prefix ?? "");
  const [enabled, setEnabled] = useState(admin?.is_active ?? true);
  const [canModify, setCanModify] = useState(admin?.modify_users_access ?? true);
  const [sudo, setSudo] = useState(admin?.is_sudo ?? true);
  const [allServices, setAllServices] = useState(admin?.all_groups_access ?? true);
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
  const passwordValid = editing ? password.length === 0 || password.length >= 12 : password.length >= 12;

  return (
    <div className="warp-dlg-overlay" onMouseDown={onClose}>
      <form className="warp-dlg" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="warp-dlg-header">
          <span className="warp-dlg-grab" />
          <p>{editing ? "Edit Admin" : "Create Admin"}</p>
        </div>

        <div className="warp-dlg-body">
          <div className="warp-dlg-field">
            <label>Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus={!editing}
              disabled={editing}
              autoComplete="off"
            />
          </div>

          <div className="warp-dlg-field">
            <label>Password</label>
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
          </div>

          <div className="warp-dlg-field">
            <label>Subscription URL prefix</label>
            <input
              value={subPrefix}
              onChange={(e) => setSubPrefix(e.target.value)}
              placeholder="https://sub.example.com"
              autoComplete="off"
            />
          </div>

          <div className="warp-dlg-field">
            <label>Enabled<span className="warp-dlg-hint">Admin can sign in.</span></label>
            <Switch checked={enabled} onChange={setEnabled} />
          </div>
          <div className="warp-dlg-field">
            <label>Sudo privilege<span className="warp-dlg-hint">Full panel access.</span></label>
            <Switch checked={sudo} onChange={setSudo} />
          </div>
          {!sudo ? (
            <div className="warp-dlg-field">
              <label>Modify users access</label>
              <Switch checked={canModify} onChange={setCanModify} />
            </div>
          ) : null}
          <div className="warp-dlg-field">
            <label>All services access</label>
            <Switch checked={allServices} onChange={setAllServices} />
          </div>

          {!allServices ? (
            <div className="warp-dlg-field" style={{ alignItems: "flex-start" }}>
              <label>Services<span className="warp-dlg-hint">{groups.length} available</span></label>
              <div className="warp-dlg-picker">
                <div className="warp-dlg-picker-list" style={{ marginTop: 0 }}>
                  {groups.length === 0 ? (
                    <p className="px-2 py-1.5 text-xs text-fg-muted">No services yet.</p>
                  ) : (
                    groups.map((g) => (
                      <div key={g.id} className="warp-dlg-picker-item">
                        <span className="truncate">{g.name}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="warp-dlg-footer">
          <button type="button" className="warp-tb-button" onClick={onClose}>Cancel</button>
          <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy || !usernameValid || !passwordValid}>
            {busy ? "Saving…" : editing ? "Save" : "Create"}
          </button>
        </div>
      </form>
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
