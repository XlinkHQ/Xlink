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
  WarpError,
  WarpHead,
  WarpMenu,
  WarpSkeleton,
  WarpTableCard,
  WarpRadial,
  type WarpMenuItem,
} from "@/shared/warp-table";
import { copyText } from "@/lib/clipboard";
import { EditUserDialog, UserDialog } from "./dialogs";
import { DgAddUser } from "@/components/console/dg-icons";
import { SearchBox } from "@/components/ui/search-box";
import { readPref, writePref, relTimeShort } from "./helpers";
import { Badge, UserNameCell, SortTh, type SortCol, type SortDir } from "./components";
import { UserProfileView } from "./UserProfileView";
import { BulkEditModal } from "./BulkEditModal";
import { useUserFilters } from "./useUserFilters";
import { useT } from "@/lib/i18n";

type UserStatusKey = "all" | "online" | "active" | "expired" | "disabled" | "limited";

export function UsersScreen() {
  const t = useT();
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
      else toast("error", t("users.bulkPartial", { ok: res.ok, total: ids.length, failed: res.failed }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("users.bulkFailed"));
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
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
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
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
    }
  };

  const copyId = async (id: string) => {
    const ok = await copyText(id);
    toast(ok ? "success" : "error", ok ? t("users.userIdCopied") : t("common.copyFailed"));
  };
  const copySub = async (id: string) => {
    let url: string;
    try {
      url = (await userSubscriptionUrl(id)).subscription_url;
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("users.couldNotGetSubLink"));
      return;
    }
    const ok = await copyText(url);
    toast(ok ? "success" : "error", ok ? t("users.subLinkCopied") : t("common.copyFailed"));
  };
  const resetUsage = async (id: string) => {
    if (!(await confirmDialog({ title: t("users.resetUsageTitle"), message: t("users.resetUsageMessage"), confirmLabel: t("action.reset"), danger: true }))) return;
    try {
      await resetUserUsage(id);
      toast("success", t("users.usageReset"));
      qc.invalidateQueries({ queryKey: ["a-traffic"] });
      qc.invalidateQueries({ queryKey: ["assignments"] });
      qc.invalidateQueries({ queryKey: ["users-usage"] });
      qc.invalidateQueries({ queryKey: ["traffic"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("users.resetFailed"));
    }
  };

  const revoke = async (id: string) => {
    if (!(await confirmDialog({ title: t("users.revokeSubTitle"), message: t("users.revokeSubMessage"), confirmLabel: t("action.revoke"), danger: true })))
      return;
    try {
      await revokeSubscription(id);
      toast("success", t("users.subRevoked"));
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["sub-url"] });
      qc.invalidateQueries({ queryKey: ["sub-links"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
    }
  };

  const restore = async (id: string) => {
    try {
      await restoreUser(id);
      toast("success", t("users.userRestored"));
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("users.restoreFailed"));
    }
  };

  const needle = search.trim().toLowerCase();
  const { filtered, maxUsed } = useUserFilters({
    users,
    search,
    statusFilter,
    sortCol,
    sortDir,
    usageMap,
    onlineSet,
  });

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
            ? act(() => disableUser(live.id), t("users.userDisabled"))
            : act(() => enableUser(live.id), t("users.userEnabled"))
        }
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      {selected.size > 0 ? (
        <div className="warp-bulkbar">
          <span className="warp-bulk-count">{t("users.selectedCount", { n: selected.size })}</span>
          <span className="warp-bulk-sep" />
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("enable", t("users.enabled"))}>
            <Power size={14} aria-hidden /> {t("action.enable")}
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("disable", t("users.disabled"))}>
            <Power size={14} aria-hidden /> {t("action.disable")}
          </button>
          <button type="button" className="warp-tb-button" onClick={() => bulkServer("reset_usage", t("users.usageReset"))}>
            <RotateCcw size={14} aria-hidden /> {t("users.resetUsage")}
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("limit")}>
            <Gauge size={14} aria-hidden /> {t("users.dataLimit")}
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("expiry")}>
            <CalendarClock size={14} aria-hidden /> {t("users.expiry")}
          </button>
          <button type="button" className="warp-tb-button" onClick={() => setBulkEdit("reset")}>
            <RefreshCw size={14} aria-hidden /> {t("users.autoReset")}
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-danger"
            onClick={async () => {
              if (await confirmDialog({ title: t("users.deleteManyTitle", { n: selected.size }), message: t("common.cannotBeUndone"), confirmLabel: t("action.delete"), danger: true }))
                bulkServer("delete", t("users.deleted"));
            }}
          >
            <Trash size={14} aria-hidden /> {t("action.delete")}
          </button>
          <button type="button" className="warp-tb-button warp-bulk-clear" onClick={clearSel}>{t("action.clear")}</button>
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
        <span className="title">{t("users.allUsers")}</span>
        <div className="right">
          <label className="flex cursor-pointer select-none items-center gap-1.5 text-[13px] text-fg-muted">
            <input
              type="checkbox"
              className="warp-tb-check"
              checked={showRemoved}
              onChange={(e) => setShowRemoved(e.target.checked)}
            />
            {t("users.showRemoved")}
          </label>
          <SearchBox value={search} onChange={setSearch} placeholder={t("users.findUser")} />
          <WarpButton primary onClick={() => setCreating(true)}>
            <DgAddUser size={18} aria-hidden /> {t("users.addNewUser")}
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
              aria-label={t("users.selectAll")}
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
            <SortTh key="username" col="username" label={t("users.username")} sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            <SortTh key="status" col="status" label={t("common.status")} sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            t("users.lastSeen"),
            <SortTh key="traffic" col="traffic" label={t("users.usedTraffic")} sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
            <SortTh key="expiration" col="expiration" label={t("users.expiration")} sortCol={sortCol} sortDir={sortDir} onSort={toggleSort} />,
          ]}
          actions
        />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : query.isError ? (
          <WarpError onRetry={() => query.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {needle || statusFilter !== "all" ? t("users.noMatches") : t("users.noUsersYet")}
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
                    <Badge variant="neutral">{t("users.status.removed")}</Badge>
                  ) : !u.is_active ? (
                    <Badge variant="critical">{t("users.status.disabled")}</Badge>
                  ) : expired ? (
                    <Badge variant="critical">{t("users.status.expired")}</Badge>
                  ) : reached || u.on_hold ? (
                    <Badge variant="warning">{reached ? t("users.status.limited") : t("users.status.onHold")}</Badge>
                  ) : (
                    <Badge variant="success">{t("users.status.active")}</Badge>
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
                      ...(u.removed ? [{ label: t("action.restore"), icon: "restore", onClick: () => restore(u.id) } as WarpMenuItem] : []),
                      { label: t("action.edit"), icon: "edit", onClick: () => setEditing(u) },
                      { label: t("users.copyId"), icon: "copy-id", onClick: () => copyId(u.id) },
                      { label: t("users.copySubscription"), icon: "copy-link", onClick: () => copySub(u.id) },
                      { label: t("users.resetUsage"), icon: "reset-usage", onClick: () => resetUsage(u.id) },
                      { label: t("users.revokeSubscription"), icon: "revoke", onClick: () => revoke(u.id) },
                      u.is_active
                        ? { label: t("action.disable"), icon: "disable", onClick: () => setActiveOptimistic(u.id, false, () => disableUser(u.id), t("users.userDisabled")) }
                        : { label: t("action.enable"), icon: "enable", onClick: () => setActiveOptimistic(u.id, true, () => enableUser(u.id), t("users.userEnabled")) },
                      {
                        label: t("action.remove"),
                        icon: "delete",
                        danger: true,
                        onClick: async () => {
                          if (await confirmDialog({ title: t("users.deleteUserTitle", { name: u.username }), message: t("common.cannotBeUndone"), confirmLabel: t("action.delete"), danger: true }))
                            act(() => deleteUser(u.id), t("users.userDeleted"));
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
              {t("users.searchLoadedHint")}
            </p>
          ) : null}
          <Button
            variant="outline"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? t("common.loading") : t("action.loadMore")}
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
