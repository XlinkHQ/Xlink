"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { DgSearch } from "@/components/console/dg-icons";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createRoutingRule,
  deleteRoutingRule,
  listOutbounds,
  listRoutingRules,
  updateRoutingRule,
  type RoutingRuleRead,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { WarpButton, WarpEmpty, WarpError, WarpHead, WarpMenu, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { useT, type TranslateFn } from "@/lib/i18n";

const outboundMeta = (t: TranslateFn): Record<string, { label: string; tone: "danger" | "success" | "neutral" | "muted" }> => ({
  block: { label: t("routing.outbound.block"), tone: "danger" },
  direct: { label: t("routing.outbound.direct"), tone: "success" },
  warp: { label: t("routing.outbound.warp"), tone: "neutral" },
  proxy: { label: t("routing.outbound.proxy"), tone: "muted" },
});

const matchLabel = (t: TranslateFn): Record<string, string> => ({
  domain: t("routing.match.domain"),
  ip: t("routing.match.ip"),
  port: t("routing.match.port"),
});

export function RoutingScreen() {
  const t = useT();
  const OUTBOUND_META = outboundMeta(t);
  const MATCH_LABEL = matchLabel(t);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["routing-rules"], queryFn: () => listRoutingRules() });
  const rules = q.data ?? [];
  const [dialog, setDialog] = useState<RoutingRuleRead | "new" | null>(null);
  const [search, setSearch] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: ["routing-rules"] });

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return rules;
    return rules.filter(
      (r) =>
        (r.name || "").toLowerCase().includes(term) ||
        r.match_values.toLowerCase().includes(term) ||
        r.outbound.toLowerCase().includes(term),
    );
  }, [rules, search]);

  const toggle = async (r: RoutingRuleRead) => {
    try {
      await updateRoutingRule(r.id, { enabled: !r.enabled });
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("routing.toast.updateFailed"));
    }
  };

  const remove = async (r: RoutingRuleRead) => {
    if (!(await confirmDialog({ title: t("routing.confirmDelete", { name: r.name || r.match_values }), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteRoutingRule(r.id);
      toast("success", t("routing.toast.deleted"));
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("routing.toast.deleteFailed"));
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("routing.allRules")}</span>
        <div className="right">
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("routing.findRule")}
            />
          </span>
          <WarpButton primary onClick={() => setDialog("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("routing.addRule")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("routing.col.match"), t("routing.col.outbound"), t("routing.col.priority"), t("common.status")]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {search.trim()
              ? t("routing.empty.search")
              : t("routing.empty.none")}
          </WarpEmpty>
        ) : (
          <>
            {filtered.map((r) => {
              const ob = OUTBOUND_META[r.outbound] ?? { label: r.outbound, tone: "neutral" as const };
              const values = r.match_values.split(",").map((v) => v.trim()).filter(Boolean);
              return (
                <div key={r.id} className={`warp-tb-row ${r.enabled ? "" : "warp-rt-off"}`}>
                  <span className="warp-tb-cell warp-tb-cell-name font-medium" title={r.name}>
                    {r.name || t("routing.unnamedRule", { type: MATCH_LABEL[r.match_type] ?? r.match_type })}
                  </span>
                  <span className="warp-tb-cell warp-rt-matchcell" title={`${MATCH_LABEL[r.match_type] ?? r.match_type}: ${r.match_values}`}>
                    <span className="warp-rt-match-type">{MATCH_LABEL[r.match_type] ?? r.match_type}</span>
                    {values[0] ? <span className="warp-rt-chip">{values[0]}</span> : null}
                    {values.length > 1 ? <span className="warp-rt-chip is-more">+{values.length - 1}</span> : null}
                  </span>
                  <span className="warp-tb-cell">
                    <Badge tone={ob.tone}>{ob.label}</Badge>
                  </span>
                  <span className="warp-tb-cell">{r.priority}</span>
                  <span className="warp-tb-cell">
                    <button
                      type="button"
                      className={`warp-rt-status ${r.enabled ? "is-on" : "is-off"}`}
                      onClick={() => toggle(r)}
                      title={r.enabled ? t("routing.status.enabledHint") : t("routing.status.disabledHint")}
                    >
                      <span className="warp-rt-dot" />
                      {r.enabled ? t("common.enabled") : t("common.disabled")}
                    </button>
                  </span>
                  <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
                    <WarpMenu
                      items={[
                        { label: t("action.edit"), icon: "edit", onClick: () => setDialog(r) },
                        { label: r.enabled ? t("action.disable") : t("action.enable"), icon: r.enabled ? "disable" : "enable", onClick: () => toggle(r) },
                        { label: t("action.delete"), icon: "delete", danger: true, onClick: () => remove(r) },
                      ]}
                    />
                  </span>
                </div>
              );
            })}
          </>
        )}
      </WarpTableCard>

      {dialog ? (
        <RuleModal
          rule={dialog === "new" ? null : dialog}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function RuleModal({
  rule,
  onClose,
  onSaved,
}: {
  rule: RoutingRuleRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const editing = rule !== null;
  const obQ = useQuery({ queryKey: ["outbounds"], queryFn: () => listOutbounds() });
  const customOutbounds = obQ.data ?? [];
  const [name, setName] = useState(rule?.name ?? "");
  const [matchType, setMatchType] = useState(rule?.match_type ?? "domain");
  const [values, setValues] = useState(rule?.match_values ?? "");
  const [outbound, setOutbound] = useState(rule?.outbound ?? "block");
  const [priority, setPriority] = useState(String(rule?.priority ?? 0));
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        name: name.trim(),
        match_type: matchType,
        match_values: values.trim(),
        outbound: outbound.trim(),
        enabled,
        priority: Number(priority) || 0,
      };
      if (editing && rule) {
        await updateRoutingRule(rule.id, body);
        toast("success", t("routing.toast.updated"));
      } else {
        await createRoutingRule(body);
        toast("success", t("routing.toast.added"));
      }
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("routing.toast.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const hint =
    matchType === "domain"
      ? "domain:example.com, geosite:google, keyword:ads"
      : matchType === "ip"
        ? "1.2.3.0/24, geoip:ir, geoip:private"
        : "443, 8443, 2053";

  const preview = values.split(",").map((v) => v.trim()).filter(Boolean);

  return (
    <Modal
      title={editing ? t("routing.modal.editTitle") : t("routing.modal.addTitle")}
      width="w-[min(580px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>{t("action.cancel")}</Button>
          <Button type="button" variant="primary" disabled={busy || !values.trim()} onClick={submit}>
            {busy ? t("common.saving") : editing ? t("action.saveChanges") : t("action.submit")}
          </Button>
        </>
      }
    >
      <div className="warp-rt-form-info">
        <Info size={16} />
        <span>
          {t("routing.modal.info")}
        </span>
      </div>

      <label className="warp-field-row">
        <span className="warp-field-label">{t("routing.field.name")}</span>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("routing.field.namePlaceholder")} autoFocus />
      </label>
      <div className="warp-dlg-2col" style={{ marginTop: 14 }}>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("routing.field.matchBy")}</span>
          <Select value={matchType} onChange={(e) => setMatchType(e.target.value)}>
            <option value="domain">{t("routing.match.domain")}</option>
            <option value="ip">{t("routing.match.ip")}</option>
            <option value="port">{t("routing.match.port")}</option>
          </Select>
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("routing.col.outbound")}</span>
          <Select value={outbound} onChange={(e) => setOutbound(e.target.value)}>
            <option value="block">{t("routing.outbound.block")}</option>
            <option value="direct">{t("routing.outbound.direct")}</option>
            <option value="warp">{t("routing.outbound.warp")}</option>
            <option value="proxy">{t("routing.outbound.proxy")}</option>
            {customOutbounds.length > 0 ? (
              <optgroup label={t("routing.customOutbounds")}>
                {customOutbounds.map((o) => (
                  <option key={o.id} value={o.tag}>{o.tag} ({o.type})</option>
                ))}
              </optgroup>
            ) : null}
            {!["block","direct","warp","proxy"].includes(outbound) && !customOutbounds.some((o) => o.tag === outbound) ? (
              <option value={outbound}>{outbound}</option>
            ) : null}
          </Select>
        </label>
      </div>
      <label className="warp-field-row" style={{ marginTop: 14 }}>
        <span className="warp-field-label">{t("routing.field.values")}</span>
        <textarea className="warp-cert-textarea" rows={3} value={values} onChange={(e) => setValues(e.target.value)} placeholder={hint} />
        <span className="warp-field-helper">{t("routing.field.valuesHelper")} · {hint}</span>
        {preview.length > 0 ? (
          <span className="warp-rt-preview">
            {preview.map((v, i) => (
              <span key={i} className="warp-rt-preview-chip">{v}</span>
            ))}
          </span>
        ) : null}
      </label>
      <div className="warp-dlg-2col" style={{ marginTop: 14 }}>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("routing.col.priority")}</span>
          <Input type="number" min="0" value={priority} onChange={(e) => setPriority(e.target.value)} />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("common.status")}</span>
          <label className="warp-switch warp-switch-inline">
            <input type="checkbox" checked={enabled} onChange={() => setEnabled((v) => !v)} />
            <span className="warp-switch-track" />
            <span className="warp-switch-label">{enabled ? t("common.enabled") : t("common.disabled")}</span>
          </label>
        </label>
      </div>
    </Modal>
  );
}
