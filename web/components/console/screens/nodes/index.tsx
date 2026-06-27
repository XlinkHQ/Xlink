"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";

/** Linear toolbar icons (exact paths from Linear). 16x16. */
function FilterIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor">
      <path fillRule="evenodd" clipRule="evenodd" d="M14.25 3a.75.75 0 0 1 0 1.5H1.75a.75.75 0 0 1 0-1.5h12.5ZM4 8a.75.75 0 0 1 .75-.75h6.5a.75.75 0 0 1 0 1.5h-6.5A.75.75 0 0 1 4 8Zm2.75 3.5a.75.75 0 0 0 0 1.5h2.5a.75.75 0 0 0 0-1.5h-2.5Z" />
    </svg>
  );
}
function DisplayIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor">
      <path fillRule="evenodd" clipRule="evenodd" d="M7 2.5C8.11933 2.5 9.06613 3.23584 9.38477 4.25H14.75C15.1642 4.25 15.5 4.58579 15.5 5C15.5 5.41421 15.1642 5.75 14.75 5.75H9.38477C9.06613 6.76416 8.11933 7.5 7 7.5C5.88067 7.5 4.93387 6.76416 4.61523 5.75H2.25C1.83579 5.75 1.5 5.41421 1.5 5C1.5 4.58579 1.83579 4.25 2.25 4.25H4.61523C4.93387 3.23584 5.88067 2.5 7 2.5ZM7 4C6.44772 4 6 4.44772 6 5C6 5.55228 6.44772 6 7 6C7.55228 6 8 5.55228 8 5C8 4.44772 7.55228 4 7 4Z" />
      <path fillRule="evenodd" clipRule="evenodd" d="M10 13.5C8.88067 13.5 7.93387 12.7642 7.61523 11.75H2.25C1.83579 11.75 1.5 11.4142 1.5 11C1.5 10.5858 1.83579 10.25 2.25 10.25H7.61523C7.93387 9.23584 8.88067 8.5 10 8.5C11.1193 8.5 12.0661 9.23584 12.3848 10.25H14.75C15.1642 10.25 15.5 10.5858 15.5 11C15.5 11.4142 15.1642 11.75 14.75 11.75H12.3848C12.0661 12.7642 11.1193 13.5 10 13.5ZM10 12C10.5523 12 11 11.5523 11 11C11 10.4477 10.5523 10 10 10C9.44772 10 9 10.4477 9 11C9 11.5523 9.44772 12 10 12Z" />
    </svg>
  );
}
function PanelIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor">
      <path fillRule="evenodd" clipRule="evenodd" d="M4.25 2C2.45508 2 1 3.45508 1 5.25V10.75C1 12.5449 2.45508 14 4.25 14H11.75C13.5449 14 15 12.5449 15 10.75V5.25C15 3.45508 13.5449 2 11.75 2H4.25ZM2.5 5.5C2.5 4.39543 3.39543 3.5 4.5 3.5H11.5C12.6046 3.5 13.5 4.39543 13.5 5.5V10.5C13.5 11.6046 12.6046 12.5 11.5 12.5H4.5C3.39543 12.5 2.5 11.6046 2.5 10.5V5.5Z" />
      <rect x="10" y="5" width="1.5" height="6" rx="0.75" />
    </svg>
  );
}

/** Linear "Project" glyph — rounded square outline with quarter-arc fill (project progress). 16x16. */
function ProjectIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="currentColor">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M3.5 2C2.67157 2 2 2.67157 2 3.5V12.5C2 13.3284 2.67157 14 3.5 14H12.5C13.3284 14 14 13.3284 14 12.5V3.5C14 2.67157 13.3284 2 12.5 2H3.5ZM3.5 3.5H12.5V12.5H3.5V3.5Z"
        opacity="0.55"
      />
      <path d="M5 5H10.5C10.7761 5 11 5.22386 11 5.5V11H5.5C5.22386 11 5 10.7761 5 10.5V5Z" />
    </svg>
  );
}
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
  WarpEmpty,
  WarpHead,
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
  const [statsOpen, setStatsOpen] = useState(false);

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
        <span className="warp-stats-wrap">
          <button
            type="button"
            className="warp-stats-trigger"
            aria-haspopup="dialog"
            aria-expanded={statsOpen}
            onClick={() => setStatsOpen((o) => !o)}
            title="Overview"
          >
            <ChevronDown size={14} className={statsOpen ? "is-open" : undefined} />
          </button>
          {statsOpen ? (
            <>
              <span className="warp-stats-scrim" aria-hidden onClick={() => setStatsOpen(false)} />
              <div className="warp-stats-pop" role="dialog">
                <div className="warp-stats-row"><span>Nodes</span><b>{nodes.length}</b></div>
                <div className="warp-stats-row"><span>Online</span><b>{online}</b></div>
                <div className="warp-stats-row"><span>Users</span><b>{totalUsers}</b></div>
              </div>
            </>
          ) : null}
        </span>
        <button
          type="button"
          className="warp-page-add"
          onClick={() => setEditing("new")}
          aria-label="Add node"
          title="Add node"
        >
          <Plus size={16} />
        </button>
      </div>

      <WarpTableCard
        toolbar={
          <>
            <span className="warp-tab is-active" aria-current="page">All nodes</span>
            <span className="warp-tb-spacer" />
            <span className="warp-tb-iconbox">
              <button type="button" className="warp-tb-ico" title="Filter" aria-label="Filter">
                <FilterIcon />
              </button>
              <button type="button" className="warp-tb-ico" title="Display options" aria-label="Display options">
                <DisplayIcon />
              </button>
              <button
                type="button"
                className="warp-tb-ico"
                title="Export backup"
                aria-label="Export backup"
                onClick={async () => {
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
                }}
              >
                <PanelIcon />
              </button>
            </span>
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
                <span className="warp-tb-icochip" data-tone={statusTone(n.status)} aria-hidden>
                  <ProjectIcon />
                </span>,
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

