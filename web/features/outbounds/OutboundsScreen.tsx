"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  deleteOutbound,
  listOutbounds,
  type OutboundRead,
  pingOutboundById,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { WarpButton, WarpEmpty, WarpError, WarpHead, WarpMenu, WarpSkeleton, WarpTableCard, type WarpMenuItem } from "@/shared/warp-table";
import { useT } from "@/lib/i18n";
import { HAS_ADDRESS } from "./constants";
import { OutboundModal } from "./OutboundModal";

export function OutboundsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["outbounds"], queryFn: () => listOutbounds() });
  const outbounds = q.data ?? [];
  const [dialog, setDialog] = useState<OutboundRead | "new" | null>(null);
  const [pinging, setPinging] = useState<string | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["outbounds"] });
    qc.invalidateQueries({ queryKey: ["routing-rules"] });
  };

  const testable = (o: OutboundRead) => !["block", "dns"].includes(o.type);

  const ping = async (o: OutboundRead) => {
    if (pinging) return;
    setPinging(o.id);
    try {
      const r = await pingOutboundById(o.id);
      if (r.ok) {
        toast("success", t("outbounds.toast.reachable", { tag: o.tag, ms: r.latency_ms ?? 0 }));
      } else {
        toast("error", t("outbounds.toast.unreachable", { tag: o.tag, detail: r.detail }));
      }
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("outbounds.toast.testFailed"));
    } finally {
      setPinging(null);
    }
  };

  const remove = async (o: OutboundRead) => {
    if (!(await confirmDialog({ title: t("outbounds.confirmDelete", { tag: o.tag }), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteOutbound(o.id);
      toast("success", t("outbounds.toast.deleted"));
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("outbounds.toast.deleteFailed"));
    }
  };

  const target = (o: OutboundRead) => {
    if (HAS_ADDRESS.has(o.type)) return String(o.settings.address ?? "");
    if (o.type === "wireguard") return String(o.settings.endpoint ?? "");
    if (o.type === "custom") return t("outbounds.rawJson");
    return "—";
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("outbounds.allOutbounds")}</span>
        <div className="right">
          <WarpButton primary onClick={() => setDialog("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("outbounds.addOutbound")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("outbounds.col.tag"), t("outbounds.col.type"), t("outbounds.col.target"), t("common.status")]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : outbounds.length === 0 ? (
          <WarpEmpty>
            {t("outbounds.empty")}
          </WarpEmpty>
        ) : (
          <>
            {outbounds.map((o) => (
              <div key={o.id} className={`warp-tb-row ${o.enabled ? "" : "warp-rt-off"}`}>
                <span className="warp-tb-cell warp-tb-cell-name font-medium">{o.tag}</span>
                <span className="warp-tb-cell"><Badge tone="neutral">{o.type}</Badge></span>
                <span className="warp-tb-cell warp-rt-matchcell">
                  <span className={o.type === "custom" ? "warp-rt-chip is-more" : "warp-rt-chip"}>{target(o)}</span>
                </span>
                <span className="warp-tb-cell">
                  <span className={`warp-rt-status ${o.enabled ? "is-on" : "is-off"}`}>
                    <span className="warp-rt-dot" />{o.enabled ? t("common.enabled") : t("common.disabled")}
                  </span>
                </span>
                <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
                  <WarpMenu
                    items={[
                      ...(testable(o) ? [{ label: pinging === o.id ? t("outbounds.testing") : t("outbounds.testConnection"), icon: "ping", disabled: pinging === o.id, onClick: () => ping(o) } as WarpMenuItem] : []),
                      { label: t("action.edit"), icon: "edit", onClick: () => setDialog(o) },
                      { label: t("action.delete"), icon: "delete", danger: true, onClick: () => remove(o) },
                    ]}
                  />
                </span>
              </div>
            ))}
          </>
        )}
      </WarpTableCard>

      {dialog ? (
        <OutboundModal
          outbound={dialog === "new" ? null : dialog}
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
