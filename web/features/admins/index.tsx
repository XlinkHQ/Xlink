"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  deleteUser,
  demoteUser,
  disableAdminUsers,
  enableAdminUsers,
  listUsers,
  type UserRead,
} from "@/lib/api";
import {
  WarpButton,
  WarpEmpty,
  WarpError,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { AdminDialog } from "./dialog";
import { DgAddUser } from "@/components/console/dg-icons";
import { SearchBox } from "@/components/ui/search-box";
import { useT } from "@/lib/i18n";

export function AdminsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: ["admins"],
    queryFn: ({ pageParam }) => listUsers({ size: 50, cursor: pageParam, role: "admin" }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const admins = (query.data?.pages.flatMap((p) => p.items) ?? []) as UserRead[];
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<UserRead | "new" | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admins"] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["admin-usage"] });
  };
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast("success", ok);
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? admins.filter((a) => a.username.toLowerCase().includes(needle))
    : admins;


  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("admins.title")}</span>
        <div className="right">
          <SearchBox value={search} onChange={setSearch} placeholder={t("admins.findAdmin")} />
          <WarpButton primary onClick={() => setDialog("new")}>
            <DgAddUser size={16} /> {t("admins.addAdmin")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("admins.username"), t("common.status"), t("admins.permission"), t("common.created")]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : query.isError ? (
          <WarpError onRetry={() => query.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {search ? t("common.noMatches") : t("admins.noAdmins")}
          </WarpEmpty>
        ) : (
          filtered.map((a) => (
            <WarpRow
              key={a.id}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setDialog(a) },
                { label: t("admins.enableUsers"), icon: "enable", onClick: () => act(() => enableAdminUsers(a.id), t("admins.usersEnabled")) },
                { label: t("admins.disableUsers"), icon: "disable", onClick: () => act(() => disableAdminUsers(a.id), t("admins.usersDisabled")) },
                {
                  label: t("admins.demoteToUser"),
                  icon: "disable",
                  onClick: async () => {
                    if (await confirmDialog({ title: t("admins.demoteConfirmTitle", { username: a.username }), message: t("admins.demoteConfirmMessage"), confirmLabel: t("admins.demote") }))
                      act(() => demoteUser(a.id), t("admins.demoted"));
                  },
                },
                {
                  label: t("action.delete"),
                  icon: "delete",
                  danger: true,
                  onClick: async () => {
                    if (await confirmDialog({ title: t("admins.deleteConfirmTitle", { username: a.username }), confirmLabel: t("action.delete"), danger: true }))
                      act(() => deleteUser(a.id), t("admins.deleted"));
                  },
                },
              ]}
              cells={[
                <span className="font-medium">{a.username}</span>,
                <span className={`warp-badge ${a.is_active ? "success" : "critical"}`}>{a.is_active ? t("common.enabled") : t("common.disabled")}</span>,
                <span className={`warp-badge ${a.is_sudo ? "info" : "neutral"}`}>{a.is_sudo ? t("admins.sudo") : t("admins.standard")}</span>,
                <span className="text-fg-muted">{a.created_at.slice(0, 10)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {query.hasNextPage ? (
        <div className="flex flex-col items-center gap-1">
          {needle ? (
            <p className="text-[11px] text-fg-muted">
              {t("admins.searchLoadedOnly")}
            </p>
          ) : null}
          <Button
            variant="ghost"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? t("common.loading") : t("common.loadMore")}
          </Button>
        </div>
      ) : null}

      {dialog ? (
        <AdminDialog
          admin={dialog === "new" ? null : dialog}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}

