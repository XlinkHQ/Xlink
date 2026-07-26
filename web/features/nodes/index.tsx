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
import { relativeTime } from "@/lib/status";
import {
  WarpButton,
  WarpEmpty,
  WarpError,
  WarpHead,
  WarpMenu,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { SearchBox } from "@/components/ui/search-box";
import { useT } from "@/lib/i18n";

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
  const t = useT();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const nodes = (query.data?.items ?? []) as NodeRead[];

  const [editing, setEditing] = useState<NodeRead | "new" | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [editInline, setEditInline] = useState(false);
  const [search, setSearch] = useState("");
  const detail = detailId ? (nodes.find((n) => n.id === detailId) ?? null) : null;

  const refresh = () => qc.invalidateQueries({ queryKey: ["nodes"] });
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) toast("success", ok);
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
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
        <span className="title">{t("nodes.allNodes")}</span>
        <div className="right">
          <SearchBox value={search} onChange={setSearch} placeholder={t("nodes.findNode")} />
          <WarpMenu
            label={t("nodes.generalActions")}
            items={[
              { label: t("action.refresh"), icon: "refresh", onClick: () => refresh() },
              {
                label: t("nodes.exportBackup"),
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
                    toast("success", t("nodes.backupExported"));
                  } catch (e) {
                    toast("error", e instanceof ApiError ? e.message : t("nodes.exportFailed"));
                  }
                },
              },
            ]}
          />
          <WarpButton primary onClick={() => setEditing("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("nodes.addNode")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("nodes.host"), t("common.status")]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : query.isError ? (
          <WarpError onRetry={() => query.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {search ? t("common.noMatches") : t("nodes.noNodesYet")}
          </WarpEmpty>
        ) : (
          filtered.map((n) => (
            <WarpRow
              key={n.id}
              onClick={() => setDetailId(n.id)}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setEditing(n) },
                {
                  label: t("nodes.restartCore"),
                  icon: "refresh",
                  onClick: async () => {
                    if (
                      await confirmDialog({
                        title: t("nodes.restartCoreConfirm", { name: n.name }),
                        message: t("nodes.restartCoreMessage"),
                        confirmLabel: t("nodes.restart"),
                        danger: true,
                      })
                    )
                      act(() => restartNodeCore(n.id), t("nodes.coreRestartRequested"));
                  },
                },
                {
                  label: t("action.disable"),
                  icon: "disable",
                  danger: true,
                  onClick: async () => {
                    if (await confirmDialog({ title: t("nodes.disableConfirm", { name: n.name }), confirmLabel: t("action.disable"), danger: true }))
                      act(() => disableNode(n.id), t("nodes.nodeDisabled"));
                  },
                },
                {
                  label: t("action.delete"),
                  icon: "delete",
                  danger: true,
                  onClick: async () => {
                    if (
                      await confirmDialog({
                        title: t("nodes.deleteConfirm", { name: n.name }),
                        message: t("nodes.deleteMessage"),
                        confirmLabel: t("action.delete"),
                        danger: true,
                      })
                    )
                      act(() => deleteNode(n.id), t("nodes.nodeDeleted"));
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


