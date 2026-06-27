"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Ban,
  Clock,
  Plus,
  Power,
  RotateCcw,
  Search,
  Trash2 as Trash,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  deleteUser,
  disableUser,
  enableUser,
  listUserDevices,
  listUsers,
  onlineUsers,
  resetUserDevices,
  promoteUser,
  resetUserUsage,
  restoreUser,
  revokeSubscription,
  type UserRead,
  usersLastSeen,
  usersUsage,
  userSubscriptionUrl,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { bytes } from "@/lib/format";
import { Avatar, Drawer } from "../parts";
import { CopyValue } from "../table-kit";
import {
  WarpBadge,
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpMenu,
  WarpSkeleton,
  WarpStat,
  WarpStatRow,
  WarpTableCard,
  WarpTraffic,
} from "../warp-table";
import { copyText } from "@/lib/clipboard";
import {
  AccessManager,
  UserNodesUsagePanel,
  UserSubscriptionPanel,
} from "./access";
import { EditUserDialog, UserDialog } from "./dialogs";

function readPref(k: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(`xlink.${k}`); } catch { return null; }
}
function writePref(k: string, v: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(`xlink.${k}`, v); } catch { /* ignore */ }
}

type UserStatusKey = "all" | "online" | "active" | "expired" | "disabled" | "limited";
type UserSortKey = "newest" | "traffic" | "expiring" | "name";
const USER_STATUS_CHIPS: Array<[UserStatusKey, string]> = [
  ["all", "All"],
  ["online", "Online"],
  ["active", "Active"],
  ["expired", "Expired"],
  ["disabled", "Disabled"],
  ["limited", "Limit reached"],
];

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
  const users = (query.data?.pages.flatMap((p) => p.items) ?? []) as UserRead[];
  const userIds = users.map((u) => u.id);
  const usageQuery = useQuery({
    queryKey: ["users-usage", userIds.join(",")],
    queryFn: () => usersUsage(userIds),
    enabled: userIds.length > 0,
  });
  const usageMap = new Map((usageQuery.data ?? []).map((u) => [u.user_id, u]));
  const onlineQuery = useQuery({
    queryKey: ["users-online"],
    queryFn: () => onlineUsers(),
    refetchInterval: 30000,
  });
  const onlineSet = new Set(onlineQuery.data?.user_ids ?? []);

  const [detail, setDetail] = useState<UserRead | null>(null);
  const [editing, setEditing] = useState<UserRead | null>(null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<UserStatusKey>(
    () => (readPref("users.status") as UserStatusKey) ?? "all",
  );
  const [sort, setSort] = useState<UserSortKey>(
    () => (readPref("users.sort") as UserSortKey) ?? "newest",
  );
  useEffect(() => writePref("users.status", statusFilter), [statusFilter]);
  useEffect(() => writePref("users.sort", sort), [sort]);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const toggleSel = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const clearSel = () => setSelected(new Set());
  const bulk = async (fn: (id: string) => Promise<unknown>, ok: string) => {
    const ids = [...selected];
    const results = await Promise.allSettled(ids.map(fn));
    const okc = results.filter((r) => r.status === "fulfilled").length;
    clearSel();
    refresh();
    qc.invalidateQueries({ queryKey: ["users-usage"] });
    if (okc === ids.length) toast("success", `${ok} (${okc}).`);
    else toast("error", `${okc}/${ids.length} done — some failed.`);
  };

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

  const needle = search.trim().toLowerCase();
  const filtered = users
    .filter((u) => (needle ? [u.username, u.email, u.role].some((v) => String(v).toLowerCase().includes(needle)) : true))
    .filter(matchStatus)
    .sort((a, b) => {
      const ua = usageMap.get(a.id)?.used_bytes ?? 0;
      const ub = usageMap.get(b.id)?.used_bytes ?? 0;
      switch (sort) {
        case "traffic": return ub - ua;
        case "expiring": return (a.expire_at ? Date.parse(a.expire_at) : Infinity) - (b.expire_at ? Date.parse(b.expire_at) : Infinity);
        case "name": return a.username.localeCompare(b.username);
        case "newest": return Date.parse(b.created_at) - Date.parse(a.created_at);
        default: return 0;
      }
    });

  const activeCount = users.filter((u) => {
    const lim = u.data_limit_bytes;
    const reached = lim != null && (usageMap.get(u.id)?.used_bytes ?? 0) >= lim;
    const expired = u.expire_at != null && Date.parse(u.expire_at) < now;
    return u.is_active && !reached && !expired;
  }).length;
  const onlineCount = users.filter((u) => onlineSet.has(u.id)).length;
  const expiredCount = users.filter((u) => u.expire_at != null && Date.parse(u.expire_at) < now).length;
  const limitedCount = users.filter((u) => {
    const lim = u.data_limit_bytes;
    return lim != null && (usageMap.get(u.id)?.used_bytes ?? 0) >= lim;
  }).length;
  const onHoldCount = users.filter((u) => u.on_hold).length;
  const disabledCount = users.filter((u) => !u.is_active).length;
  const usedTotal = users.reduce((s, u) => s + (usageMap.get(u.id)?.used_bytes ?? 0), 0);
  const maxUsed = users.reduce((m, u) => Math.max(m, usageMap.get(u.id)?.used_bytes ?? 0), 0);


  return (
    <div className="mx-auto w-full max-w-6xl">
      <WarpStatRow>
        <WarpStat label={query.hasNextPage ? "Loaded Users" : "Total Users"} value={query.hasNextPage ? `${users.length}+` : users.length} />
        <WarpStat label="Active" value={`${activeCount} / ${users.length}`} />
        <WarpStat label="Usage (loaded)" value={bytes(usedTotal)} />
      </WarpStatRow>

      {selected.size > 0 ? (
        <div className="warp-bulkbar">
          <span className="warp-bulk-count">{selected.size} selected</span>
          <span className="warp-bulk-sep" />
          <button type="button" className="warp-tb-button" onClick={() => bulk((id) => enableUser(id), "Enabled")}>
            <Power size={14} /> Enable
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulk((id) => disableUser(id), "Disabled")}>
            <Power size={14} /> Disable
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulk((id) => resetUserUsage(id), "Usage reset")}>
            <RotateCcw size={14} /> Reset usage
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-danger"
            onClick={async () => {
              if (await confirmDialog({ title: `Delete ${selected.size} user(s)?`, message: "This cannot be undone.", confirmLabel: "Delete", danger: true }))
                bulk((id) => deleteUser(id), "Deleted");
            }}
          >
            <Trash size={14} /> Delete
          </button>
          <button type="button" className="warp-tb-button warp-bulk-clear" onClick={clearSel}>Clear</button>
        </div>
      ) : null}

      <WarpTableCard
        toolbar={
          <>
            <WarpButton primary onClick={() => setCreating(true)}>
              <Plus size={14} /> Add User
            </WarpButton>
            <span className="warp-mini-stats" style={{ margin: 0 }}>
              <span className="warp-mstat is-green" title="Online users">online {onlineCount}</span>
              <span className="warp-mstat is-blue" title="On-hold users">on-hold {onHoldCount}</span>
              <span className="warp-mstat is-red" title="Data-limited users">limited {limitedCount}</span>
              <span className="warp-mstat is-amber" title="Expired users">expired {expiredCount}</span>
              <span className="warp-mstat is-red" title="Disabled users">disabled {disabledCount}</span>
            </span>
            <span className="warp-tb-spacer" />
            <span className="warp-tb-search-wrap" style={{ maxWidth: 220 }}>
              <Search size={13} />
              <input
                className="warp-tb-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search"
              />
            </span>
            <select
              className="warp-tb-search"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as UserStatusKey)}
              style={{ width: 140, minWidth: 0, flex: "none" }}
            >
              {USER_STATUS_CHIPS.map(([key, label]) => (
                <option key={key} value={key}>
                  {key === "all" ? "All statuses" : label}
                </option>
              ))}
            </select>
            <select
              className="warp-tb-search"
              value={sort}
              onChange={(e) => setSort(e.target.value as UserSortKey)}
              style={{ width: 140, minWidth: 0, flex: "none" }}
            >
              <option value="newest">Newest</option>
              <option value="traffic">Most traffic</option>
              <option value="expiring">Expiring soon</option>
              <option value="name">Name A–Z</option>
            </select>
          </>
        }
      >
        <WarpHead cols={["#", "Username", "Online", "Status", "Used Traffic", "Expiration"]} actions />
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
            const expired = u.expire_at != null && Date.parse(u.expire_at) < now;
            return (
              <div
                key={u.id}
                className="warp-tb-row"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  const row = e.currentTarget as HTMLElement & { _t?: number };
                  if (row._t) window.clearTimeout(row._t);
                  row._t = window.setTimeout(() => setDetail(u), 220);
                }}
                onDoubleClick={(e) => {
                  const row = e.currentTarget as HTMLElement & { _t?: number };
                  if (row._t) { window.clearTimeout(row._t); row._t = undefined; }
                  row.querySelector<HTMLButtonElement>(".warp-menu button")?.click();
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  (e.currentTarget as HTMLElement).querySelector<HTMLButtonElement>(".warp-menu button")?.click();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setDetail(u);
                  }
                }}
              >
                <span
                  className="warp-tb-cell"
                  onClick={(e) => { e.stopPropagation(); toggleSel(u.id); }}
                >
                  <span className="warp-tb-idcell">
                    <input
                      type="checkbox"
                      className="warp-tb-check"
                      checked={selected.has(u.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleSel(u.id)}
                      tabIndex={-1}
                    />
                    <span className="warp-tb-idnum">{idx + 1}</span>
                  </span>
                </span>
                <span className="warp-tb-cell font-medium">{u.username}</span>
                <span className="warp-tb-cell">
                  <span
                    className="warp-online-tag"
                    data-online={onlineSet.has(u.id) ? "true" : "false"}
                    title={onlineSet.has(u.id) ? "Online" : "Offline"}
                  >
                    {onlineSet.has(u.id) ? <Wifi size={14} /> : <WifiOff size={14} />}
                  </span>
                </span>
                <span className="warp-tb-cell">
                  {!u.is_active ? (
                    <WarpBadge tone="gray"><Ban size={13} /> Disabled</WarpBadge>
                  ) : reached ? (
                    <WarpBadge tone="red"><AlertCircle size={13} /> Limited</WarpBadge>
                  ) : expired ? (
                    <WarpBadge tone="orange"><Clock size={13} /> Expired</WarpBadge>
                  ) : u.on_hold ? (
                    <WarpBadge tone="blue"><Clock size={13} /> On-hold</WarpBadge>
                  ) : (
                    <WarpBadge tone="green"><Wifi size={13} /> Active</WarpBadge>
                  )}
                </span>
                <span className="warp-tb-cell">
                  <WarpTraffic
                    tone={!limit ? "unlimited" : used >= limit ? "danger" : "default"}
                    pct={limit ? (used / limit) * 100 : 0}
                    label={limit ? `${bytes(used)} / ${bytes(limit)}` : `${bytes(used)} / ∞`}
                  />
                </span>
                <span className="warp-tb-cell">
                  {(() => {
                    const rel = relativeExpiry(u.expire_at);
                    if (!rel) return <span className="text-fg-muted">Never</span>;
                    return <span className={rel.urgent ? "text-danger" : "text-fg-muted"}>{rel.text}</span>;
                  })()}
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
                        label: "Promote to admin",
                        icon: "shield-halved",
                        onClick: async () => {
                          if (await confirmDialog({ title: `Promote "${u.username}" to admin?`, message: "They will gain full panel access.", confirmLabel: "Promote" }))
                            act(() => promoteUser(u.id), "Promoted to admin.");
                        },
                      },
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

      {detail ? (
        <Drawer
          title={<span className="text-lg font-medium">Settings</span>}
          width="w-[720px]"
          panelClassName="bg-canvas"
          onClose={() => setDetail(null)}
        >
          <UserSettings
            key={detail.id}
            user={detail}
            used={usageMap.get(detail.id)?.used_bytes ?? 0}
            onReset={() => resetUsage(detail.id)}
            onToggle={() =>
              detail.is_active
                ? act(() => disableUser(detail.id), "User disabled.")
                : act(() => enableUser(detail.id), "User enabled.")
            }
          />
        </Drawer>
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
  ["info", "User Info"],
  ["services", "Services"],
  ["subscription", "Subscription"],
  ["nodes", "Nodes Usage"],
] as const;

function UserSettings({
  user,
  used,
  onReset,
  onToggle,
}: {
  user: UserRead;
  used: number;
  onReset: () => void;
  onToggle: () => void;
}) {
  const [tab, setTab] = useState<string>("info");
  const limit = user.data_limit_bytes;
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const expired = !!user.expire_at && new Date(user.expire_at).getTime() < Date.now();
  const reached = !!limit && used >= limit;
  const qc = useQueryClient();
  const lastSeenQuery = useQuery({
    queryKey: ["user-last-seen", user.id],
    queryFn: () => usersLastSeen([user.id]),
  });
  const lastSeen = lastSeenQuery.data?.[0]?.last_seen_at ?? null;
  const devicesQuery = useQuery({
    queryKey: ["user-devices", user.id],
    queryFn: () => listUserDevices(user.id),
  });
  const deviceCount = devicesQuery.data?.length ?? 0;
  const resetDevices = async () => {
    if (!(await confirmDialog({ title: "Reset registered devices?", message: "The user can reconnect from new devices.", confirmLabel: "Reset", danger: true }))) return;
    try {
      await resetUserDevices(user.id);
      toast("success", "Devices reset.");
      qc.invalidateQueries({ queryKey: ["user-devices", user.id] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Reset failed.");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="warp-usettings-tabs">
        {USER_TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn("warp-usettings-tab", tab === key && "is-active")}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "info" ? (
        <div>
          <div className="flex flex-row items-center justify-end gap-4 pb-3">
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" onClick={onReset} className="warp-tb-button">
                <RotateCcw size={14} aria-hidden />
                Reset Usage
              </button>
              <button
                type="button"
                onClick={onToggle}
                className={cn("warp-tb-button", user.is_active && "warp-tb-button-danger")}
              >
                <Power size={14} aria-hidden />
                {user.is_active ? "Disable" : "Enable"}
              </button>
            </div>
          </div>
          <div>
            <table className="w-full text-sm">
              <tbody>
                <URow label="Username" value={user.username} />
                <URow
                  label="Activated"
                  value={
                    !user.is_active ? (
                      <WarpBadge tone="red">Disabled</WarpBadge>
                    ) : reached ? (
                      <WarpBadge tone="red">Limited</WarpBadge>
                    ) : expired ? (
                      <WarpBadge tone="orange">Expired</WarpBadge>
                    ) : user.on_hold ? (
                      <WarpBadge tone="orange">Waiting</WarpBadge>
                    ) : (
                      <WarpBadge tone="green">Active</WarpBadge>
                    )
                  }
                />
                <URow
                  label="Enabled"
                  value={
                    <WarpBadge tone={user.is_active ? "green" : "red"}>
                      {user.is_active ? "Enabled" : "Disabled"}
                    </WarpBadge>
                  }
                />
                <URow
                  label="Data Limit Reached"
                  value={
                    <WarpBadge tone={reached ? "red" : "green"}>
                      {reached ? "Reached" : "Left"}
                    </WarpBadge>
                  }
                />
                <URow
                  label="Expired"
                  value={
                    <WarpBadge tone={expired ? "red" : "green"}>
                      {expired ? "Expired" : "Valid"}
                    </WarpBadge>
                  }
                />
                <URow
                  label="Expiration"
                  value={user.expire_at ? user.expire_at.slice(0, 10) : "Never"}
                />
                <URow
                  label="Used Traffic"
                  value={`${pct}% · ${bytes(used)} / ${limit ? bytes(limit) : "Unlimited"}`}
                />
                <URow
                  label="Last online"
                  value={lastSeen ? new Date(lastSeen).toLocaleString() : "Never connected"}
                />
                <URow
                  label="Devices"
                  value={
                    <span className="flex items-center gap-2">
                      <span>
                        {deviceCount}
                        {user.device_limit ? ` / ${user.device_limit}` : " · unlimited"}
                      </span>
                      {deviceCount > 0 ? (
                        <button type="button" className="warp-tb-button" style={{ height: 26, padding: "0 10px" }} onClick={resetDevices}>
                          Reset
                        </button>
                      ) : null}
                    </span>
                  }
                />
                <URow
                  label="Last subscription update"
                  value={
                    user.sub_updated_at ? new Date(user.sub_updated_at).toLocaleString() : "Never"
                  }
                />
                <URow label="Last User Agent" value={user.sub_last_user_agent || "No Use"} />
                <URow
                  label="Created At"
                  value={new Date(user.created_at).toLocaleString()}
                  last
                />
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {tab === "services" ? <AccessManager userId={user.id} /> : null}
      {tab === "subscription" ? <UserSubscriptionPanel userId={user.id} /> : null}
      {tab === "nodes" ? <UserNodesUsagePanel userId={user.id} /> : null}
    </div>
  );
}

function expireLabel(u: UserRead): string {
  if (u.expire_at) return u.expire_at.slice(0, 10);
  if (u.expire_strategy === "start_on_first_use") return "On first use";
  return "Never";
}

function relativeExpiry(expireAt: string | null): { text: string; urgent: boolean } | null {
  if (!expireAt) return null;
  const ms = new Date(expireAt).getTime() - Date.now();
  const past = ms < 0;
  const days = Math.floor(Math.abs(ms) / 86400000);
  const hours = Math.floor((Math.abs(ms) % 86400000) / 3600000);
  let span: string;
  if (days >= 1) span = `${days}d`;
  else if (hours >= 1) span = `${hours}h`;
  else span = "<1h";
  return {
    text: past ? `${span} ago` : `in ${span}`,
    urgent: past || ms < 7 * 86400000,
  };
}

function URow({
  label,
  value,
  last,
}: {
  label: string;
  value: React.ReactNode;
  last?: boolean;
}) {
  return (
    <tr>
      <td className="py-3 pr-4 align-middle font-normal text-fg-muted">{label}</td>
      <td className="py-3 align-middle font-normal text-fg">{value}</td>
    </tr>
  );
}

