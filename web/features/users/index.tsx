"use client";

import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, ChevronDown, ChevronRight, ChevronUp, CircleUser, Gauge, Globe, Layers, Link as LinkIcon, Pencil, Power, RefreshCw, RotateCcw, Smartphone, Trash } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  type BulkAction,
  bulkUserAction,
  deleteUser,
  disableUser,
  enableUser,
  listUsers,
  onlineUsers,
  usersLastSeen,
  listUserDevices,
  resetUserDevices,
  resetUserUsage,
  restoreUser,
  revokeSubscription,
  type UserRead,
  usersUsage,
  userSubscriptionUrl,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { bytes } from "@/lib/format";
import { CopyValue } from "@/shared/table-kit";
import {
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpMenu,
  WarpSkeleton,
  WarpTableCard,
  WarpRadial,
  WarpRow,
} from "@/shared/warp-table";
import { copyText } from "@/lib/clipboard";
import {
  AccessManager,
  UserNodesUsagePanel,
  UserSubscriptionPanel,
} from "./access";
import { EditUserDialog, UserDialog } from "./dialogs";
import { DgAddUser } from "@/components/console/dg-icons";
import { SearchBox } from "@/components/ui/search-box";
import { SettingsSection } from "@/shared/settings-kit";

function readPref(k: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(`xlink.${k}`); } catch { return null; }
}
function writePref(k: string, v: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(`xlink.${k}`, v); } catch { /* ignore */ }
}

type UserStatusKey = "all" | "online" | "active" | "expired" | "disabled" | "limited";
type SortCol = "name" | "username" | "email" | "online" | "status" | "traffic" | "expiration";
type SortDir = "asc" | "desc";
type BadgeVariant = "success" | "critical" | "neutral" | "warning" | "info";
function Badge({ variant, children }: { variant: BadgeVariant; children: React.ReactNode }) {
  return <span className={`warp-badge ${variant}`}>{children}</span>;
}

