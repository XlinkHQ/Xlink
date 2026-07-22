"use client";

import { type ReactNode, useState } from "react";
import { type NodeRead } from "@/lib/api";
import { ArrowLeft, ChevronRight, Pencil } from "lucide-react";
import { cn } from "@/lib/cn";
import { isNodeOnline } from "@/lib/status";
import { XrayBackendCard } from "./detail-config";
import { NodeInboundsCard, NodeInfo } from "./detail-info";

export function NodeDetail({
  node,
  onClose,
  onEdit,
  editing = false,
  editForm = null,
}: {
  node: NodeRead;
  onClose: () => void;
  onEdit: () => void;
  editing?: boolean;
  /** inline edit form rendered below the content when editing */
  editForm?: ReactNode;
}) {
  const [tab, setTab] = useState<"config" | "info" | "inbounds">("config");
  const running = isNodeOnline(node.status);

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-breadcrumbs">
        <div className="track">
          <button
            type="button"
            className="warp-breadcrumbs-back"
            aria-label="Back"
            onClick={onClose}
          >
            <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
          </button>
          <span className="warp-breadcrumbs-divider" />
          <div className="links">
            <button type="button" className="crumb" onClick={onClose}>
              Nodes
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{node.name}</span>
          </div>
          <div className="ml-auto">
            <button
              type="button"
              className={cn("warp-tb-button", editing && "is-active")}
              onClick={onEdit}
              aria-pressed={editing}
            >
              <Pencil size={14} aria-hidden /> Edit
            </button>
          </div>
        </div>
      </div>
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

      {editForm}
    </div>
  );
}
