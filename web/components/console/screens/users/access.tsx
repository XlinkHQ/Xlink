"use client";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Plus, QrCode as QrIcon, Trash } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  type AssignmentRead,
  assignmentTraffic,
  createAssignment,
  deleteAssignment,
  type GroupRead,
  listAssignments,
  listGroups,
  listNodes,
  listProfiles,
  type NodeRead,
  type ProfileRead,
  revokeSubscription,
  subscriptionFeed,
  userNodeUsage,
  userSubscriptionUrl,
  userUsageSeries,
} from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { cn } from "@/lib/cn";
import { UsageAreaChart } from "../usage-chart";
import { bytes } from "@/lib/format";

const TAG_TONE: Record<string, string> = {
  sub: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
  vless: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  vmess: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  trojan: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
  shadowsocks: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  ss: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  hysteria2: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
  hy2: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
  tuic: "bg-pink-500/15 text-pink-600 dark:text-pink-400",
  wireguard: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
};

function tagTone(name: string): string {
  return TAG_TONE[name.toLowerCase()] ?? "bg-muted text-fg-muted";
}

function QrImage({ value, size = 180 }: { value: string; size?: number }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!value) return;
    QRCode.toDataURL(value, {
      width: size,
      margin: 1,
      errorCorrectionLevel: "M",
      color: { light: "#ffffff", dark: "#161616" },
    })
      .then(setSrc)
      .catch(() => setSrc(""));
  }, [value, size]);
  if (!src) return null;
  return (
    <div className="inline-block bg-white p-2" style={{ borderRadius: 0 }}>
      <img src={src} alt="Subscription QR code" width={size} height={size} className="block" style={{ borderRadius: 0 }} />
    </div>
  );
}

