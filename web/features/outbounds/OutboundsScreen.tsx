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
import { WarpButton, WarpEmpty, WarpHead, WarpMenu, WarpSkeleton, WarpTableCard, type WarpMenuItem } from "@/shared/warp-table";
import { HAS_ADDRESS } from "./constants";
import { OutboundModal } from "./OutboundModal";

export function OutboundsScreen() {
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
        toast("success", `${o.tag} reachable · ${r.latency_ms ?? 0} ms`);
      } else {
        toast("error", `${o.tag} unreachable · ${r.detail}`);
      }
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Test failed.");
    } finally {
      setPinging(null);
    }
  };

  const remove = async (o: OutboundRead) => {
    if (!(await confirmDialog({ title: `Delete outbound "${o.tag}"?`, confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteOutbound(o.id);
      toast("success", "Outbound deleted.");
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  const target = (o: OutboundRead) => {
    if (HAS_ADDRESS.has(o.type)) return String(o.settings.address ?? "");
    if (o.type === "wireguard") return String(o.settings.endpoint ?? "");
    if (o.type === "custom") return "raw JSON";
    return "—";
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">All outbounds</span>
        <div className="right">
          <WarpButton primary onClick={() => setDialog("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> Add Outbound
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Tag", "Type", "Target", "Status"]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : outbounds.length === 0 ? (
          <WarpEmpty>
            No custom outbounds yet. Rules can also use the builtins (block / direct / warp).
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
                    <span className="warp-rt-dot" />{o.enabled ? "Enabled" : "Disabled"}
                  </span>
                </span>
                <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
                  <WarpMenu
                    items={[
                      ...(testable(o) ? [{ label: pinging === o.id ? "Testing…" : "Test connection", icon: "ping", disabled: pinging === o.id, onClick: () => ping(o) } as WarpMenuItem] : []),
                      { label: "Edit", icon: "edit", onClick: () => setDialog(o) },
                      { label: "Delete", icon: "delete", danger: true, onClick: () => remove(o) },
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
