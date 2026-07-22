"use client";

import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  type FailoverPlanRead,
  failoverExecute,
  failoverPlan,
  listInboundHosts,
  listProfiles,
  type NodeRead,
  nodeCores,
  nodeMetricsRecent,
  nodeTrafficUsage,
  nodeUsageSeries,
  provisionAgentToken,
} from "@/lib/api";
import { Activity, ArrowRightLeft, Cpu, Info, KeyRound } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/cn";
import { bytes } from "@/lib/format";
import { MetricsAreaChart, UsageAreaChart } from "@/shared/usage-chart";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { SettingsSection } from "@/shared/settings-kit";
import { isNodeOnline } from "@/lib/status";
import { CORE_LABELS, CopyField, INSTALLABLE_CORES, installCommand } from "./detail-parts";
import { protoBadge } from "@/lib/proto";

export function NodeInfo({ node }: { node: NodeRead }) {
  const [token, setToken] = useState<string | null>(null);
  const [tokenBusy, setTokenBusy] = useState(false);
  const [coresSel, setCoresSel] = useState<string[]>([...INSTALLABLE_CORES]);
  const [drainPlan, setDrainPlan] = useState<FailoverPlanRead | null>(null);
  const [drainBusy, setDrainBusy] = useState(false);
  const usageQuery = useQuery({
    queryKey: ["node-usage", node.id],
    queryFn: () => nodeTrafficUsage(),
  });
  const coresQuery = useQuery({
    queryKey: ["node-cores", node.id],
    queryFn: () => nodeCores(node.id),
  });
  const measured = usageQuery.data?.find((u) => u.node_id === node.id)?.total_bytes ?? 0;
  const healthy = isNodeOnline(node.status);

  const coreOk = (s: string) => ["healthy", "online", "connected", "running", "ok"].includes(s.toLowerCase());

  const openDrain = async () => {
    setDrainBusy(true);
    try {
      setDrainPlan(await failoverPlan(node.id, true));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not build failover plan.");
    } finally {
      setDrainBusy(false);
    }
  };
  const runDrain = async () => {
    if (!drainPlan) return;
    setDrainBusy(true);
    try {
      // Plan was built with dry_run:true (preview); execute for real or the
      // backend short-circuits and migrates nobody.
      const res = await failoverExecute({ ...drainPlan, dry_run: false });
      toast("success", `${res.migrated} migrated, ${res.skipped} skipped.`);
      setDrainPlan(null);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Failover failed.");
    } finally {
      setDrainBusy(false);
    }
  };

  const genToken = async () => {
    setTokenBusy(true);
    try {
      const res = await provisionAgentToken(node.id);
      setToken(res.agent_token);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Failed to generate token.");
    } finally {
      setTokenBusy(false);
    }
  };

  const rows: Array<[string, ReactNode]> = [
    ["Name", node.name],
    ["Address", `${node.host}:${node.port}`],
    ["Usage Coefficient", String(node.usage_coefficient)],
    [
      "Status",
      <span
        key="s"
        className={cn("warp-tb-badge", healthy ? "green" : node.status === "offline" ? "red" : "gray")}
      >
        {healthy ? "Healthy" : node.status === "offline" ? "Unhealthy" : "Disabled"}
      </span>,
    ],
  ];

  return (
    <div className="warp-settings-card">
      <SettingsSection icon={Info} title="Details" description="Core connection details for this node.">
        <div className="warp-pd-form">
          {rows.map(([k, v]) => (
            <div key={String(k)} className="warp-pd-row">
              <span className="warp-pd-row-label">{k}</span>
              <span className="warp-pd-row-value">{v}</span>
            </div>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection divider icon={Activity} title="Node Traffic Usage" description="Total traffic served through this node.">
        <div className="flex items-end justify-between gap-3 pb-3">
          <span className="text-sm text-fg-muted">All-time total</span>
          <div className="flex flex-col items-end">
            <span className="text-2xl font-medium leading-none text-fg">{bytes(measured)}</span>
            <span className="text-sm text-fg-muted">Total</span>
          </div>
        </div>
        <NodeUsageChart nodeId={node.id} />
      </SettingsSection>

      <SettingsSection divider icon={Cpu} title="Node health" description="CPU and memory reported by the node agent.">
        <NodeMetricsChart nodeId={node.id} />
      </SettingsSection>

      <SettingsSection divider icon={KeyRound} title="Agent connection" description="Generate a token to get the node ID, token and one-line install command.">
        <div className="flex items-center justify-end">
          <button type="button" className="warp-dg-btn secondary" onClick={genToken} disabled={tokenBusy}>
            {tokenBusy ? "Generating…" : token ? "Regenerate token" : "Generate token"}
          </button>
        </div>
        {token ? (
          <div className="mt-4 flex flex-col gap-3">
            <CopyField label="Node ID" value={node.id} />
            <CopyField label="Agent token" value={token} />
            <div className="flex flex-col gap-2">
              <span className="warp-field-label">Cores to install</span>
              <div className="flex flex-wrap gap-3">
                {INSTALLABLE_CORES.map((c) => {
                  const on = coresSel.includes(c);
                  return (
                    <label key={c} className="flex items-center gap-1.5 text-[13px] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={c === "xray"}
                        onChange={(e) =>
                          setCoresSel((s) =>
                            e.target.checked ? [...new Set([...s, c])] : s.filter((x) => x !== c),
                          )
                        }
                      />
                      {CORE_LABELS[c === "singbox" ? "sing-box" : c] ?? c}
                    </label>
                  );
                })}
              </div>
            </div>
            <CopyField label="One-line install (run on the node as root)" value={installCommand(node.id, token, coresSel)} />
            <p className="warp-copyfield-hint">Shown once — store it now.</p>
          </div>
        ) : null}
      </SettingsSection>

      <SettingsSection divider icon={Cpu} title="Cores" description="Per-core health and latency reported by this node.">
        <WarpTableCard className="warp-users-table">
          <WarpHead cols={["Provider", "Status", "Latency", "Checked"]} />
          {coresQuery.isLoading ? (
            <WarpSkeleton />
          ) : (coresQuery.data ?? []).length === 0 ? (
            <WarpEmpty>No core health reported yet.</WarpEmpty>
          ) : (
            (coresQuery.data ?? []).map((c) => (
              <WarpRow
                key={c.provider_name}
                cells={[
                  <span className="font-medium">{c.provider_name}</span>,
                  <span className={`warp-badge ${coreOk(c.status) ? "success" : "critical"}`}>{c.status}</span>,
                  <span className="text-fg-muted">{c.latency_ms != null ? `${Math.round(c.latency_ms)} ms` : "—"}</span>,
                  <span className="text-fg-muted">{c.checked_at ? new Date(c.checked_at).toLocaleString() : "—"}</span>,
                ]}
              />
            ))
          )}
        </WarpTableCard>
      </SettingsSection>

      <SettingsSection divider icon={ArrowRightLeft} title="Failover" description="Migrate all clients off this node to healthy nodes.">
        <div className="flex items-center justify-end">
          <button type="button" className="warp-dg-btn secondary" onClick={openDrain} disabled={drainBusy}>
            {drainBusy ? "Planning…" : "Drain node"}
          </button>
        </div>
      </SettingsSection>

      {drainPlan ? (
        <Modal
          title="Drain node"
          onClose={() => setDrainPlan(null)}
          footer={
            <>
              <button type="button" className="warp-tb-button" onClick={() => setDrainPlan(null)} disabled={drainBusy}>
                Cancel
              </button>
              <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={runDrain} disabled={drainBusy || drainPlan.items.length === 0}>
                {drainBusy ? "Migrating…" : "Migrate"}
              </button>
            </>
          }
        >
          <p className="text-sm text-fg-muted" style={{ marginBottom: 12 }}>
            {drainPlan.items.length === 0
              ? "Nothing to migrate — no active assignments on this node."
              : `${drainPlan.items.length} assignment(s) will be migrated to healthy nodes.`}
          </p>
          {drainPlan.items.length > 0 ? (
            <WarpTableCard className="warp-users-table">
              <WarpHead cols={["Profile", "User", "Target node"]} />
              {drainPlan.items.map((it) => (
                <WarpRow
                  key={it.assignment_id}
                  cells={[
                    <span className="warp-tb-mono">{it.profile_id.slice(0, 8)}</span>,
                    <span className="warp-tb-mono">{it.user_id.slice(0, 8)}</span>,
                    <span className="warp-tb-mono">{it.target_node_id.slice(0, 8)}</span>,
                  ]}
                />
              ))}
            </WarpTableCard>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}

export function NodeInboundsCard({ node }: { node: NodeRead }) {
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const hostsQuery = useQuery({
    queryKey: ["inbound-hosts", "all"],
    queryFn: () => listInboundHosts(),
  });

  const profiles = (profilesQuery.data?.items ?? []).filter((p) => p.node_id === node.id);
  const hosts = hostsQuery.data ?? [];
  const loading = profilesQuery.isLoading;

  const addressesFor = (profileId: string): string => {
    const addrs = hosts
      .filter((h) => h.profile_id === profileId)
      .map((h) => (h.port != null ? `${h.address ?? "?"}:${h.port}` : h.address ?? ""))
      .filter(Boolean);
    return addrs.length ? addrs.join(", ") : "—";
  };

  return (
      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Name", "Protocol", "Addresses"]} />
        {loading ? (
          <WarpSkeleton />
        ) : profiles.length === 0 ? (
          <WarpEmpty>No inbounds on this node yet.</WarpEmpty>
        ) : (
          profiles.map((p) => (
            <WarpRow
              key={p.id}
              cells={[
                <span key="n" className="font-medium">{p.name}</span>,
                <span key="p" className={`warp-proto-badge ${protoBadge(p.protocol)}`}>
                  {p.protocol}
                </span>,
                <span key="a" className="text-fg-muted">{addressesFor(p.id)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>
  );
}

function NodeUsageChart({ nodeId }: { nodeId: string }) {
  const q = useQuery({
    queryKey: ["node-usage-series", nodeId],
    queryFn: () => nodeUsageSeries(nodeId, 24),
  });
  return <UsageAreaChart series={q.data ?? []} loading={q.isLoading} />;
}

function NodeMetricsChart({ nodeId }: { nodeId: string }) {
  const q = useQuery({
    queryKey: ["node-metrics", nodeId],
    queryFn: () => nodeMetricsRecent(nodeId, 120),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });
  const samples = q.data ?? [];
  const pick = (name: string) =>
    samples
      .filter((s) => s.name === name)
      .map((s) => ({ x: new Date(s.observed_at).getTime(), y: s.value }))
      .sort((a, b) => a.x - b.x);
  return (
    <MetricsAreaChart
      cpu={pick("cpu_percent")}
      mem={pick("memory_percent")}
      loading={q.isLoading}
    />
  );
}
