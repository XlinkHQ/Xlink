"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import { selectDialog } from "@/components/ui/dialog";
import {
  ApiError,
  type FailoverPlanRead,
  failoverExecute,
  failoverPlan,
  getCoreTemplates,
  issueAgentCommand,
  listInboundHosts,
  listProfiles,
  type NodeRead,
  nodeCores,
  nodeLogs,
  nodeMetricsRecent,
  nodeTrafficUsage,
  nodeUsageSeries,
  provisionAgentToken,
  restartNodeCore,
  updateCoreTemplate,
  xrayVersions,
} from "@/lib/api";
import { Activity, ArrowRightLeft, ChevronDown, Cpu, Info, KeyRound, Layers as LayersIcon, RotateCw, Server } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";
import { bytes } from "@/lib/format";
import { JsonEditor } from "../json-editor";
import { MetricsAreaChart, UsageAreaChart } from "../usage-chart";
import { Spinner } from "@/components/ui/spinner";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "../warp-table";
import { SettingsSection } from "../settings-kit";
import { isNodeOnline } from "./util";

function protoBadge(p: string): string {
  switch (p.toLowerCase()) {
    case "vless": return "is-blue";
    case "vmess": return "is-indigo";
    case "trojan": return "is-pink";
    case "shadowsocks": return "is-purple";
    case "wireguard": return "is-orange";
    case "hysteria":
    case "hysteria2": return "is-teal";
    case "tuic": return "is-cyan";
    default: return "is-slate";
  }
}

const XRAY_DEFAULT_TEMPLATE = JSON.stringify(
  {
    log: { loglevel: "warning" },
    dns: { servers: ["1.1.1.1", "8.8.8.8", "localhost"] },
    outbounds: [
      { protocol: "freedom", tag: "direct", settings: { domainStrategy: "UseIP" } },
      { protocol: "blackhole", tag: "blocked" },
    ],
    routing: {
      domainStrategy: "IPIfNonMatch",
      rules: [
        { type: "field", protocol: ["bittorrent"], outboundTag: "blocked" },
        { type: "field", ip: ["geoip:private"], outboundTag: "blocked" },
      ],
    },
  },
  null,
  2,
);

const CORE_DEFAULTS: Record<string, string> = {
  xray: XRAY_DEFAULT_TEMPLATE,
  "sing-box": JSON.stringify(
    {
      log: { level: "warn" },
      dns: { servers: [{ tag: "cf", address: "1.1.1.1" }] },
      outbounds: [
        { type: "direct", tag: "direct" },
        { type: "block", tag: "block" },
      ],
    },
    null,
    2,
  ),
  hysteria: JSON.stringify(
    {
      bandwidth: { up: "100 mbps", down: "100 mbps" },
      ignoreClientBandwidth: false,
      masquerade: { type: "proxy", proxy: { url: "https://news.ycombinator.com/", rewriteHost: true } },
    },
    null,
    2,
  ),
  wireguard: JSON.stringify(
    {
      Interface: { MTU: 1420, DNS: ["1.1.1.1"] },
    },
    null,
    2,
  ),
};

const CORE_PLACEHOLDERS: Record<string, string> = {
  xray: '{ "dns": { "servers": ["1.1.1.1"] }, "routing": { "rules": [] } }',
  "sing-box": '{ "log": { "level": "warn" }, "outbounds": [] }',
  hysteria: '{ "bandwidth": { "up": "100 mbps", "down": "100 mbps" } }',
  wireguard: '{ "Interface": { "MTU": 1420 } }',
};

function apiOrigin(): string {
  if (typeof window === "undefined") return "";
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env.replace(/\/+$/, "");
  return `${window.location.origin}/api/v1`;
}

const INSTALLABLE_CORES = ["xray", "singbox", "hysteria", "wireguard"] as const;

