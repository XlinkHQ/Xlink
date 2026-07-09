"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Pencil,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  type AssignmentRead,
  type GroupRead,
  listAllUsers,
  onlineUsers,
  type ProfileRead,
  updateGroup,
} from "@/lib/api";
import { bytes } from "@/lib/format";
import { cn } from "@/lib/cn";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "../warp-table";

const PAGE_SIZE = 10;

function protoBadge(p: string): string {
  switch (p.toLowerCase()) {
    case "vless": return "is-blue";
    case "vmess": return "is-indigo";
    case "trojan": return "is-pink";
    case "shadowsocks": return "is-purple";
    case "wireguard": return "is-orange";
    case "hysteria":
    case "hysteria2": return "is-teal";
    case "tuic": return "is-cyan";
    default: return "is-slate";
  }
}

export function ServiceSettings({
  group,
  profiles,
  nodeName,
  assignments,
  onClose,
  onEdit,
  onSaved,
  editing = false,
  editForm = null,
}: {
  group: GroupRead;
  profiles: ProfileRead[];
  nodeName: (id: string) => string;
  assignments: AssignmentRead[];
  onClose: () => void;
  onEdit: () => void;
  onSaved: () => void;
  /** whether the inline edit box is open (drives the Edit button state) */
  editing?: boolean;
  /** inline edit form rendered below the list when editing */
  editForm?: React.ReactNode;
}) {
  const [tab, setTab] = useState<"inbounds" | "users">("inbounds");

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
              Services
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{group.name}</span>
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
        {([["inbounds", "Inbounds"], ["users", "Users"]] as const).map(([key, label]) => (
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

      {tab === "inbounds" ? (
        <InboundsTab group={group} profiles={profiles} nodeName={nodeName} onSaved={onSaved} />
      ) : (
        <UsersTab group={group} assignments={assignments} />
      )}

      {editForm}
    </div>
  );
}

function InboundsTab({
  group,
  profiles,
  nodeName,
  onSaved,
}: {
  group: GroupRead;
  profiles: ProfileRead[];
  nodeName: (id: string) => string;
  onSaved: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(group.profile_ids));
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);

  const pageCount = Math.max(1, Math.ceil(profiles.length / PAGE_SIZE));
  const start = page * PAGE_SIZE;
  const rows = profiles.slice(start, start + PAGE_SIZE);
  const allOnPage = rows.length > 0 && rows.every((p) => selected.has(p.id));

  const persist = async (next: Set<string>) => {
    const prev = selected;
    setSelected(next);
    setBusy(true);
    try {
      await updateGroup(group.id, { name: group.name, profile_ids: [...next] });
      onSaved();
    } catch (e) {
      // Roll the checkbox back so the on-screen state matches the server after a
      // failed save instead of showing the unsaved (optimistic) selection.
      setSelected(prev);
      toast("error", e instanceof ApiError ? e.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };
  const toggle = (id: string) => {
    const n = new Set(selected);
    n.has(id) ? n.delete(id) : n.add(id);
    persist(n);
  };
  const toggleAll = () => {
    const n = new Set(selected);
    if (allOnPage) rows.forEach((p) => n.delete(p.id));
    else rows.forEach((p) => n.add(p.id));
    persist(n);
  };

  return (
    <div className="flex flex-col gap-4">
      <WarpTableCard className="warp-users-table">
        <WarpHead
          cols={[
            <input key="all" type="checkbox" className="warp-tb-check" checked={allOnPage} onChange={toggleAll} onClick={(e) => e.stopPropagation()} />,
            "Tag",
            "Protocol",
            "Nodes",
          ]}
        />
        {rows.length === 0 ? (
          <WarpEmpty icon="fa-globe">No inbounds available.</WarpEmpty>
        ) : (
          rows.map((p) => (
            <WarpRow
              key={p.id}
              onClick={() => toggle(p.id)}
              cells={[
                <span key="c" className="warp-tb-idcell" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" className="warp-tb-check" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
                </span>,
                <span key="n" className="font-medium">{p.name}</span>,
                <span key="p" className={`warp-proto-badge ${protoBadge(p.protocol)}`}>{p.protocol}</span>,
                <span key="nd" className="text-fg-muted">{nodeName(p.node_id)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      <div className="flex items-center justify-between gap-3 text-xs text-fg-muted">
        <span>
          {busy ? "Saving…" : `${selected.size} / ${profiles.length} selected`}
        </span>
        <div className="flex items-center gap-1">
          <span className="mr-2">
            Page {page + 1} of {pageCount}
          </span>
          <PageBtn onClick={() => setPage(0)} disabled={page === 0} aria-label="First page">
            <ChevronsLeft className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} aria-label="Previous page">
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn onClick={() => setPage(pageCount - 1)} disabled={page >= pageCount - 1} aria-label="Last page">
            <ChevronsRight className="h-4 w-4" aria-hidden />
          </PageBtn>
        </div>
      </div>
    </div>
  );
}

function UsersTab({
  group,
  assignments,
}: {
  group: GroupRead;
  assignments: AssignmentRead[];
}) {
  // listAllUsers walks the cursor — the backend clamps single pages to 100 rows.
  const usersQuery = useQuery({ queryKey: ["users", "all"], queryFn: () => listAllUsers() });
  const onlineQuery = useQuery({ queryKey: ["users-online"], queryFn: () => onlineUsers(), refetchInterval: 30000, refetchIntervalInBackground: false });
  const onlineSet = new Set(onlineQuery.data?.user_ids ?? []);
  const users = usersQuery.data ?? [];
  const members = useMemo(() => {
    const inbounds = new Set(group.profile_ids);
    const ids = new Set<string>();
    for (const a of assignments) if (inbounds.has(a.profile_id)) ids.add(a.user_id);
    return users.filter((u) => ids.has(u.id));
  }, [group.profile_ids, assignments, users]);

  const now = Date.now();

  return (
    <WarpTableCard className="warp-users-table">
      <WarpHead cols={["Username", "Online", "Status", "Used Traffic", "Expiration"]} />
      {usersQuery.isLoading ? (
        <WarpSkeleton />
      ) : members.length === 0 ? (
        <WarpEmpty icon="fa-user">No users in this service yet.</WarpEmpty>
      ) : (
        members.map((u) => {
          const expired = u.expire_at != null && Date.parse(u.expire_at) < now;
          return (
            <WarpRow
              key={u.id}
              cells={[
                <span className="font-medium">{u.username}</span>,
                <span className={`warp-badge ${onlineSet.has(u.id) ? "success" : "neutral"}`}>
                  {onlineSet.has(u.id) ? "Online" : "Offline"}
                </span>,
                <span className={`warp-badge ${!u.is_active ? "critical" : expired ? "critical" : "success"}`}>
                  {!u.is_active ? "Disabled" : expired ? "Expired" : "Active"}
                </span>,
                <span className="text-fg-muted">{bytes(u.users_data_usage ?? 0)}</span>,
                <span className="text-fg-muted">{u.expire_at ? u.expire_at.slice(0, 10) : "Never"}</span>,
              ]}
            />
          );
        })
      )}
    </WarpTableCard>
  );
}

function CheckBox({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={onChange}
      className={cn(
        "grid h-4 w-4 flex-none place-items-center rounded border transition-colors",
        checked ? "border-primary bg-primary text-white" : "border-hairline bg-surface",
      )}
    >
      {checked ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
    </button>
  );
}

function PageBtn({
  onClick,
  disabled,
  children,
  "aria-label": ariaLabel,
}: {
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
  "aria-label"?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className="grid h-7 w-7 place-items-center rounded-md border border-hairline text-fg-muted transition-colors hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
