"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  deleteNode,
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
import { relativeTime } from "./util";
import {
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpMenu,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/components/console/screens/warp-table";
import { SearchBox } from "@/components/ui/search-box";

type BadgeVariant = "success" | "critical" | "neutral" | "warning" | "info";
function Badge({ variant, children }: { variant: BadgeVariant; children: React.ReactNode }) {
  return <span className={`warp-badge ${variant}`}>{children}</span>;
}
const _TRANSITIONAL = new Set(["pending", "connecting", "syncing", "provisioning"]);
function statusVariant(status: string): BadgeVariant {
  const s = status.toLowerCase();
  if (["active", "online", "healthy"].includes(s)) return "success";
  if (["maintenance"].includes(s)) return "warning";
  if (["offline", "unreachable", "sync_error", "provider_error"].includes(s)) return "critical";
  return "neutral";
}
function StatusBadge({ status }: { status: string }) {
  if (_TRANSITIONAL.has(status.toLowerCase())) {
    return (
      <span className="warp-badge info">
        <Spinner size={11} />
        {status}
      </span>
    );
  }
  return <Badge variant={statusVariant(status)}>{status}</Badge>;
}

export function NodesScreen() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const nodes = (query.data?.items ?? []) as NodeRead[];

  const [editing, setEditing] = useState<NodeRead | "new" | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [editInline, setEditInline] = useState(false);
  const [search, setSearch] = useState("");
  // Resolve the open detail node live from the query, so a rename reflects and a
  // deletion closes the view (was falling back to a stale snapshot).
  const detail = detailId ? (nodes.find((n) => n.id === detailId) ?? null) : null;

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

  if (detail) {
    return (
      <NodeDetail
        node={detail}
        onClose={() => { setDetailId(null); setEditInline(false); }}
        onEdit={() => setEditInline((v) => !v)}
        editing={editInline}
        editForm={
          editInline ? (
            <NodeDialog
              variant="inline"
              node={detail}
              onClose={() => setEditInline(false)}
              onSaved={() => { setEditInline(false); refresh(); }}
            />
          ) : null
        }
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">All nodes</span>
        <div className="right">
          <SearchBox value={search} onChange={setSearch} placeholder="Find node" />
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
          <WarpButton primary onClick={() => setEditing("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> Add Node
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Name", "Host", "Status"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-server">
            {search ? "No matches." : "No nodes yet."}
          </WarpEmpty>
        ) : (
          filtered.map((n) => (
            <WarpRow
              key={n.id}
              onClick={() => setDetailId(n.id)}
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
                {
                  label: "Delete",
                  icon: "delete",
                  danger: true,
                  onClick: async () => {
                    if (
                      await confirmDialog({
                        title: `Delete node "${n.name}"?`,
                        message: "The node and its assignments are removed. This cannot be undone.",
                        confirmLabel: "Delete",
                        danger: true,
                      })
                    )
                      act(() => deleteNode(n.id), "Node deleted.");
                  },
                },
              ]}
              cells={[
                <span className="font-medium">{n.name}</span>,
                <span className="warp-tb-mono">{n.host}:{n.port}</span>,
                <StatusBadge status={n.status} />,
              ]}
            />
          ))
        )}
      </WarpTableCard>

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


