"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  disableNode,
  restartNodeCore,
  exportBackup,
  issueAgentCommand,
  listNodes,
  type NodeRead,
  setNodeStatus,
} from "@/lib/api";
import { NodeDetail } from "./detail";
import { NodeDialog } from "./dialog";
import { isNodeOnline, relativeTime } from "./util";
import {
  WarpBadge,
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpMenu,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "../warp-table";

export function NodesScreen() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const nodes = (query.data?.items ?? []) as NodeRead[];

  const [editing, setEditing] = useState<NodeRead | "new" | null>(null);
  const [detail, setDetail] = useState<NodeRead | null>(null);
  const [search, setSearch] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: ["nodes"] });
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) toast("success", ok);
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? nodes.filter((n) =>
        [n.name, n.host, n.status, n.slug].some((v) => String(v).toLowerCase().includes(needle)),
      )
    : nodes;
  const online = nodes.filter((n) => isNodeOnline(n.status)).length;
  const totalUsers = nodes.reduce((s, n) => s + n.current_users, 0);

  return (
    <div className="w-full">
      <div className="warp-page-head">
        <h1 className="warp-page-title">Nodes</h1>
        <div className="warp-page-stats">
          <span><b>{nodes.length}</b> nodes</span>
          <span className="warp-page-dot" />
          <span><b>{online}</b> online</span>
          <span className="warp-page-dot" />
          <span><b>{totalUsers}</b> users</span>
        </div>
      </div>

      <WarpTableCard
        toolbar={
          <>
            <WarpButton primary onClick={() => setEditing("new")}>
              <Plus size={16} /> Add Node
            </WarpButton>
            <span className="warp-tb-spacer" />
            <span className="warp-tb-search-wrap" style={{ maxWidth: 220, flex: "none" }}>
              <Search size={13} style={{ position: "absolute", left: 14, color: "var(--body-muted)", pointerEvents: "none" }} />
              <input
                className="warp-tb-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search"
              />
            </span>
            <WarpMenu
              label="General Actions"
              items={[
                { label: "Refresh", icon: "refresh", onClick: () => refresh() },
                {
                  label: "Export Backup",
                  icon: "download",
                  onClick: async () => {
                    try {
                      const doc = await exportBackup();
                      const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "xlink-backup.json";
                      a.click();
                      URL.revokeObjectURL(url);
                      toast("success", "Backup exported.");
                    } catch (e) {
                      toast("error", e instanceof ApiError ? e.message : "Export failed.");
                    }
                  },
                },
              ]}
            />
          </>
        }
      >
        <WarpHead cols={["", "Name", "Host", "Status", "Users", "Last Seen"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-server">
            {search ? "No matches." : "No nodes yet."}
          </WarpEmpty>
        ) : (
          filtered.map((n, i) => (
            <WarpRow
              key={n.id}
              onClick={() => setDetail(n)}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setEditing(n) },
                {
                  label: "Restart core",
                  icon: "refresh",
                  onClick: async () => {
                    if (
                      await confirmDialog({
                        title: `Restart core on "${n.name}"?`,
                        message: "Active connections drop briefly.",
                        confirmLabel: "Restart",
                        danger: true,
                      })
                    )
                      act(() => restartNodeCore(n.id), "Core restart requested.");
                  },
                },
                {
                  label: "Disable",
                  icon: "disable",
                  danger: true,
                  onClick: async () => {
                    if (await confirmDialog({ title: `Disable node "${n.name}"?`, confirmLabel: "Disable", danger: true }))
                      act(() => disableNode(n.id), "Node disabled.");
                  },
                },
              ]}
              cells={[
                <span className="warp-tb-rowdot" data-tone={statusTone(n.status)} aria-hidden />,
                <span>{n.name}</span>,
                <span className="warp-tb-mono">{n.host}:{n.port}</span>,
                <WarpBadge tone={statusTone(n.status)}>{n.status}</WarpBadge>,
                <span>{n.current_users}</span>,
                relativeTime(n.last_seen_at),
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {detail ? <NodeDetail node={detail} onClose={() => setDetail(null)} onEdit={() => { setEditing(detail); setDetail(null); }} /> : null}

      {editing ? (
        <NodeDialog
          node={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function statusTone(status: string): "green" | "red" | "orange" | "gray" {
  const s = status.toLowerCase();
  if (["active", "online", "healthy"].includes(s)) return "green";
  if (["maintenance"].includes(s)) return "orange";
  if (["offline", "unreachable", "sync_error", "provider_error"].includes(s)) return "red";
  return "gray";
}

