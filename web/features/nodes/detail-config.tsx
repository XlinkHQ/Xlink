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
import { useT } from "@/lib/i18n";

export function XrayBackendCard({ node, running }: { node: NodeRead; running: boolean }) {
  const t = useT();
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
      toast("error", e instanceof ApiError ? e.message : t("nodes.xrayVersionsError"));
      return;
    }
    const current = version ? (version.startsWith("v") ? version : `v${version}`) : "";
    const latest = versions[0] ?? "";
    const options = versions.map((v, i) => {
      const tags: string[] = [];
      if (v === current) tags.push(t("nodes.tagInstalled"));
      if (i === 0) tags.push(t("nodes.tagLatest"));
      return {
        value: v,
        label: v,
        hint: tags.join(" · ") || undefined,
        disabled: v === current,
      };
    });
    const upToDate = current && current === latest;
    const target = await selectDialog({
      title: t("nodes.upgradeXrayTitle"),
      message: upToDate
        ? t("nodes.upgradeUpToDate", { current })
        : current
          ? t("nodes.upgradeCurrent", { current, latest })
          : t("nodes.upgradeSelect"),
      options,
      defaultValue: upToDate ? "" : latest,
      confirmLabel: t("nodes.upgrade"),
      emptyLabel: t("nodes.noReleases"),
    });
    if (!target || target === current) return;
    setUpgrading(true);
    try {
      await issueAgentCommand(node.id, {
        kind: "upgrade",
        payload: { core: activeCore, target_version: target },
      });
      toast("success", t("nodes.upgradeQueued", { target }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("nodes.upgradeFailed"));
    } finally {
      setUpgrading(false);
    }
  };

  const [restarting, setRestarting] = useState(false);
  const restartCore = async () => {
    setRestarting(true);
    try {
      await issueAgentCommand(node.id, { kind: "restart", payload: { core: activeCore } });
      toast("success", t("nodes.restartQueued", { core: CORE_LABELS[activeCore] ?? activeCore }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("nodes.restartFailed"));
    } finally {
      setRestarting(false);
    }
  };

  const coreHealth = (coresQ.data ?? []).find((c) => c.provider_name === activeCore);

  return (
    <div className="warp-settings-card">
      <SettingsSection icon={Server} title={t("nodes.coresTitle")} description={t("nodes.coresConfigDesc")}>
        <div className="warp-xray-head">
          <select
            className="warp-ver-pill warp-core-select"
            value={activeCore}
            onChange={(e) => setCore(e.target.value)}
            title={t("nodes.selectCore")}
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
            const label = coreHealth ? (ok ? t("nodes.healthy") : coreHealth.status) : running ? t("nodes.running") : t("nodes.offline");
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
              title={t("nodes.changeXrayVersion")}
            >
              {upgrading ? <Spinner size={12} /> : null}
              {version ? `v${version}` : t("nodes.setVersion")}
              <ChevronDown size={12} aria-hidden />
            </button>
          ) : null}
          <button
            type="button"
            className="warp-ver-pill"
            onClick={restartCore}
            disabled={restarting}
            title={t("nodes.restartCoreTitle", { core: CORE_LABELS[activeCore] ?? activeCore })}
          >
            {restarting ? <Spinner size={12} /> : null}
            {t("nodes.restart")}
          </button>
        </div>
        <div className="warp-pd-tabs warp-xray-tabs">
          {(
            [
              ["logs", t("nodes.tabLogs")],
              ["config", t("nodes.tabCoreConfig")],
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
  const t = useT();
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
      toast("success", t("nodes.templateSaved", { core }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    setRestarting(true);
    try {
      await restartNodeCore(node.id);
      toast("success", t("nodes.coreRestartApplies"));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("nodes.restartFailed"));
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <JsonEditor
        value={q.isLoading ? t("common.loading") : text}
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
          {busy ? t("common.saving") : t("action.save")}
        </button>
        <button type="button" className="warp-tb-button" onClick={restart} disabled={restarting}>
          <RotateCw size={14} aria-hidden />
          {restarting ? t("nodes.restarting") : t("nodes.restartCore")}
        </button>
        {!valid ? (
          <span className="text-[11px] font-medium text-danger">{t("nodes.invalidJson")}</span>
        ) : dirty ? (
          <span className="text-[11px] text-fg-muted">{t("nodes.unsavedChanges")}</span>
        ) : null}
      </div>
    </div>
  );
}
