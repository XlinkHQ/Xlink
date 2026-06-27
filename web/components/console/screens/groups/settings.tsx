"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  type AssignmentRead,
  type GroupRead,
  listUsers,
  type ProfileRead,
  updateGroup,
  type UserRead,
} from "@/lib/api";
import { bytes } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Drawer } from "../parts";

const TABS = [
  ["inbounds", "Inbounds"],
  ["users", "Users"],
] as const;
const PAGE_SIZE = 10;

export function ServiceSettings({
  group,
  profiles,
  nodeName,
  assignments,
  onClose,
  onEdit,
  onSaved,
}: {
  group: GroupRead;
  profiles: ProfileRead[];
  nodeName: (id: string) => string;
  assignments: AssignmentRead[];
  onClose: () => void;
  onEdit: () => void;
  onSaved: () => void;
}) {
  const [tab, setTab] = useState<string>("inbounds");

  return (
    <Drawer title="Settings" width="w-[720px]" onClose={onClose} onEdit={onEdit}>
      <div className="warp-usettings-tabs">
        {TABS.map(([key, label]) => (
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

      <div className="mt-4">
        {tab === "inbounds" ? (
          <InboundsTab group={group} profiles={profiles} nodeName={nodeName} onSaved={onSaved} />
        ) : null}
        {tab === "users" ? <UsersTab group={group} assignments={assignments} /> : null}
      </div>
    </Drawer>
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

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const toggleAll = () =>
    setSelected((s) => {
      const n = new Set(s);
      if (allOnPage) rows.forEach((p) => n.delete(p.id));
      else rows.forEach((p) => n.add(p.id));
      return n;
    });

  const apply = async () => {
    setBusy(true);
    try {
      await updateGroup(group.id, { name: group.name, profile_ids: [...selected] });
      toast("success", "Service inbounds updated.");
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-lg border border-hairline">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-hairline text-left">
              <th className="w-10 px-3 py-2.5">
                <CheckBox checked={allOnPage} onChange={toggleAll} />
              </th>
              <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Tag</th>
              <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Protocol</th>
              <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Nodes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.id}
                onClick={() => toggle(p.id)}
                className="cursor-pointer border-b border-hairline transition-colors last:border-0 hover:bg-muted"
              >
                <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                  <CheckBox checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
                </td>
                <td className="px-3 py-2.5 font-medium text-fg">{p.name}</td>
                <td className="px-3 py-2.5">
                  <Badge tone="neutral">{p.protocol}</Badge>
                </td>
                <td className="px-3 py-2.5">
                  <Badge tone="muted">{nodeName(p.node_id)}</Badge>
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-xs text-fg-muted">
                  No inbounds available.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 text-xs text-fg-muted">
        <span>
          {selected.size} / {profiles.length} selected
        </span>
        <div className="flex items-center gap-1">
          <span className="mr-2">
            Page {page + 1} of {pageCount}
          </span>
          <PageBtn onClick={() => setPage(0)} disabled={page === 0}>
            <ChevronsLeft className="h-4 w-4" />
          </PageBtn>
          <PageBtn onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
            <ChevronLeft className="h-4 w-4" />
          </PageBtn>
          <PageBtn
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
          >
            <ChevronRight className="h-4 w-4" />
          </PageBtn>
          <PageBtn onClick={() => setPage(pageCount - 1)} disabled={page >= pageCount - 1}>
            <ChevronsRight className="h-4 w-4" />
          </PageBtn>
        </div>
      </div>

      <button
        type="button"
        className="warp-tb-button warp-tb-button-primary flex w-full justify-center"
        onClick={apply}
        disabled={busy}
      >
        {busy ? "Applying…" : "Apply"}
      </button>
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
  const usersQuery = useQuery({ queryKey: ["users", "all"], queryFn: () => listUsers({ size: 500 }) });
  const users = (usersQuery.data?.items ?? []) as UserRead[];
  const members = useMemo(() => {
    const inbounds = new Set(group.profile_ids);
    const ids = new Set<string>();
    for (const a of assignments) if (inbounds.has(a.profile_id)) ids.add(a.user_id);
    return users.filter((u) => ids.has(u.id));
  }, [group.profile_ids, assignments, users]);

  return (
    <div className="overflow-hidden rounded-lg border border-hairline">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-hairline text-left">
            <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Username</th>
            <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Activated</th>
            <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Used Traffic</th>
            <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Expire Date</th>
          </tr>
        </thead>
        <tbody>
          {members.map((u) => (
            <tr key={u.id} className="border-b border-hairline last:border-0">
              <td className="px-3 py-2.5 font-medium text-fg">{u.username}</td>
              <td className="px-3 py-2.5">
                <Badge tone={u.is_active ? "success" : "muted"}>
                  {u.is_active ? "Active" : "Disabled"}
                </Badge>
              </td>
              <td className="px-3 py-2.5 text-fg-muted">{bytes(u.users_data_usage ?? 0)}</td>
              <td className="px-3 py-2.5 text-fg-muted">
                {u.expire_at ? u.expire_at.slice(0, 10) : "—"}
              </td>
            </tr>
          ))}
          {members.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-3 py-8 text-center text-xs text-fg-muted">
                No users in this service yet.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
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
}: {
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="grid h-7 w-7 place-items-center rounded-md border border-hairline text-fg-muted transition-colors hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