function installCommand(nodeId: string, token: string, cores: string[]): string {
  const base = apiOrigin();
  // No env-var prefix before sudo — it sets the var on the sudo process (often
  // stripped by sudoers) not the child bash. The installer derives the agent URL
  // from the panel URL positional arg, so it's redundant anyway.
  // Pass --cores only when it's a strict subset, so the default (all) stays clean.
  const all = INSTALLABLE_CORES.length;
  const flag =
    cores.length && cores.length < all ? ` --cores=${cores.join(",")}` : "";
  return `curl -fsSL ${base}/agent/install.sh | sudo -E bash -s ${window.location.origin} ${nodeId} ${token}${flag}`;
}

export function NodeDetail({
  node,
  onClose,
  onEdit,
}: {
  node: NodeRead;
  onClose: () => void;
  onEdit: () => void;
}) {
  const [tab, setTab] = useState<"config" | "info" | "inbounds">("config");
  const running = isNodeOnline(node.status);

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-pd-tabs warp-profile-tabs">
        {(
          [
            ["config", "Config"],
            ["info", "Info"],
            ["inbounds", "Inbounds"],
          ] as Array<["config" | "info" | "inbounds", string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn("warp-pd-tab", tab === key && "is-active")}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "config" ? <XrayBackendCard node={node} running={running} /> : null}
      {tab === "info" ? <NodeInfo node={node} /> : null}
      {tab === "inbounds" ? <NodeInboundsCard node={node} /> : null}
    </div>
  );
}

const CORE_LABELS: Record<string, string> = {
  xray: "Xray",
  "sing-box": "sing-box",
  hysteria: "Hysteria",
  wireguard: "WireGuard",
};

function XrayBackendCard({ node, running }: { node: NodeRead; running: boolean }) {
  const [sub, setSub] = useState<"logs" | "config">("logs");
  const [core, setCore] = useState<string>("xray");
  const [upgrading, setUpgrading] = useState(false);
  const coresQ = useQuery({
    queryKey: ["node-cores", node.id],
    queryFn: () => nodeCores(node.id),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });
  const installed = (coresQ.data ?? []).map((c) => c.provider_name);
  const cores = installed.length ? installed : ["xray"];
  const activeCore = cores.includes(core) ? core : cores[0];
  const isXray = activeCore === "xray";
  const md = (node.metadata ?? {}) as Record<string, unknown>;
  const version =
    md.xray_version != null
      ? String(md.xray_version)
      : md.core_version != null
        ? String(md.core_version)
        : "";

  const upgrade = async () => {
    let versions: string[] = [];
    try {
      versions = await xrayVersions();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not load Xray versions.");
      return;
    }
    const current = version ? (version.startsWith("v") ? version : `v${version}`) : "";
    const latest = versions[0] ?? "";
    const options = versions.map((v, i) => {
      const tags: string[] = [];
      if (v === current) tags.push("installed");
      if (i === 0) tags.push("latest");
      return {
        value: v,
        label: v,
        hint: tags.join(" · ") || undefined,
        disabled: v === current,
      };
    });
    const upToDate = current && current === latest;
    const target = await selectDialog({
      title: "Upgrade Xray core",
      message: upToDate
        ? `This node already runs the latest release (${current}). Pick an older release only to roll back.`
        : current
          ? `This node runs ${current}. Select a release to install — ${latest} is the latest.`
          : "Select the Xray-core release to install on this node.",
      options,
      defaultValue: upToDate ? "" : latest,
      confirmLabel: "Upgrade",
      emptyLabel: "No releases available right now. Try again shortly.",
    });
    if (!target || target === current) return;
    setUpgrading(true);
    try {
      await issueAgentCommand(node.id, {
        kind: "upgrade",
        payload: { core: activeCore, target_version: target },
      });
      toast("success", `Upgrade to ${target} queued — the agent applies it shortly.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Upgrade failed.");
    } finally {
      setUpgrading(false);
    }
  };

  const [restarting, setRestarting] = useState(false);
  const restartCore = async () => {
    setRestarting(true);
    try {
      await issueAgentCommand(node.id, { kind: "restart", payload: { core: activeCore } });
      toast("success", `Restart of ${CORE_LABELS[activeCore] ?? activeCore} queued.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restart failed.");
    } finally {
      setRestarting(false);
    }
  };

  const coreHealth = (coresQ.data ?? []).find((c) => c.provider_name === activeCore);

  return (
    <div className="warp-settings-card">
      <SettingsSection icon={Server} title="Cores" description="Version, runtime status, logs and configuration per installed core.">
        <div className="warp-xray-head">
          <select
            className="warp-ver-pill warp-core-select"
            value={activeCore}
            onChange={(e) => setCore(e.target.value)}
            title="Select core"
          >
            {cores.map((k) => (
              <option key={k} value={k}>
                {CORE_LABELS[k] ?? k}
              </option>
            ))}
          </select>
          {(() => {
            const st = coreHealth?.status?.toLowerCase();
            const ok = st
              ? ["healthy", "online", "connected", "running", "ok", "idle"].includes(st)
              : running;
            const label = coreHealth ? (ok ? "Healthy" : coreHealth.status) : running ? "Running" : "Offline";
            return (
              <span className={cn("warp-badge", ok ? "success" : "neutral")}>{label}</span>
            );
          })()}
          {isXray ? (
            <button
              type="button"
              className="warp-ver-pill"
              onClick={upgrade}
              disabled={upgrading}
              title="Change Xray-core version"
            >
              {upgrading ? <Spinner size={12} /> : null}
              {version ? `v${version}` : "Set version"}
              <ChevronDown size={12} />
            </button>
          ) : null}
          <button
            type="button"
            className="warp-ver-pill"
            onClick={restartCore}
            disabled={restarting}
            title={`Restart ${CORE_LABELS[activeCore] ?? activeCore}`}
          >
            {restarting ? <Spinner size={12} /> : null}
            Restart
          </button>
        </div>
        <div className="warp-pd-tabs warp-xray-tabs">
          {(
            [
              ["logs", "Logs"],
              ["config", "Core config"],
            ] as Array<["logs" | "config", string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSub(key)}
              className={cn("warp-pd-tab", sub === key && "is-active")}
            >
              {label}
            </button>
          ))}
        </div>
        {sub === "logs" ? (
          <NodeLogs nodeId={node.id} source={activeCore} />
        ) : (
          <CoreConfig node={node} core={activeCore} />
        )}
      </SettingsSection>
    </div>
  );
}

