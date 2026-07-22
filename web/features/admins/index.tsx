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
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { AdminDialog } from "./dialog";
import { DgAddUser } from "@/components/console/dg-icons";
import { SearchBox } from "@/components/ui/search-box";

export function AdminsScreen() {
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
    // enable/disable/demote change the admin's USERS' active state + usage view.
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
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? admins.filter((a) => a.username.toLowerCase().includes(needle))
    : admins;


  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">All admins</span>
        <div className="right">
          <SearchBox value={search} onChange={setSearch} placeholder="Find admin" />
          <WarpButton primary onClick={() => setDialog("new")}>
            <DgAddUser size={16} /> Add Admin
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Username", "Status", "Permission", "Created"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-user-shield">
            {search ? "No matches." : "No admins yet."}
          </WarpEmpty>
        ) : (
          filtered.map((a) => (
            <WarpRow
              key={a.id}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setDialog(a) },
                { label: "Enable users", icon: "enable", onClick: () => act(() => enableAdminUsers(a.id), "Enabled this admin's users.") },
                { label: "Disable users", icon: "disable", onClick: () => act(() => disableAdminUsers(a.id), "Disabled this admin's users.") },
                {
                  label: "Demote to user",
                  icon: "disable",
                  onClick: async () => {
                    if (await confirmDialog({ title: `Demote "${a.username}" to a regular user?`, message: "They lose all admin access.", confirmLabel: "Demote" }))
                      act(() => demoteUser(a.id), "Admin demoted to user.");
                  },
                },
                {
                  label: "Delete",
                  icon: "delete",
                  danger: true,
                  onClick: async () => {
                    if (await confirmDialog({ title: `Delete admin "${a.username}"?`, confirmLabel: "Delete", danger: true }))
                      act(() => deleteUser(a.id), "Admin deleted.");
                  },
                },
              ]}
              cells={[
                <span className="font-medium">{a.username}</span>,
                <span className={`warp-badge ${a.is_active ? "success" : "critical"}`}>{a.is_active ? "Enabled" : "Disabled"}</span>,
                <span className={`warp-badge ${a.is_sudo ? "info" : "neutral"}`}>{a.is_sudo ? "Sudo" : "Standard"}</span>,
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
              Searching loaded admins only — load more to widen the search.
            </p>
          ) : null}
          <Button
            variant="ghost"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load more"}
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