export function AccessManager({ userId }: { userId: string }) {
  const qc = useQueryClient();
  const aq = useQuery({
    queryKey: ["assignments", userId],
    queryFn: () => listAssignments({ userId }),
  });
  const pq = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const nq = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const gq = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const mine = (aq.data?.items ?? []) as AssignmentRead[];
  const profiles = (pq.data?.items ?? []) as ProfileRead[];
  const nodes = (nq.data?.items ?? []) as NodeRead[];
  const groups = (gq.data ?? []) as GroupRead[];

  const trafficQs = useQueries({
    queries: mine.map((a) => ({
      queryKey: ["a-traffic", a.id],
      queryFn: () => assignmentTraffic(a.id),
      staleTime: 30_000,
    })),
  });
  const usedFor = (id: string) => {
    const i = mine.findIndex((a) => a.id === id);
    return i >= 0 ? (trafficQs[i]?.data?.total_bytes ?? 0) : 0;
  };
  const profName = (id: string) => profiles.find((p) => p.id === id)?.name ?? id.slice(0, 8);
  const nodeName = (id: string) => nodes.find((n) => n.id === id)?.name ?? id.slice(0, 8);

  const [adding, setAdding] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [limitGiB, setLimitGiB] = useState("");
  const [expiry, setExpiry] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["assignments"] });
    qc.invalidateQueries({ queryKey: ["sub-links"] });
  };

  const available = profiles.filter(
    (p) => !mine.some((a) => a.profile_id === p.id && a.node_id === p.node_id),
  );

  const resetForm = () => {
    setAdding(false);
    setProfileId("");
    setLimitGiB("");
    setExpiry("");
  };

  const grant = async () => {
    const prof = profiles.find((p) => p.id === profileId);
    if (!prof) {
      toast("error", "Profile not found.");
      return;
    }
    try {
      const gib = Number(limitGiB);
      await createAssignment({
        user_id: userId,
        profile_id: prof.id,
        node_id: prof.node_id,
        provider_kind: prof.provider_kind,
        expires_at: expiry ? new Date(expiry).toISOString() : null,
        traffic_limit_bytes: limitGiB && gib > 0 ? Math.round(gib * 1024 ** 3) : null,
      });
      toast("success", "Access granted.");
      resetForm();
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Failed to grant access.");
    }
  };

  const grantGroup = async (groupId: string) => {
    const group = groups.find((g) => g.id === groupId);
    if (!group) return;
    const targets = group.profile_ids
      .map((pid) => profiles.find((p) => p.id === pid))
      .filter((p): p is ProfileRead => Boolean(p))
      .filter((p) => !mine.some((a) => a.profile_id === p.id && a.node_id === p.node_id));
    if (targets.length === 0) {
      toast("error", "All inbounds in this group are already granted.");
      return;
    }
    const results = await Promise.allSettled(
      targets.map((p) =>
        createAssignment({
          user_id: userId,
          profile_id: p.id,
          node_id: p.node_id,
          provider_kind: p.provider_kind,
          expires_at: null,
          traffic_limit_bytes: null,
          group_id: group.id,
        }),
      ),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.length - ok;
    const firstError = results.find((r) => r.status === "rejected") as
      | PromiseRejectedResult
      | undefined;
    const reason =
      firstError && firstError.reason instanceof ApiError
        ? firstError.reason.message
        : "Request failed.";
    refresh();
    if (ok > 0 && failed === 0) {
      toast("success", `Granted ${ok} inbound(s) from "${group.name}".`);
    } else if (ok > 0) {
      toast("success", `Granted ${ok} of ${results.length} — ${reason}`);
    } else {
      toast("error", `Could not apply "${group.name}": ${reason}`);
    }
  };

  const revoke = async (id: string) => {
    try {
      await deleteAssignment(id);
      toast("success", "Access removed.");
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Failed to remove access.");
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-3 pb-4">
        <h3 className="text-xl font-medium leading-none tracking-tight text-fg">Services</h3>
        {available.length > 0 ? (
          <Button variant="outline" onClick={() => setAdding((v) => !v)}>
            <Plus className="h-4 w-4" />
            Add inbound
          </Button>
        ) : null}
      </div>

      <div className="flex flex-col gap-4">
        {groups.length > 0 ? (
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">
              Service bundles
            </div>
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => {
                const granted =
                  g.profile_ids.length > 0 &&
                  g.profile_ids.every((pid) => {
                    const prof = profiles.find((p) => p.id === pid);
                    return prof
                      ? mine.some((a) => a.profile_id === prof.id && a.node_id === prof.node_id)
                      : false;
                  });
                return (
                  <button
                    key={g.id}
                    type="button"
                    disabled={granted}
                    onClick={() => grantGroup(g.id)}
                    className={cn(
                      "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-medium transition-colors",
                      granted
                        ? "border-hairline bg-muted text-fg-muted"
                        : "border-primary/30 text-primary hover:bg-primary-soft",
                    )}
                  >
                    {granted ? null : <Plus className="h-3.5 w-3.5" />}
                    {g.name}
                    {granted ? " ✓" : ""}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* Add a single inbound */}
        {adding ? (
          <div className="flex flex-col gap-2 rounded-md border border-hairline p-3">
            <Select value={profileId} onChange={(e) => setProfileId(e.target.value)} className="h-9">
              <option value="">Select inbound…</option>
              {available.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.protocol} @ {nodeName(p.node_id)}
                </option>
              ))}
            </Select>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-widest text-fg-muted">
                Traffic limit (GiB)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={limitGiB}
                  onChange={(e) => setLimitGiB(e.target.value)}
                  placeholder="Unlimited"
                  className="h-9 rounded-md border border-hairline bg-transparent px-2.5 text-sm font-normal text-fg outline-none focus:border-primary"
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-widest text-fg-muted">
                Expiry date
                <input
                  type="date"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                  className="h-9 rounded-md border border-hairline bg-transparent px-2.5 text-sm font-normal text-fg outline-none focus:border-primary"
                />
              </label>
            </div>
            <p className="text-[11px] text-fg-muted">Leave blank to inherit the user-level quota and expiry.</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={resetForm}>
                Cancel
              </Button>
              <Button variant="primary" onClick={grant} disabled={!profileId}>
                Grant
              </Button>
            </div>
          </div>
        ) : null}

        {/* Granted inbounds */}
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">
            Granted inbounds
          </div>
          {mine.length === 0 ? (
            <p className="py-4 text-center text-sm text-fg-muted">No inbounds granted yet.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {mine.map((a) => (
                  <tr key={a.id} className="border-b border-hairline last:border-0">
                    <td className="py-3 pr-3 align-middle">
                      <div className="font-medium text-fg">{profName(a.profile_id)}</div>
                      <div className="text-xs text-fg-muted">@ {nodeName(a.node_id)}</div>
                    </td>
                    <td className="py-3 align-middle text-sm text-fg-muted">
                      {bytes(usedFor(a.id))}
                      {a.traffic_limit_bytes ? ` / ${bytes(a.traffic_limit_bytes)}` : " used"}
                      {a.expires_at ? (
                        <span className="block text-xs">exp {a.expires_at.slice(0, 10)}</span>
                      ) : null}
                    </td>
                    <td className="py-3 align-middle">
                      <Badge tone={toneForStatus(a.status)}>{a.status}</Badge>
                    </td>
                    <td className="py-3 pl-3 text-right align-middle">
                      <button
                        type="button"
                        onClick={() => revoke(a.id)}
                        aria-label="Remove access"
                        className="text-fg-muted transition-colors hover:text-danger"
                      >
                        <Trash className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

export function UserSubscription({ userId }: { userId: string }) {
  const urlQ = useQuery({ queryKey: ["sub-url", userId], queryFn: () => userSubscriptionUrl(userId) });
  const linksQ = useQuery({
    queryKey: ["sub-links", userId],
    queryFn: () => subscriptionFeed("users", userId, "text"),
  });
  const subUrl = urlQ.data?.subscription_url ?? "";
  const links = (linksQ.data?.content ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.includes("://"));

  return (
    <div className="flex flex-col gap-1 pt-2">
      {subUrl ? <LinkRow tag="sub" value={subUrl} /> : null}
      {links.map((link, i) => (
        <LinkRow key={`${link}-${i}`} tag={link.split("://")[0]} value={link} />
      ))}
    </div>
  );
}

export function UserQrButton({ userId }: { userId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label="QR codes"
        title="QR codes"
        onClick={() => setOpen(true)}
        className="grid h-7 w-7 place-items-center rounded text-fg-muted hover:bg-muted hover:text-fg"
      >
        <QrIcon className="h-4 w-4" />
      </button>
      {open ? <UserQrModal userId={userId} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function UserQrModal({ userId, onClose }: { userId: string; onClose: () => void }) {
  const urlQ = useQuery({ queryKey: ["sub-url", userId], queryFn: () => userSubscriptionUrl(userId) });
  const linksQ = useQuery({
    queryKey: ["sub-links", userId],
    queryFn: () => subscriptionFeed("users", userId, "text"),
  });
  const subUrl = urlQ.data?.subscription_url ?? "";
  const links = (linksQ.data?.content ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.includes("://"));
  const qrItems = [
    ...(subUrl ? [{ label: "sub", value: subUrl }] : []),
    ...links.map((l) => ({ label: l.split("://")[0], value: l })),
  ];
  return <QrModal items={qrItems} onClose={onClose} />;
}

function LinkRow({ tag, value }: { tag: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title="Click to copy"
      onClick={async () => {
        await copyText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      }}
      className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left"
    >
      <span className={`flex-none rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${tagTone(tag)}`}>
        {tag}
      </span>
      <span className={`truncate font-mono text-[11px] ${copied ? "font-medium text-success" : "text-fg-muted"}`}>
        {copied ? "Copied to clipboard" : value}
      </span>
    </button>
  );
}

function QrModal({ items, onClose }: { items: { label: string; value: string }[]; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-black/50 p-4"
      onMouseDown={onClose}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-w-[90vw] flex-wrap items-start justify-center gap-6 rounded-xl bg-canvas p-6 shadow-pop"
      >
        {items.map((it) => (
          <QrItem key={`${it.label}-${it.value}`} label={it.label} value={it.value} />
        ))}
      </div>
    </div>
  );
}

function QrItem({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title="Click to copy config"
      onClick={async () => {
        await copyText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      }}
      className="flex flex-col items-center gap-2.5"
    >
      <QrImage value={value} size={200} />
      <span className={`rounded px-2 py-0.5 text-[11px] font-medium uppercase ${tagTone(label)}`}>
        {label}
      </span>
      <span className={`text-[10px] ${copied ? "font-medium text-success" : "text-fg-muted"}`}>
        {copied ? "Copied ✓" : "Click to copy"}
      </span>
    </button>
  );
}

export function UserSubscriptionPanel({ userId }: { userId: string }) {
  const qc = useQueryClient();
  const urlQ = useQuery({ queryKey: ["sub-url", userId], queryFn: () => userSubscriptionUrl(userId) });
  const subUrl = urlQ.data?.subscription_url ?? "";
  const [busy, setBusy] = useState(false);

  const revoke = async () => {
    if (!(await confirmDialog({ title: "Revoke subscription link?", message: "Existing clients will stop updating.", confirmLabel: "Revoke", danger: true }))) return;
    setBusy(true);
    try {
      await revokeSubscription(userId);
      toast("success", "Subscription revoked.");
      qc.invalidateQueries({ queryKey: ["sub-url", userId] });
      qc.invalidateQueries({ queryKey: ["sub-links", userId] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Revoke failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="pb-4">
          <h3 className="text-xl font-medium leading-none tracking-tight text-fg">
            Subscription QRCode
          </h3>
        </div>
        <div className="grid place-items-center py-10">
          {subUrl ? (
            <QrImage value={subUrl} size={280} />
          ) : (
            <span className="text-sm text-fg-muted">No subscription link.</span>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          variant="outline"
          className="flex-1"
          disabled={!subUrl}
          onClick={async () => {
            await copyText(subUrl);
            toast("success", "Subscription link copied.");
          }}
        >
          <Copy className="h-4 w-4" />
          Subscription Link
        </Button>
        <Button variant="danger" className="flex-1" disabled={busy} onClick={revoke}>
          Revoke Subscription
        </Button>
      </div>
    </div>
  );
}

export function UserNodesUsagePanel({ userId }: { userId: string }) {
  const [days, setDays] = useState(14);
  const nodesQ = useQuery({
    queryKey: ["user-node-usage", userId],
    queryFn: () => userNodeUsage(userId),
  });
  const seriesQ = useQuery({
    queryKey: ["user-usage-series", userId, days],
    queryFn: () => userUsageSeries(userId, days),
  });
  const rows = nodesQ.data ?? [];
  const series = seriesQ.data ?? [];
  const total = rows.reduce((sum, r) => sum + r.total_bytes, 0);
  const RANGES: Array<[number, string]> = [
    [7, "7d"],
    [14, "14d"],
    [30, "30d"],
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-end justify-between gap-3 pb-4">
          <div>
            <h3 className="text-xl font-medium leading-none tracking-tight text-fg">
              Nodes Usage
            </h3>
            <div className="mt-2 flex gap-1">
              {RANGES.map(([d, label]) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(d)}
                  className={cn(
                    "h-7 rounded-md px-2.5 text-xs font-medium transition-colors",
                    days === d ? "bg-primary-soft text-primary" : "text-fg-muted hover:bg-muted",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-2xl font-medium leading-none text-fg">{bytes(total)}</span>
            <span className="text-sm text-fg-muted">Total</span>
          </div>
        </div>
        <div className="py-2">
          <UsageAreaChart
            series={series.map((p) => ({ ts: p.date, total_bytes: p.total_bytes, upload_bytes: p.upload_bytes, download_bytes: p.download_bytes }))}
            loading={seriesQ.isLoading}
            height={240}
            empty="No measured traffic in this range."
          />
        </div>
      </div>

      {rows.length > 0 ? (
        <div>
          <div className="pb-3">
            <h4 className="text-sm font-medium uppercase tracking-wide text-fg-muted">
              Per node
            </h4>
          </div>
          <div className="py-1">
            <table className="w-full text-sm">
              <tbody>
                {rows.map((r) => {
                  const pct = total > 0 ? Math.round((r.total_bytes / total) * 100) : 0;
                  return (
                    <tr key={r.node_id}>
                      <td className="w-40 py-2.5 pr-4 align-middle font-normal text-fg">
                        {r.node_name}
                      </td>
                      <td className="py-2.5 align-middle">
                        <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--primary-soft)" }}>
                          <div
                            className="h-full rounded-full"
                            style={{ width: `${pct}%`, background: "var(--primary)" }}
                          />
                        </div>
                      </td>
                      <td className="w-28 py-2.5 pl-4 text-right align-middle font-medium text-fg">
                        {bytes(r.total_bytes)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

