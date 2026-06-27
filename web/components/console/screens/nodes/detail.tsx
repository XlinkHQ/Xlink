"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import { selectDialog } from "@/components/ui/dialog";
import {
  ApiError,
  getCoreTemplates,
  issueAgentCommand,
  type NodeRead,
  nodeLogs,
  nodeTrafficUsage,
  nodeUsageSeries,
  provisionAgentToken,
  restartNodeCore,
  updateCoreTemplate,
  xrayVersions,
} from "@/lib/api";
import { ChevronDown, Globe, Loader2, RotateCw, Upload, Wifi, WifiOff, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";
import { bytes } from "@/lib/format";
import { JsonEditor } from "../json-editor";
import { UsageAreaChart } from "../usage-chart";
import { isNodeOnline } from "./util";

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

function apiOrigin(): string {
  if (typeof window === "undefined") return "";
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env.replace(/\/+$/, "");
  return `${window.location.origin}/api/v1`;
}

function installCommand(nodeId: string, token: string): string {
  const base = apiOrigin();
  return `curl -fsSL ${base}/agent/install.sh | XLINK_AGENT_URL=${base}/agent/xlink-agent.py sudo -E bash -s ${window.location.origin} ${nodeId} ${token}`;
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
  const [tab, setTab] = useState<"config" | "info">("config");
  const running = isNodeOnline(node.status);

  return (
    <div className="fixed inset-0 z-[55] flex justify-end bg-black/30" onMouseDown={onClose}>
      <aside
        onMouseDown={(e) => e.stopPropagation()}
        className="flex h-full w-[720px] max-w-full flex-col overflow-auto border-l border-hairline bg-canvas"
      >
        <div className="flex items-center justify-between gap-3 border-b border-hairline p-5">
          <h3 className="text-lg font-medium text-fg">Settings</h3>
          <button
            type="button"
            onClick={onClose}
            className="grid h-7 w-7 flex-none place-items-center rounded text-fg-muted hover:bg-muted"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-4 p-5">
          <div className="warp-usettings-tabs">
            {(
              [
                ["config", "Config"],
                ["info", "Info"],
              ] as Array<["config" | "info", string]>
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={cn("warp-usettings-tab", tab === key && "is-active")}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "config" ? <XrayBackendCard node={node} running={running} /> : null}
          {tab === "info" ? <NodeInfo node={node} /> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-hairline p-4">
          <button type="button" className="warp-tb-button" onClick={onClose}>Close</button>
          <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={onEdit}>Edit</button>
        </div>
      </aside>
    </div>
  );
}

function XrayBackendCard({ node, running }: { node: NodeRead; running: boolean }) {
  const [sub, setSub] = useState<"logs" | "config">("logs");
  const [upgrading, setUpgrading] = useState(false);
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
      await issueAgentCommand(node.id, { kind: "upgrade", payload: { target_version: target } });
      toast("success", `Upgrade to ${target} queued — the agent applies it shortly.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Upgrade failed.");
    } finally {
      setUpgrading(false);
    }
  };

  const updateGeo = async () => {
    setUpgrading(true);
    try {
      await issueAgentCommand(node.id, { kind: "update_geo", payload: {} });
      toast("success", "Geo-IP / geo-site update queued.");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Geo update failed.");
    } finally {
      setUpgrading(false);
    }
  };

  return (
    <div>
      <div className="flex flex-row items-center gap-2 pb-4">
        <h4 className="text-base font-medium capitalize text-fg">Xray</h4>
        <button
          type="button"
          className="warp-ver-pill"
          onClick={upgrade}
          disabled={upgrading}
          title="Change Xray-core version"
        >
          {version ? `v${version}` : "Set version"}
          <ChevronDown size={12} />
        </button>
        <span className={cn("warp-tb-badge", running ? "green" : "red")}>
          {running ? <Wifi size={12} /> : <WifiOff size={12} />} {running ? "Running" : "Offline"}
        </span>
        <button
          type="button"
          className="warp-tb-iconbtn"
          style={{ marginLeft: "auto" }}
          onClick={updateGeo}
          disabled={upgrading}
          title="Update geo-IP / geo-site"
        >
          <Globe size={14} />
        </button>
        <button
          type="button"
          className="warp-tb-iconbtn"
          onClick={upgrade}
          disabled={upgrading}
          title="Upgrade Xray core"
        >
          {upgrading ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />}
        </button>
      </div>
      <div>
        <div className="warp-usettings-tabs mb-3">
          {(
            [
              ["logs", "Logs"],
              ["config", "Config"],
            ] as Array<["logs" | "config", string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSub(key)}
              className={cn("warp-usettings-tab", sub === key && "is-active")}
            >
              {label}
            </button>
          ))}
        </div>
        {sub === "logs" ? (
          <NodeLogs nodeId={node.id} />
        ) : (
          <CoreConfig node={node} />
        )}
      </div>
    </div>
  );
}

function CoreConfig({ node }: { node: NodeRead }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["core-templates"], queryFn: () => getCoreTemplates() });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const remoteRaw = q.data?.templates?.xray ?? "";
  const remote = remoteRaw.trim() && remoteRaw.trim() !== "{}" ? remoteRaw : XRAY_DEFAULT_TEMPLATE;
  useEffect(() => {
    if (q.data) setText(remote);
  }, [q.data, remote]);

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
      const res = await updateCoreTemplate("xray", text || "{}");
      qc.setQueryData(["core-templates"], res);
      toast("success", "Core template saved — nodes apply it instantly.");
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
        rows={26}
        disabled={q.isLoading}
        placeholder='{ "dns": { "servers": ["1.1.1.1"] }, "routing": { "rules": [] } }'
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
  const usageQuery = useQuery({
    queryKey: ["node-usage", node.id],
    queryFn: () => nodeTrafficUsage(),
  });
  const measured = usageQuery.data?.find((u) => u.node_id === node.id)?.total_bytes ?? 0;
  const healthy = isNodeOnline(node.status);

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
    <div className="flex flex-col gap-6">
      <div>
        <div className="pb-2">
          <h4 className="text-base font-medium text-fg">Details</h4>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td className="py-2.5 align-middle text-fg-muted">{k}</td>
                <td className="py-2.5 text-right align-middle font-medium text-fg">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <div className="flex items-end justify-between gap-3 pb-3">
          <div>
            <h4 className="text-base font-medium text-fg">Node Traffic Usage</h4>
            <p className="mt-1 text-sm text-fg-muted">Total traffic usage on this node</p>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-2xl font-medium leading-none text-fg">{bytes(measured)}</span>
            <span className="text-sm text-fg-muted">Total</span>
          </div>
        </div>
        <div className="py-2">
          <NodeUsageChart nodeId={node.id} />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between gap-3">
          <span className="warp-copyfield-title">Agent connection</span>
          <button
            type="button"
            className="warp-tb-button"
            onClick={genToken}
            disabled={tokenBusy}
          >
            {tokenBusy ? "Generating…" : token ? "Regenerate token" : "Generate token"}
          </button>
        </div>
        {token ? (
          <div className="mt-4 flex flex-col gap-3">
            <CopyField label="Node ID" value={node.id} />
            <CopyField label="Agent token" value={token} />
            <CopyField label="One-line install (run on the node as root)" value={installCommand(node.id, token)} />
            <p className="warp-copyfield-hint">Shown once — store it now.</p>
          </div>
        ) : (
          <p className="warp-copyfield-hint mt-3">
            Generate a token to get the node ID, token, and a one-line install command.
          </p>
        )}
      </div>
    </div>
  );
}

function NodeUsageChart({ nodeId }: { nodeId: string }) {
  const q = useQuery({
    queryKey: ["node-usage-series", nodeId],
    queryFn: () => nodeUsageSeries(nodeId, 24),
  });
  return <UsageAreaChart series={q.data ?? []} loading={q.isLoading} />;
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

function NodeLogs({ nodeId }: { nodeId: string }) {
  const q = useQuery({
    queryKey: ["node-logs", nodeId],
    queryFn: () => nodeLogs(nodeId),
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