function relTimeShort(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

function initialsOf(name: string): string {
  const s = name.trim();
  if (!s) return "?";
  const parts = s.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return s.slice(0, 2).toUpperCase();
}

function UserNameCell({ name, online }: { name: string; online: boolean }) {
  return (
    <span className="warp-user-namecell">
      <span
        className={`warp-user-online-dot ${online ? "is-on" : "is-off"}`}
        aria-label={online ? "online" : "offline"}
        title={online ? "Online" : "Offline"}
      />
      <span className="warp-user-name">{name}</span>
    </span>
  );
}

function SortTh({
  col,
  label,
  sortCol,
  sortDir,
  onSort,
}: {
  col: SortCol;
  label: string;
  sortCol: SortCol | null;
  sortDir: SortDir;
  onSort: (c: SortCol) => void;
}) {
  const active = sortCol === col;
  return (
    <button type="button" className={`warp-th-sort${active ? " is-active" : ""}`} onClick={() => onSort(col)}>
      <span>{label}</span>
      {active ? (
        sortDir === "asc" ? <ChevronUp size={13} strokeWidth={2} aria-hidden /> : <ChevronDown size={13} strokeWidth={2} aria-hidden />
      ) : null}
    </button>
  );
}

export function UsersScreen() {
  const qc = useQueryClient();
  const [showRemoved, setShowRemoved] = useState(false);
  const query = useInfiniteQuery({
    queryKey: ["users", showRemoved],
    queryFn: ({ pageParam }) =>
      listUsers({ size: 50, cursor: pageParam, role: "user", includeRemoved: showRemoved }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const users = useMemo(
    () => (query.data?.pages.flatMap((p) => p.items) ?? []) as UserRead[],
    [query.data],
  );
  const pageKeys = useMemo(
    () => (query.data?.pages ?? []).map((p) => p.items.map((u) => u.id)),
    [query.data],
  );
  const usageResults = useQueries({
    queries: pageKeys.map((ids) => ({
      queryKey: ["users-usage", ids.join(",")],
      queryFn: () => usersUsage(ids),
      enabled: ids.length > 0,
      staleTime: 15000,
    })),
  });
  const lastSeenResults = useQueries({
    queries: pageKeys.map((ids) => ({
      queryKey: ["users-lastseen", ids.join(",")],
      queryFn: () => usersLastSeen(ids),
      enabled: ids.length > 0,
      staleTime: 15000,
    })),
  });
  const usageMap = useMemo(
    () => new Map(usageResults.flatMap((r) => (r.data ?? []).map((u) => [u.user_id, u]))),
    [usageResults],
  );
  const lastSeenMap = useMemo(
    () => new Map(lastSeenResults.flatMap((r) => (r.data ?? []).map((r2) => [r2.user_id, r2.last_seen_at]))),
    [lastSeenResults],
  );
  const onlineQuery = useQuery({
    queryKey: ["users-online"],
    queryFn: () => onlineUsers(),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });
  const onlineSet = useMemo(
    () => new Set(onlineQuery.data?.user_ids ?? []),
    [onlineQuery.data],
  );

  const [detail, setDetail] = useState<UserRead | null>(null);
  const [editing, setEditing] = useState<UserRead | null>(null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<UserStatusKey>(
    () => (readPref("users.status") as UserStatusKey) ?? "all",
  );
  const [sortCol, setSortCol] = useState<SortCol | null>(
    () => (readPref("users.sortCol") as SortCol) ?? null,
  );
  const [sortDir, setSortDir] = useState<SortDir>(
    () => (readPref("users.sortDir") as SortDir) ?? "asc",
  );
  useEffect(() => writePref("users.status", statusFilter), [statusFilter]);
  useEffect(() => writePref("users.sortCol", sortCol ?? ""), [sortCol]);
  useEffect(() => writePref("users.sortDir", sortDir), [sortDir]);
  const toggleSort = (col: SortCol) => {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const toggleSel = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const clearSel = () => setSelected(new Set());
  const bulkServer = async (
    action: BulkAction,
    ok: string,
    params?: Parameters<typeof bulkUserAction>[2],
  ) => {
    const ids = [...selected];
    try {
      const res = await bulkUserAction(action, ids, params);
      clearSel();
      refresh();
      qc.invalidateQueries({ queryKey: ["users-usage"] });
      if (res.failed === 0) toast("success", `${ok} (${res.ok}).`);
      else toast("error", `${res.ok}/${ids.length} done — ${res.failed} failed.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Bulk action failed.");
    }
  };
  const [bulkEdit, setBulkEdit] = useState<null | "limit" | "expiry" | "reset">(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) toast("success", ok);
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const setActiveOptimistic = async (id: string, active: boolean, fn: () => Promise<unknown>, ok: string) => {
    const key = ["users", showRemoved];
    const prev = qc.getQueryData(key);
    qc.setQueryData(key, (old: unknown) => {
      const data = old as { pages: { items: UserRead[] }[] } | undefined;
      if (!data) return old;
      return {
        ...data,
        pages: data.pages.map((p) => ({
          ...p,
          items: p.items.map((u) => (u.id === id ? { ...u, is_active: active } : u)),
        })),
      };
    });
    try {
      await fn();
      toast("success", ok);
      refresh();
    } catch (e) {
      qc.setQueryData(key, prev);
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const copyId = async (id: string) => {
    const ok = await copyText(id);
    toast(ok ? "success" : "error", ok ? "User ID copied." : "Copy failed — select and copy manually.");
  };
  const copySub = async (id: string) => {
    let url: string;
    try {
      url = (await userSubscriptionUrl(id)).subscription_url;
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not get subscription link.");
      return;
    }
    const ok = await copyText(url);
    toast(ok ? "success" : "error", ok ? "Subscription link copied." : "Copy failed — select and copy manually.");
  };
  const resetUsage = async (id: string) => {
    if (!(await confirmDialog({ title: "Reset traffic usage?", message: "This user's counter returns to zero.", confirmLabel: "Reset", danger: true }))) return;
    try {
      await resetUserUsage(id);
      toast("success", "Usage reset.");
      qc.invalidateQueries({ queryKey: ["a-traffic"] });
      qc.invalidateQueries({ queryKey: ["assignments"] });
      qc.invalidateQueries({ queryKey: ["users-usage"] });
      qc.invalidateQueries({ queryKey: ["traffic"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Reset failed.");
    }
  };

  const revoke = async (id: string) => {
    if (!(await confirmDialog({ title: "Revoke subscription link?", message: "The current link will stop working.", confirmLabel: "Revoke", danger: true })))
      return;
    try {
      await revokeSubscription(id);
      toast("success", "Subscription revoked.");
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["sub-url"] });
      qc.invalidateQueries({ queryKey: ["sub-links"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const restore = async (id: string) => {
    try {
      await restoreUser(id);
      toast("success", "User restored.");
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restore failed.");
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = useMemo(() => {
    const now = Date.now();
    const matchStatus = (u: UserRead): boolean => {
      if (statusFilter === "all") return true;
      const used = usageMap.get(u.id)?.used_bytes ?? 0;
      const reached = u.data_limit_bytes != null && used >= u.data_limit_bytes;
      const expired = u.expire_at != null && Date.parse(u.expire_at) < now;
      switch (statusFilter) {
        case "online": return onlineSet.has(u.id);
        case "active": return u.is_active && !expired && !reached;
        case "disabled": return !u.is_active;
        case "expired": return expired;
        case "limited": return reached;
        default: return false;
      }
    };
    return users
      .filter((u) => (needle ? [u.username, u.email, u.role].some((v) => String(v).toLowerCase().includes(needle)) : true))
      .filter(matchStatus)
      .sort((a, b) => {
        if (!sortCol) return Date.parse(b.created_at) - Date.parse(a.created_at);
        const dir = sortDir === "asc" ? 1 : -1;
        const ua = usageMap.get(a.id)?.used_bytes ?? 0;
        const ub = usageMap.get(b.id)?.used_bytes ?? 0;
        switch (sortCol) {
          case "name": return (a.full_name || a.username).localeCompare(b.full_name || b.username) * dir;
          case "email": return String(a.email ?? "").localeCompare(String(b.email ?? "")) * dir;
          case "username": return a.username.localeCompare(b.username) * dir;
          case "online": return ((onlineSet.has(b.id) ? 1 : 0) - (onlineSet.has(a.id) ? 1 : 0)) * dir;
          case "status": return ((a.is_active ? 1 : 0) - (b.is_active ? 1 : 0)) * dir;
          case "traffic": return (ua - ub) * dir;
          case "expiration": return ((a.expire_at ? Date.parse(a.expire_at) : Infinity) - (b.expire_at ? Date.parse(b.expire_at) : Infinity)) * dir;
          default: return 0;
        }
      });
  }, [users, needle, statusFilter, sortCol, sortDir, usageMap, onlineSet]);

  const maxUsed = useMemo(
    () => users.reduce((m, u) => Math.max(m, usageMap.get(u.id)?.used_bytes ?? 0), 0),
    [users, usageMap],
  );

  if (detail) {
    const live = users.find((u) => u.id === detail.id) ?? detail;
    return (
      <UserProfileView
        key={live.id}
        user={live}
        onBack={() => setDetail(null)}
        onReset={() => resetUsage(live.id)}
        onToggle={() =>
          live.is_active
            ? act(() => disableUser(live.id), "User disabled.")
            : act(() => enableUser(live.id), "User enabled.")
        }
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      {selected.size > 0 ? (
        <div className="warp-bulkbar">
          <span className="warp-bulk-count">{selected.size} selected</span>
          <span className="warp-bulk-sep" />
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("enable", "Enabled")}>
            <Power size={14} aria-hidden /> Enable
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("disable", "Disabled")}>
            <Power size={14} aria-hidden /> Disable
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("reset_usage", "Usage reset")}>
            <RotateCcw size={14} aria-hidden /> Reset usage
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("limit")}>
            <Gauge size={14} aria-hidden /> Data limit
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("expiry")}>
            <CalendarClock size={14} aria-hidden /> Expiry
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("reset")}>
            <RefreshCw size={14} aria-hidden /> Auto-reset
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-danger"
            onClick={async () => {
              if (await confirmDialog({ title: `Delete ${selected.size} user(s)?`, message: "This cannot be undone.", confirmLabel: "Delete", danger: true }))
                bulkServer("delete", "Deleted");
            }}
          >
            <Trash size={14} aria-hidden /> Delete
          </button>
          <button type="button" className="warp-tb-button warp-bulk-clear" onClick={clearSel}>Clear</button>
        </div>
      ) : null}

      {bulkEdit ? (
        <BulkEditModal
          kind={bulkEdit}
          count={selected.size}
          onClose={() => setBulkEdit(null)}
          onApply={async (action, params, ok) => {
            setBulkEdit(null);
            await bulkServer(action, ok, params);
          }}
        />
      ) : null}

      <div className="warp-table-top">
        <span className="title">All users</span>
        <div className="right">
          <label className="flex cursor-pointer select-none items-center gap-1.5 text-[13px] text-fg-muted">
            <input
              type="checkbox"
              className="warp-tb-check"
              checked={showRemoved}
              onChange={(e) => setShowRemoved(e.target.checked)}
            />
            Show removed
          </label>
          <SearchBox value={search} onChange={setSearch} placeholder="Find user" />
          <WarpButton primary onClick={() => setCreating(true)}>
            <DgAddUser size={18} aria-hidden /> Add new user
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead
          cols={[
            <input
              key="selall"
              type="checkbox"
              className="warp-tb-check"
              aria-label="Select all"
              checked={filtered.length > 0 && filtered.every((u) => selected.has(u.id))}
              ref={(el) => {
                if (el)
                  el.indeterminate =
                    selected.size > 0 && !filtered.every((u) => selected.has(u.id));
              }}
              onChange={(e) =>
                setSelected(
                  e.target.checked ? new Set(filtered.map((u) => u.id)) : new Set(),
                )
              }
            />,
            <SortTh key="username" col="username" label="Username" sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            <SortTh key="status" col="status" label="Status" sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            "Last seen",
            <SortTh key="traffic" col="traffic" label="Used Traffic" sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            <SortTh key="expiration" col="expiration" label="Expiration" sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
          ]}
          actions
        />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-user">
            {needle || statusFilter !== "all" ? "No matches." : "No users yet."}
          </WarpEmpty>
        ) : (
          <>{filtered.map((u, idx) => {
            const used = usageMap.get(u.id)?.used_bytes ?? 0;
            const limit = u.data_limit_bytes;
            const reached = limit != null && used >= limit;
            const expired = u.expire_at != null && Date.parse(u.expire_at) < Date.now();
            return (
              <div
                key={u.id}
                className="warp-tb-row"
                role="button"
                tabIndex={0}
                onClick={() => setDetail(u)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setDetail(u);
                  }
                }}
              >
                <span className="warp-tb-cell">
                  <span className="warp-tb-idcell">
                    <input
                      type="checkbox"
                      className="warp-tb-check"
                      checked={selected.has(u.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleSel(u.id)}
                    />
                  </span>
                </span>
                <span className="warp-tb-cell warp-tb-cell-name">
                  <UserNameCell name={u.username} online={onlineSet.has(u.id)} />
                </span>
                <span className="warp-tb-cell">
                  {u.removed ? (
                    <Badge variant="neutral">Removed</Badge>
                  ) : !u.is_active ? (
                    <Badge variant="critical">Disabled</Badge>
                  ) : expired ? (
                    <Badge variant="critical">Expired</Badge>
                  ) : reached || u.on_hold ? (
                    <Badge variant="warning">{reached ? "Limited" : "On hold"}</Badge>
                  ) : (
                    <Badge variant="success">Active</Badge>
                  )}
                </span>
                <span className="warp-tb-cell text-fg-muted">{relTimeShort(lastSeenMap.get(u.id))}</span>
                <span className="warp-tb-cell">
                  <WarpRadial
                    tone={reached ? "green" : "blue"}
                    pct={limit ? (used / limit) * 100 : maxUsed > 0 ? (used / maxUsed) * 100 : 0}
                    label={limit ? `${bytes(used)} / ${bytes(limit)}` : bytes(used)}
                  />
                </span>
                <span className="warp-tb-cell">
                  {u.expire_at ? (
                    <Badge variant={expired ? "critical" : "warning"}>{u.expire_at.slice(0, 10)}</Badge>
                  ) : (
                    <Badge variant="neutral">∞</Badge>
                  )}
                </span>
                <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
                  <WarpMenu
                    items={[
                      ...(u.removed ? [{ label: "Restore", icon: "restore", onClick: () => restore(u.id) }] : []),
                      { label: "Edit", icon: "edit", onClick: () => setEditing(u) },
                      { label: "Copy ID", icon: "copy-id", onClick: () => copyId(u.id) },
                      { label: "Copy subscription", icon: "copy-link", onClick: () => copySub(u.id) },
                      { label: "Reset usage", icon: "reset-usage", onClick: () => resetUsage(u.id) },
                      { label: "Revoke subscription", icon: "revoke", onClick: () => revoke(u.id) },
                      u.is_active
                        ? { label: "Disable", icon: "disable", onClick: () => setActiveOptimistic(u.id, false, () => disableUser(u.id), "User disabled.") }
                        : { label: "Enable", icon: "enable", onClick: () => setActiveOptimistic(u.id, true, () => enableUser(u.id), "User enabled.") },
                      {
                        label: "Remove",
                        icon: "delete",
                        danger: true,
                        onClick: async () => {
                          if (await confirmDialog({ title: `Delete user "${u.username}"?`, message: "This cannot be undone.", confirmLabel: "Delete", danger: true }))
                            act(() => deleteUser(u.id), "User deleted.");
                        },
                      },
                    ]}
                  />
                </span>
              </div>
            );
          })}</>
        )}
      </WarpTableCard>

      {query.hasNextPage ? (
        <div className="flex flex-col items-center gap-1">
          {needle ? (
            <p className="text-[11px] text-fg-muted">
              Searching loaded users only — load more to widen the search.
            </p>
          ) : null}
          <Button
            variant="outline"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}

      {creating ? (
        <UserDialog
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            refresh();
          }}
        />
      ) : null}

      {editing ? (
        <EditUserDialog
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
            qc.invalidateQueries({ queryKey: ["users-usage"] });
          }}
        />
      ) : null}
    </div>
  );
}

const USER_TABS = [
  ["info", "Details"],
  ["services", "Services"],
  ["subscription", "Subscription"],
  ["nodes", "Nodes Usage"],
] as const;

function UserProfileView({
  user,
  onBack,
  onReset,
  onToggle,
}: {
  user: UserRead;
  onBack: () => void;
  onReset: () => void;
  onToggle: () => void;
}) {
  const [tab, setTab] = useState<string>("info");
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-breadcrumbs">
        <div className="track">
          <button
            type="button"
            className="warp-breadcrumbs-back"
            aria-label="Back"
            onClick={onBack}
          >
            <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
          </button>
          <span className="warp-breadcrumbs-divider" />
          <div className="links">
            <button type="button" className="crumb" onClick={onBack}>
              Users
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{user.username}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" className="warp-tb-button" onClick={() => setEditing(true)}>
              <Pencil size={14} aria-hidden /> Edit
            </button>
            <button type="button" className="warp-tb-button" onClick={onReset}>
              <RotateCcw size={14} aria-hidden /> Reset usage
            </button>
            <button type="button" className="warp-tb-button" onClick={onToggle}>
              <Power size={14} aria-hidden /> {user.is_active ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
      </div>
      <div className="warp-pd-tabs warp-profile-tabs">
        {USER_TABS.map(([key, label]) => (
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

      {tab === "info" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={CircleUser} title="General" description="Account details and usage limits for this user.">
            <div className="warp-pd-form">
              <PdRow label="Username" value={user.username} />
              <PdRow label="Name" value={user.full_name || "—"} />
              <PdRow label="Email" value={user.email || "—"} />
              <PdRow label="Status" value={
                !user.is_active ? <Badge variant="critical">Disabled</Badge>
                  : user.on_hold ? <Badge variant="warning">On-hold</Badge>
                  : (user.expire_at && Date.parse(user.expire_at) < Date.now()) ? <Badge variant="critical">Expired</Badge>
                  : <Badge variant="success">Active</Badge>
              } />
              <PdRow label="Expiration" value={
                user.expire_at ? new Date(user.expire_at).toLocaleDateString() : "Never"
              } />
              <PdRow label="Data limit" value={
                user.data_limit_bytes ? bytes(user.data_limit_bytes) : "Unlimited"
              } />
              <PdRow label="Used traffic" value={bytes(user.users_data_usage ?? 0)} />
              <PdRow label="Device limit" value={
                user.device_limit != null ? String(user.device_limit) : "Unlimited"
              } />
              <PdRow label="Owner" value={user.owner_id ? user.owner_id.slice(0, 8) : "—"} />
              <PdRow label="Created" value={
                user.created_at ? new Date(user.created_at).toLocaleString() : "—"
              } />
            </div>
          </SettingsSection>
          <SettingsSection divider icon={Smartphone} title="Devices" description="Devices currently bound to this user.">
            <UserDevicesTable userId={user.id} deviceLimit={user.device_limit} />
          </SettingsSection>
        </div>
      ) : null}

      {tab === "services" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Layers} title="Services" description="Services and inbounds granted to this user.">
            <AccessManager userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "subscription" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={LinkIcon} title="Subscription" description="Subscription link and client configuration for this user.">
            <UserSubscriptionPanel userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "nodes" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Globe} title="Nodes usage" description="Per-node traffic usage for this user.">
            <UserNodesUsagePanel userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}

      {editing ? (
        <EditUserDialog
          user={user}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            qc.invalidateQueries({ queryKey: ["users"] });
          }}
        />
      ) : null}
    </div>
  );
}

function UserDevicesTable({ userId, deviceLimit }: { userId: string; deviceLimit: number | null }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-devices", userId], queryFn: () => listUserDevices(userId) });
  const devices = q.data ?? [];
  const reset = async () => {
    if (!(await confirmDialog({ title: "Reset this user's devices?", message: "All device bindings are removed; the user can re-bind up to the limit.", confirmLabel: "Reset", danger: true }))) return;
    try {
      await resetUserDevices(userId);
      toast("success", "Devices reset.");
      qc.invalidateQueries({ queryKey: ["user-devices", userId] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Reset failed.");
    }
  };
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-fg-muted">
          {devices.length}{deviceLimit != null ? ` / ${deviceLimit}` : ""} bound
        </span>
        <button type="button" className="warp-dg-btn secondary" onClick={reset} disabled={devices.length === 0}>
          Reset devices
        </button>
      </div>
      <WarpTableCard className="warp-users-table warp-devices-table">
        <WarpHead cols={["Device", "User agent", "Last seen"]} />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : devices.length === 0 ? (
          <WarpEmpty icon="fa-mobile">No devices bound.</WarpEmpty>
        ) : (
          devices.map((d) => (
            <WarpRow
              key={d.id}
              cells={[
                <span className="warp-tb-mono">{d.device_hash.slice(0, 12)}</span>,
                <span className="text-fg-muted" title={d.user_agent}>{d.user_agent || "—"}</span>,
                <span className="text-fg-muted">{relTimeShort(d.last_seen_at)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>
    </>
  );
}

function PdRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="warp-pd-row">
      <span className="warp-pd-row-label">{label}</span>
      <span className="warp-pd-row-value">{value}</span>
    </div>
  );
}

function FactorRow({
  icon,
  title,
  availability,
  badge,
}: {
  icon: React.ReactNode;
  title: string;
  availability: string;
  badge: React.ReactNode;
}) {
  return (
    <div className="warp-pd-factor">
      <div className="track">
        <div className="info">
          {icon}
          <p className="factor-name">{title}</p>
          <div className="badges">{badge}</div>
        </div>
        <div className="avail-line">
          <div className="fill" />
          <p className="availability">{availability}</p>
        </div>
      </div>
    </div>
  );
}


function BulkEditModal({
  kind,
  count,
  onClose,
  onApply,
}: {
  kind: "limit" | "expiry" | "reset";
  count: number;
  onClose: () => void;
  onApply: (
    action: BulkAction,
    params: Parameters<typeof bulkUserAction>[2],
    ok: string,
  ) => void;
}) {
  const [limitGb, setLimitGb] = useState("");
  const [expMode, setExpMode] = useState<"date" | "extend">("date");
  const [expDate, setExpDate] = useState("");
  const [extendDays, setExtendDays] = useState("30");
  const [strategy, setStrategy] = useState("no_reset");

  const title =
    kind === "limit" ? "Set data limit" : kind === "expiry" ? "Set expiry" : "Auto-reset usage";

  const apply = () => {
    if (kind === "limit") {
      const gb = Number(limitGb);
      onApply(
        "set_data_limit",
        { data_limit_bytes: limitGb.trim() === "" ? null : Math.round(gb * 1024 ** 3) },
        "Data limit set",
      );
    } else if (kind === "expiry") {
      if (expMode === "extend") {
        onApply("extend_expiry", { extend_days: Number(extendDays) || 0 }, "Expiry extended");
      } else {
        onApply(
          "set_expiry",
          { expire_at: expDate ? new Date(expDate + "T23:59:59").toISOString() : null },
          "Expiry set",
        );
      }
    } else {
      onApply("set_reset_strategy", { data_reset_strategy: strategy }, "Auto-reset set");
    }
  };

  return (
    <Modal
      title={`${title} · ${count} user${count === 1 ? "" : "s"}`}
      width="w-[min(460px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="primary" onClick={apply}>Apply</Button>
        </>
      }
    >
      {kind === "limit" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">Data limit (GiB)</span>
          <Input
            type="number"
            min="0"
            value={limitGb}
            onChange={(e) => setLimitGb(e.target.value)}
            placeholder="Leave empty for unlimited"
            autoFocus
          />
          <span className="warp-field-helper">Applies the same cap to every selected user. Empty = unlimited.</span>
        </label>
      ) : null}

      {kind === "expiry" ? (
        <>
          <label className="warp-field-row">
            <span className="warp-field-label">Mode</span>
            <Select value={expMode} onChange={(e) => setExpMode(e.target.value as "date" | "extend")}>
              <option value="date">Set a fixed date</option>
              <option value="extend">Extend by days</option>
            </Select>
          </label>
          {expMode === "date" ? (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">Expiry date</span>
              <Input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} />
              <span className="warp-field-helper">Empty clears the expiry (never expires).</span>
            </label>
          ) : (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">Extend by (days)</span>
              <Input type="number" min="1" value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
              <span className="warp-field-helper">Adds to each user&apos;s current expiry (or from now if none).</span>
            </label>
          )}
        </>
      ) : null}

      {kind === "reset" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">Auto-reset usage</span>
          <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="no_reset">No reset</option>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
            <option value="year">Yearly</option>
          </Select>
          <span className="warp-field-helper">Usage auto-zeroes each period for all selected users.</span>
        </label>
      ) : null}
    </Modal>
  );
}
