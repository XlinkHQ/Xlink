"use client";

import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Plus, Trash } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toneForStatus } from "@/components/ui/badge";
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
  userNodeUsage,
  userSubscriptionUrl,
  userUsageSeries,
} from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { cn } from "@/lib/cn";
import { UsageAreaChart } from "@/shared/usage-chart";
import { bytes, fromGiB } from "@/lib/format";


/** Map a status string to a .warp-badge variant class. */
function badgeClassForStatus(status: string): string {
  switch (toneForStatus(status)) {
    case "success": return "success";
    case "warning": return "warning";
    case "danger": return "critical";
    case "muted": return "neutral";
    default: return "info";
  }
}

function QrImage({ value, size = 180 }: { value: string; size?: number }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!value) return;
    let active = true;
    QRCode.toDataURL(value, {
      width: size,
      margin: 1,
      errorCorrectionLevel: "M",
      color: { light: "#ffffff", dark: "#161616" },
    })
      .then((url) => {
        if (active) setSrc(url);
      })
      .catch(() => {
        if (active) setSrc("");
      });
    return () => {
      active = false;
    };
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
        // End-of-day, matching the user Edit/bulk dialogs — new Date(expiry) alone
        // is start-of-day UTC and would expire the access ~24h early.
        expires_at: expiry ? new Date(`${expiry}T23:59:59Z`).toISOString() : null,
        traffic_limit_bytes: limitGiB && gib > 0 ? fromGiB(gib) : null,
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
    <div className="warp-svc">
      <div className="warp-svc-toolbar">
        {available.length > 0 ? (
          <button type="button" className="warp-dg-btn secondary" onClick={() => setAdding((v) => !v)}>
            <Plus size={14} strokeWidth={1.8} aria-hidden />
            Add inbound
          </button>
        ) : null}
      </div>

      {groups.length > 0 ? (
        <div className="warp-svc-group">
          <p className="warp-svc-label">Service bundles</p>
          <div className="warp-svc-bundles">
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
                  className={cn("warp-svc-bundle", granted && "is-granted")}
                >
                  {granted ? null : <Plus size={14} strokeWidth={1.8} aria-hidden />}
                  {g.name}
                  {granted ? " ✓" : ""}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {adding ? (
        <div className="warp-svc-add">
          <Select value={profileId} onChange={(e) => setProfileId(e.target.value)} className="h-9">
            <option value="">Select inbound…</option>
            {available.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.protocol} @ {nodeName(p.node_id)}
              </option>
            ))}
          </Select>
          <div className="warp-svc-add-grid">
            <label className="warp-svc-field">
              <span>Traffic limit (GiB)</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={limitGiB}
                onChange={(e) => setLimitGiB(e.target.value)}
                placeholder="Unlimited"
              />
            </label>
            <label className="warp-svc-field">
              <span>Expiry date</span>
              <input
                type="date"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              />
            </label>
          </div>
          <p className="warp-svc-hint">Leave blank to inherit the user-level quota and expiry.</p>
          <div className="warp-svc-add-actions">
            <button type="button" className="warp-dg-btn secondary" onClick={resetForm}>
              Cancel
            </button>
            <button type="button" className="warp-dg-btn primary" onClick={grant} disabled={!profileId}>
              Grant
            </button>
          </div>
        </div>
      ) : null}

      <div className="warp-svc-group">
        <p className="warp-svc-label">Granted inbounds</p>
        {mine.length === 0 ? (
          <p className="warp-svc-empty">No inbounds granted yet.</p>
        ) : (
          <div className="warp-svc-rows">
            {mine.map((a) => (
              <div key={a.id} className="warp-svc-row">
                <div className="warp-svc-row-main">
                  <span className="warp-svc-row-name">{profName(a.profile_id)}</span>
                  <span className="warp-svc-row-node">@ {nodeName(a.node_id)}</span>
                </div>
                <div className="warp-svc-row-usage">
                  {bytes(usedFor(a.id))}
                  {a.traffic_limit_bytes ? ` / ${bytes(a.traffic_limit_bytes)}` : " used"}
                  {a.expires_at ? (
                    <span className="warp-svc-row-exp">exp {a.expires_at.slice(0, 10)}</span>
                  ) : null}
                </div>
                <span className={`warp-badge ${badgeClassForStatus(a.status)}`}>{a.status}</span>
                <button
                  type="button"
                  onClick={() => revoke(a.id)}
                  aria-label="Remove access"
                  className="warp-svc-row-remove"
                >
                  <Trash size={16} strokeWidth={1.8} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
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
    <div className="warp-sub">
      <div className="warp-sub-qr">
        {subUrl ? (
          <QrImage value={subUrl} size={260} />
        ) : (
          <span className="warp-sub-empty">No subscription link.</span>
        )}
      </div>

      <div className="warp-sub-actions">
        <button
          type="button"
          className="warp-dg-btn secondary"
          disabled={!subUrl}
          onClick={async () => {
            await copyText(subUrl);
            toast("success", "Subscription link copied.");
          }}
        >
          <Copy size={14} strokeWidth={1.8} aria-hidden />
          Subscription Link
        </button>
        <button type="button" className="warp-dg-btn critical" disabled={busy} onClick={revoke}>
          <Trash size={14} strokeWidth={1.8} aria-hidden />
          Revoke Subscription
        </button>
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
    <div className="warp-nu">
      <div className="warp-nu-head">
        <div className="warp-nu-ranges">
          {RANGES.map(([d, label]) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={cn("warp-nu-range", days === d && "is-active")}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="warp-nu-total">
          <span className="warp-nu-total-val">{bytes(total)}</span>
          <span className="warp-nu-total-label">Total</span>
        </div>
      </div>

      <div className="warp-nu-chart">
        <UsageAreaChart
          series={series.map((p) => ({ ts: p.date, total_bytes: p.total_bytes, upload_bytes: p.upload_bytes, download_bytes: p.download_bytes }))}
          loading={seriesQ.isLoading}
          height={240}
          empty="No measured traffic in this range."
        />
      </div>

      {rows.length > 0 ? (
        <div className="warp-nu-pernode">
          <p className="warp-svc-label">Per node</p>
          <div className="warp-nu-rows">
            {rows.map((r) => {
              const pct = total > 0 ? Math.round((r.total_bytes / total) * 100) : 0;
              return (
                <div key={r.node_id} className="warp-nu-row">
                  <span className="warp-nu-row-name">{r.node_name}</span>
                  <span className="warp-nu-bar">
                    <span className="warp-nu-bar-fill" style={{ width: `${pct}%` }} />
                  </span>
                  <span className="warp-nu-row-val">{bytes(r.total_bytes)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

