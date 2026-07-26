"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui/toast";
import { selectDialog } from "@/components/ui/dialog";
import {
  ApiError,
  getCoreTemplates,
  issueAgentCommand,
  type NodeRead,
  nodeCores,
  restartNodeCore,
  updateCoreTemplate,
  xrayVersions,
} from "@/lib/api";
import { ChevronDown, RotateCw, Server } from "lucide-react";
import { cn } from "@/lib/cn";
import { JsonEditor } from "./json-editor";
import { Spinner } from "@/components/ui/spinner";
import { SettingsSection } from "@/shared/settings-kit";
import { CORE_DEFAULTS, CORE_LABELS, CORE_PLACEHOLDERS } from "./detail-parts";
import { NodeLogs } from "./detail-logs";

export function XrayBackendCard({ node, running }: { node: NodeRead; running: boolean }) {
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
              <ChevronDown size={12} aria-hidden />
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
  const loadedCore = useRef<string | null>(null);
  useEffect(() => {
    if (q.data && loadedCore.current !== core) {
      setText(remote);
      loadedCore.current = core;
    }
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