function CoreConfig({ node, core }: { node: NodeRead; core: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["core-templates"], queryFn: () => getCoreTemplates() });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const remoteRaw = q.data?.templates?.[core] ?? "";
  const remote =
    remoteRaw.trim() && remoteRaw.trim() !== "{}" ? remoteRaw : CORE_DEFAULTS[core] ?? "{}";
  useEffect(() => {
    if (q.data) setText(remote);
  }, [q.data, remote, core]);

  const dirty = q.data ? text !== remote : false;
  const valid = (() => {
    try {
      const p = JSON.parse(text || "{}");
      return Boolean(p && typeof p === "object" && !Array.isArray(p));
    } catch {
      return false;
    }
  })();

  const save = async () => {
    setBusy(true);
    try {
      const res = await updateCoreTemplate(core, text || "{}");
      qc.setQueryData(["core-templates"], res);
      toast("success", `${core} template saved — nodes apply it instantly.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    setRestarting(true);
    try {
      await restartNodeCore(node.id);
      toast("success", "Core restart requested — applies within seconds.");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restart failed.");
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <JsonEditor
        value={q.isLoading ? "Loading…" : text}
        onChange={setText}
        rows={24}
        disabled={q.isLoading}
        placeholder={CORE_PLACEHOLDERS[core]}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="warp-tb-button warp-tb-button-primary"
          onClick={save}
          disabled={busy || !valid || !dirty || q.isLoading}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" className="warp-tb-button" onClick={restart} disabled={restarting}>
          <RotateCw size={14} aria-hidden />
          {restarting ? "Restarting…" : "Restart core"}
        </button>
        {!valid ? (
          <span className="text-[11px] font-medium text-danger">Invalid JSON</span>
        ) : dirty ? (
          <span className="text-[11px] text-fg-muted">Unsaved changes</span>
        ) : null}
      </div>
    </div>
  );
}

function NodeInfo({ node }: { node: NodeRead }) {
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
          <span className="text-sm text-fg-muted">Last 24 hours</span>
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
            <WarpEmpty icon="fa-server">No core health reported yet.</WarpEmpty>
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

function NodeInboundsCard({ node }: { node: NodeRead }) {
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
          <WarpEmpty icon="fa-plug">No inbounds on this node yet.</WarpEmpty>
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

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="warp-copyfield">
      <span className="warp-copyfield-label">{label}</span>
      <div className="warp-copyfield-row">
        <div className="warp-copyfield-box">
          <span className="warp-copyfield-val">{value}</span>
        </div>
        <button
          type="button"
          className={cn("warp-copyfield-btn", copied && "is-copied")}
          onClick={async () => {
            const ok = await copyText(value);
            if (!ok) return;
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function NodeLogs({ nodeId, source }: { nodeId: string; source?: string }) {
  const q = useQuery({
    queryKey: ["node-logs", nodeId, source ?? "all"],
    queryFn: () => nodeLogs(nodeId, 100, source),
    refetchInterval: 10000,
  });
  const logs = q.data ?? [];

  const parse = (l: Record<string, unknown>) => {
    const msgRaw = l.message ?? l.msg ?? l.line ?? l.text;
    const msg = typeof msgRaw === "string" ? msgRaw : JSON.stringify(l);
    const lvlRaw = String(l.level ?? l.severity ?? "");
    const lvl = lvlRaw.toLowerCase().replace(/[[\]]/g, "");
    const tsRaw = l.ts ?? l.timestamp ?? l.time;
    const ts = typeof tsRaw === "string" ? tsRaw.slice(11, 19) : "";
    return { ts, lvl, msg };
  };

  const lvlTone = (lvl: string) =>
    lvl.includes("error") ? "err" : lvl.includes("warn") ? "warn" : lvl.includes("debug") ? "dim" : "info";

  const renderMsg = (msg: string) => {
    const re =
      /(\baccepted\b|\brejected\b|\bblocked\b)|(\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b)|(\b\d{1,3}(?:\.\d{1,3}){3}\b)|(\b(?:tcp|udp):[^\s]+)|(email:\s*[^\s]+)|(->|>>)/g;
    const out: ReactNode[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    let k = 0;
    while ((m = re.exec(msg)) !== null) {
      if (m.index > last) out.push(msg.slice(last, m.index));
      let cls = "lg-dim";
      if (m[1]) cls = m[1] === "accepted" ? "lg-accept" : "lg-rej";
      else if (m[2]) cls = "lg-addr";
      else if (m[3]) cls = "lg-ip";
      else if (m[4]) cls = "lg-dest";
      else if (m[5]) cls = "lg-email";
      else if (m[6]) cls = "lg-arrow";
      out.push(
        <span key={k++} className={cls}>
          {m[0]}
        </span>,
      );
      last = m.index + m[0].length;
    }
    if (last < msg.length) out.push(msg.slice(last));
    return out;
  };

  return (
    <div>
      <pre className="warp-logs-pre">
        {q.isLoading ? (
          "Loading…"
        ) : logs.length === 0 ? (
          "No logs reported by this node yet."
        ) : (
          logs.map((l, i) => {
            const { ts, lvl, msg } = parse(l);
            return (
              <div key={i} className="warp-log-line">
                {ts ? <span className="warp-log-ts">{ts}</span> : null}
                {lvl ? <span className={`warp-log-lvl ${lvlTone(lvl)}`}>[{lvl}]</span> : null}
                <span className="warp-log-msg">{renderMsg(msg)}</span>
              </div>
            );
          })
        )}
      </pre>
    </div>
  );
}
