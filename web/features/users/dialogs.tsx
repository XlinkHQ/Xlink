"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createAssignment,
  createUser,
  type GroupRead,
  listGroups,
  listNodes,
  listProfiles,
  listUserTemplates,
  type ProfileRead,
  updateUser,
  type UserRead,
} from "@/lib/api";
import { Field } from "@/components/console/screens/parts";

export function EditUserDialog({
  user,
  onClose,
  onSaved,
}: {
  user: UserRead;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(user.full_name ?? "");
  const [limitGib, setLimitGib] = useState(
    user.data_limit_bytes ? (user.data_limit_bytes / 1024 ** 3).toString() : "",
  );
  const [expire, setExpire] = useState(user.expire_at ? user.expire_at.slice(0, 10) : "");
  const [reset, setReset] = useState(user.data_reset_strategy ?? "no_reset");
  const [devices, setDevices] = useState(user.device_limit?.toString() ?? "");
  const [onHold, setOnHold] = useState(user.on_hold ?? false);
  const [holdDays, setHoldDays] = useState("");
  const [activationDeadline, setActivationDeadline] = useState(
    user.activation_deadline ? user.activation_deadline.slice(0, 10) : "",
  );
  const [pinned, setPinned] = useState<string[]>(user.pinned_node_ids ?? []);
  const nodesQuery = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const nodes = nodesQuery.data?.items ?? [];
  const togglePin = (id: string) =>
    setPinned((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const dateToIso = (next: string, original: string | null) => {
        if (!next) return null;
        if (original && original.slice(0, 10) === next) return original;
        return new Date(`${next}T23:59:59Z`).toISOString();
      };
      await updateUser(user.id, {
        full_name: fullName.trim() || null,
        data_limit_bytes: limitGib ? Math.round(Number(limitGib) * 1024 ** 3) : null,
        // An on-hold user cannot also carry a fixed expiry (backend rejects it),
        // so clear expire_at whenever on-hold is checked.
        expire_at: onHold ? null : dateToIso(expire, user.expire_at),
        data_reset_strategy: reset,
        device_limit: devices ? Number(devices) : null,
        on_hold: onHold,
        on_hold_duration_seconds: onHold && holdDays ? Number(holdDays) * 86400 : null,
        activation_deadline: onHold ? dateToIso(activationDeadline, user.activation_deadline) : null,
        pinned_node_ids: pinned,
      });
      toast("success", "User updated.");
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Edit ${user.username}`}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <Field label="Full name (optional)">
        <Input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="off" />
      </Field>
      <div className="warp-dlg-2col">
        <Field label="Data limit (GiB)">
          <Input
            type="number"
            min="0"
            step="0.1"
            value={limitGib}
            onChange={(e) => setLimitGib(e.target.value)}
            placeholder="unlimited"
          />
        </Field>
        <Field label="Expires">
          <Input type="date" value={expire} onChange={(e) => setExpire(e.target.value)} />
        </Field>
        <Field label="Auto-reset usage">
          <Select value={reset} onChange={(e) => setReset(e.target.value)}>
            <option value="no_reset">No reset</option>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
            <option value="year">Yearly</option>
          </Select>
        </Field>
        <Field label="Device limit (HWID)">
          <Input
            type="number"
            min="0"
            value={devices}
            onChange={(e) => setDevices(e.target.value)}
            placeholder="unlimited"
          />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-xs text-fg">
        <input type="checkbox" checked={onHold} onChange={(e) => setOnHold(e.target.checked)} />
        On-hold — start the expiry countdown on first connection
      </label>
      {onHold ? (
        <div className="warp-dlg-2col">
          <Field label="Hold duration (days)">
            <Input
              type="number"
              min="0"
              value={holdDays}
              onChange={(e) => setHoldDays(e.target.value)}
              placeholder="e.g. 30"
            />
          </Field>
          <Field label="Activation deadline">
            <Input
              type="date"
              value={activationDeadline}
              onChange={(e) => setActivationDeadline(e.target.value)}
            />
          </Field>
        </div>
      ) : null}
      <Field label="Pinned nodes (empty = all nodes)">
        <div className="warp-dlg-chipbox">
          {nodes.length === 0 ? (
            <span className="text-[11px] text-fg-muted">No nodes yet.</span>
          ) : (
            nodes.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => togglePin(n.id)}
                className={`warp-pin-chip ${pinned.includes(n.id) ? "is-on" : ""}`}
              >
                {pinned.includes(n.id) ? <Check size={10} aria-hidden /> : null}
                {n.name}
              </button>
            ))
          )}
        </div>
      </Field>
      <p className="text-[11px] text-fg-muted">
        Leave a field empty for unlimited / no expiry. Activation deadline: the user must connect
        before this date or the sub expires.
      </p>
    </Modal>
  );
}

export function UserDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const qc = useQueryClient();
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const profilesQ = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const templatesQ = useQuery({ queryKey: ["user-templates"], queryFn: () => listUserTemplates() });
  const groups = (groupsQ.data ?? []) as GroupRead[];
  const profiles = (profilesQ.data?.items ?? []) as ProfileRead[];
  const templates = templatesQ.data ?? [];

  const [username, setUsername] = useState("");
  const [note, setNote] = useState("");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const toggleGroup = (id: string) =>
    setGroupIds((g) => (g.includes(id) ? g.filter((x) => x !== id) : [...g, id]));
  const [profileIds, setProfileIds] = useState<string[]>([]);
  const toggleProfile = (id: string) =>
    setProfileIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const [limitGib, setLimitGib] = useState("");
  const [devices, setDevices] = useState("");
  const [expireStrategy, setExpireStrategy] = useState<"never" | "fixed_date" | "start_on_first_use">(
    "never",
  );
  const [expire, setExpire] = useState("");
  const [usageDays, setUsageDays] = useState("");
  const [busy, setBusy] = useState(false);

  const applyTemplate = (id: string) => {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    setLimitGib(t.data_limit_bytes ? (t.data_limit_bytes / 1024 ** 3).toString() : "");
    setDevices(t.device_limit != null ? String(t.device_limit) : "");
    if (t.expire_days && t.expire_days > 0) {
      setExpireStrategy("fixed_date");
      const d = new Date();
      d.setDate(d.getDate() + t.expire_days);
      setExpire(d.toISOString().slice(0, 10));
    }
    if (t.username_prefix && !username) {
      setUsername(`${t.username_prefix}${Math.floor(1000 + Math.random() * 9000)}`);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await createUser({
        username: username.trim(),
        full_name: note.trim() || null,
        data_limit_bytes: limitGib ? Math.round(Number(limitGib) * 1024 ** 3) : null,
        device_limit: devices ? Number(devices) : null,
        expire_strategy: expireStrategy,
        expire_at:
          expireStrategy === "fixed_date" && expire
            ? new Date(`${expire}T23:59:59Z`).toISOString()
            : null,
        on_hold: expireStrategy === "start_on_first_use",
        on_hold_duration_seconds:
          expireStrategy === "start_on_first_use" && usageDays
            ? Math.round(Number(usageDays) * 86400)
            : null,
      });

      const chosen = groups.filter((g) => groupIds.includes(g.id));
      const fromGroups = chosen.flatMap((g) =>
        g.profile_ids
          .map((pid) => profiles.find((p) => p.id === pid))
          .filter((p): p is ProfileRead => Boolean(p))
          .map((p) => ({ profile: p, groupId: g.id as string | null })),
      );
      const fromDirect = profiles
        .filter((p) => profileIds.includes(p.id))
        .map((p) => ({ profile: p, groupId: null as string | null }));
      const targets = [...fromGroups, ...fromDirect];
      if (targets.length) {
        const seen = new Set<string>();
        const unique = targets.filter((t) =>
          seen.has(t.profile.id) ? false : (seen.add(t.profile.id), true),
        );
        const results = await Promise.allSettled(
          unique.map((t) =>
            createAssignment({
              user_id: res.id,
              profile_id: t.profile.id,
              node_id: t.profile.node_id,
              provider_kind: t.profile.provider_kind,
              expires_at: null,
              traffic_limit_bytes: null,
              group_id: t.groupId,
            }),
          ),
        );
        const ok = results.filter((r) => r.status === "fulfilled").length;
        const failed = results.length - ok;
        qc.invalidateQueries({ queryKey: ["assignments"] });
        if (failed > 0) {
          const firstErr = results.find((r) => r.status === "rejected") as
            | PromiseRejectedResult
            | undefined;
          const reason =
            firstErr?.reason instanceof ApiError ? firstErr.reason.message : "some inbounds failed";
          toast("error", `User created, but ${failed} inbound(s) failed: ${reason}`);
        } else {
          toast("success", `User “${username.trim()}” created with ${ok} inbound(s).`);
        }
      } else {
        toast("success", `User “${username.trim()}” created.`);
      }
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Create failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Add user"
      width="sm:w-[40rem]"
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
            disabled={busy || !/^[a-zA-Z0-9_]{3,64}$/.test(username.trim())}
          >
            {busy ? "Adding…" : "Add user"}
          </Button>
        </>
      }
    >
      {templates.length > 0 ? (
        <Field label="Template" hint="Prefill limits/expiry from a preset (optional).">
          <Select defaultValue="" onChange={(e) => applyTemplate(e.target.value)}>
            <option value="">No template</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}

      <p className="warp-dlg-section-title">Login information</p>
      <div className="warp-dlg-2col">
        <Field label="Username" hint="3–64 chars · letters, numbers, _">
          <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="off" />
          {username.trim() && !/^[a-zA-Z0-9_]{3,64}$/.test(username.trim()) ? (
            <p className="text-[12px] text-danger" style={{ marginTop: 4 }}>
              Only letters, numbers and _ (3–64 chars). No spaces or other characters.
            </p>
          ) : null}
        </Field>
        <Field label="Full name" hint="Optional display name.">
          <Input value={note} onChange={(e) => setNote(e.target.value)} autoComplete="off" />
        </Field>
      </div>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">Account details</p>
      <div className="warp-dlg-2col">
        <Field label="Data limit (GiB)">
          <Input type="number" min="0" step="0.1" value={limitGib} onChange={(e) => setLimitGib(e.target.value)} placeholder="unlimited" />
        </Field>
        <Field label="Device limit (HWID)" hint="max simultaneous devices/IPs">
          <Input type="number" min="0" value={devices} onChange={(e) => setDevices(e.target.value)} placeholder="unlimited" />
        </Field>
        <Field label="Expiration">
          <Select
            value={expireStrategy}
            onChange={(e) => setExpireStrategy(e.target.value as "never" | "fixed_date" | "start_on_first_use")}
          >
            <option value="never">Never</option>
            <option value="fixed_date">Fixed Date</option>
            <option value="start_on_first_use">On first use</option>
          </Select>
        </Field>
      </div>
      {expireStrategy === "fixed_date" ? (
        <Field label="Expire date">
          <Input type="date" value={expire} onChange={(e) => setExpire(e.target.value)} />
        </Field>
      ) : null}
      {expireStrategy === "start_on_first_use" ? (
        <Field label="Usage duration (days)">
          <Input type="number" min="1" value={usageDays} onChange={(e) => setUsageDays(e.target.value)} placeholder="e.g. 30" />
        </Field>
      ) : null}

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">Access</p>
      <Field label="Services" hint="grants their inbounds on create">
        <div className="warp-dlg-chipbox">
          {groups.length === 0 ? (
            <span className="text-[11px] text-fg-muted">No services yet.</span>
          ) : (
            groups.map((g) => (
              <button
                key={g.id}
                type="button"
                onClick={() => toggleGroup(g.id)}
                className={`warp-pin-chip ${groupIds.includes(g.id) ? "is-on" : ""}`}
              >
                {groupIds.includes(g.id) ? <Check size={10} aria-hidden /> : null}
                {g.name} · {g.profile_ids.length}
              </button>
            ))
          )}
        </div>
      </Field>
      <Field label="Inbounds" hint="combine multiple in one sub">
        <div className="warp-dlg-chipbox">
          {profiles.length === 0 ? (
            <span className="text-[11px] text-fg-muted">No inbounds yet.</span>
          ) : (
            profiles.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => toggleProfile(p.id)}
                className={`warp-pin-chip ${profileIds.includes(p.id) ? "is-on" : ""}`}
              >
                {profileIds.includes(p.id) ? <Check size={10} aria-hidden /> : null}
                {p.name} · {p.protocol}
              </button>
            ))
          )}
        </div>
      </Field>
    </Modal>
  );
}
