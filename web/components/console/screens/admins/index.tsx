"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, UserCheck, UserX } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  deleteUser,
  disableAdminUsers,
  enableAdminUsers,
  listUsers,
  type UserRead,
} from "@/lib/api";
import { bytes } from "@/lib/format";
import { Avatar, Drawer } from "../parts";
import {
  WarpBadge,
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpStat,
  WarpStatRow,
  WarpTableCard,
} from "../warp-table";
import { AdminDialog } from "./dialog";

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
  const [detail, setDetail] = useState<UserRead | null>(null);
  const [dialog, setDialog] = useState<UserRead | "new" | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["admins"] });
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

  const sudoCount = admins.filter((a) => a.is_sudo).length;
  const activeCount = admins.filter((a) => a.is_active).length;

  return (
    <div className="mx-auto w-full max-w-6xl">
      <WarpStatRow>
        <WarpStat label={query.hasNextPage ? "Loaded Admins" : "Total Admins"} value={query.hasNextPage ? `${admins.length}+` : admins.length} />
        <WarpStat label="Active" value={`${activeCount} / ${admins.length}`} />
        <WarpStat label="Sudo" value={sudoCount} />
      </WarpStatRow>

      <WarpTableCard
        toolbar={
          <>
            <WarpButton primary onClick={() => setDialog("new")}>
              <Plus size={14} /> Add Admin
            </WarpButton>
            <input
              className="warp-tb-search warp-tb-spacer"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search admins…"
            />
          </>
        }
      >
        <WarpHead cols={["#", "Username", "Status", "Permission", "Created"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-user-shield">
            {search ? "No matches." : "No admins yet."}
          </WarpEmpty>
        ) : (
          filtered.map((a, i) => (
            <WarpRow
              key={a.id}
              onClick={() => setDetail(a)}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setDialog(a) },
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
                i + 1,
                <span className="font-medium">{a.username}</span>,
                <WarpBadge tone={a.is_active ? "green" : "red"}>{a.is_active ? "Enabled" : "Disabled"}</WarpBadge>,
                <WarpBadge tone={a.is_sudo ? "blue" : "orange"}>{a.is_sudo ? "Sudo" : "Standard"}</WarpBadge>,
                a.created_at.slice(0, 10),
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

      {detail ? (
        <Drawer
          title={<span className="text-lg font-medium">Settings</span>}
          width="w-[720px]"
          panelClassName="bg-canvas"
          onClose={() => setDetail(null)}
        >
          <div>
            <div className="flex flex-row items-center justify-end gap-4 pb-4">
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={async () => {
                    await act(() => enableAdminUsers(detail.id), "Enabled this admin's users.");
                    setDetail(null);
                  }}
                  className="warp-tb-button"
                >
                  <UserCheck size={14} aria-hidden />
                  Enable users
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await act(() => disableAdminUsers(detail.id), "Disabled this admin's users.");
                    setDetail(null);
                  }}
                  className="warp-tb-button warp-tb-button-danger"
                >
                  <UserX size={14} aria-hidden />
                  Disable users
                </button>
              </div>
            </div>

            <div className="px-5 py-2">
              <table className="w-full text-sm">
                <tbody>
                  <InfoRow label="Username" value={detail.username} />
                  <InfoRow
                    label="Status"
                    value={
                      <WarpBadge tone={detail.is_active ? "green" : "red"}>
                        {detail.is_active ? "Enabled" : "Disabled"}
                      </WarpBadge>
                    }
                  />
                  <InfoRow
                    label="Permission"
                    value={
                      <WarpBadge tone={detail.is_sudo ? "blue" : "orange"}>
                        {detail.is_sudo ? "Sudo" : "Standard"}
                      </WarpBadge>
                    }
                  />
                  <InfoRow label="Created" value={detail.created_at.slice(0, 10)} />
                  <InfoRow label="Users Data Usage" value={bytes(detail.users_data_usage)} last />
                </tbody>
              </table>
            </div>
          </div>
        </Drawer>
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

function InfoRow({
  label,
  value,
  last,
}: {
  label: string;
  value: ReactNode;
  last?: boolean;
}) {
  return (
    <tr>
      <td className="py-2.5 pr-4 align-middle font-normal text-fg-muted">{label}</td>
      <td className="py-2.5 align-middle font-normal text-fg">{value}</td>
    </tr>
  );
}

