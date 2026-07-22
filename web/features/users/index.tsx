"use client";

import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Gauge, Power, RefreshCw, RotateCcw, Trash } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
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
  resetUserUsage,
  restoreUser,
  revokeSubscription,
  type UserRead,
  usersUsage,
  userSubscriptionUrl,
} from "@/lib/api";
import { bytes } from "@/lib/format";
import { userStatus } from "@/lib/status";
import {
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpMenu,
  WarpSkeleton,
  WarpTableCard,
  WarpRadial,
} from "@/shared/warp-table";
import { copyText } from "@/lib/clipboard";
import { EditUserDialog, UserDialog } from "./dialogs";
import { DgAddUser } from "@/components/console/dg-icons";
import { SearchBox } from "@/components/ui/search-box";
import { readPref, writePref, relTimeShort } from "./helpers";
import { Badge, UserNameCell, SortTh, type SortCol, type SortDir } from "./components";
import { UserProfileView } from "./UserProfileView";
import { BulkEditModal } from "./BulkEditModal";

type UserStatusKey = "all" | "online" | "active" | "expired" | "disabled" | "limited";

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
      const s = userStatus(u, used);
      switch (statusFilter) {
        case "online": return onlineSet.has(u.id);
        case "active": return u.is_active && !expired && !reached;
        case "disabled": return s === "disabled";
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
