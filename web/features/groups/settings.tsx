"use client";
import { protoBadge } from "@/lib/proto";

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
import { userStatus } from "@/lib/status";
import { cn } from "@/lib/cn";
import { WarpEmpty, WarpError, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { useT } from "@/lib/i18n";

const PAGE_SIZE = 10;

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
  editing?: boolean;
  editForm?: React.ReactNode;
}) {
  const t = useT();
  const [tab, setTab] = useState<"inbounds" | "users">("inbounds");

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-breadcrumbs">
        <div className="track">
          <button
            type="button"
            className="warp-breadcrumbs-back"
            aria-label={t("action.back")}
            onClick={onClose}
          >
            <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
          </button>
          <span className="warp-breadcrumbs-divider" />
          <div className="links">
            <button type="button" className="crumb" onClick={onClose}>
              {t("groups.services")}
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
              <Pencil size={14} aria-hidden /> {t("action.edit")}
            </button>
          </div>
        </div>
      </div>
      <div className="warp-pd-tabs warp-profile-tabs">
        {([["inbounds", t("groups.inbounds")], ["users", t("groups.users")]] as const).map(([key, label]) => (
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
  const t = useT();
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
      setSelected(prev);
      toast("error", e instanceof ApiError ? e.message : t("common.updateFailed"));
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
            t("groups.tag"),
            t("profiles.protocol"),
            t("groups.nodes"),
          ]}
        />
        {rows.length === 0 ? (
          <WarpEmpty>{t("groups.noInboundsAvailable")}</WarpEmpty>
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
          {busy ? t("common.saving") : t("groups.selectedCount", { n: selected.size, total: profiles.length })}
        </span>
        <div className="flex items-center gap-1">
          <span className="mr-2">
            {t("common.pageOf", { page: page + 1, total: pageCount })}
          </span>
          <PageBtn onClick={() => setPage(0)} disabled={page === 0} aria-label={t("common.firstPage")}>
            <ChevronsLeft className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} aria-label={t("common.previousPage")}>
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
            aria-label={t("common.nextPage")}
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </PageBtn>
          <PageBtn onClick={() => setPage(pageCount - 1)} disabled={page >= pageCount - 1} aria-label={t("common.lastPage")}>
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
  const t = useT();
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

  return (
    <WarpTableCard className="warp-users-table">
      <WarpHead cols={[t("groups.username"), t("groups.online"), t("common.status"), t("groups.usedTraffic"), t("groups.expiration")]} />
      {usersQuery.isLoading ? (
        <WarpSkeleton />
      ) : usersQuery.isError ? (
        <WarpError onRetry={() => usersQuery.refetch()} />
      ) : members.length === 0 ? (
        <WarpEmpty>{t("groups.noUsersYet")}</WarpEmpty>
      ) : (
        members.map((u) => {
          const s = userStatus(u);
          const statusClass =
            s === "disabled" ? "critical"
              : s === "onhold" ? "warning"
              : s === "expired" ? "critical"
              : s === "limited" ? "critical"
              : "success";
          const statusText =
            s === "disabled" ? t("groups.statusDisabled")
              : s === "onhold" ? t("groups.statusOnhold")
              : s === "expired" ? t("groups.statusExpired")
              : s === "limited" ? t("groups.statusLimited")
              : t("groups.statusActive");
          return (
            <WarpRow
              key={u.id}
              cells={[
                <span className="font-medium">{u.username}</span>,
                <span className={`warp-badge ${onlineSet.has(u.id) ? "success" : "neutral"}`}>
                  {onlineSet.has(u.id) ? t("groups.online") : t("groups.offline")}
                </span>,
                <span className={`warp-badge ${statusClass}`}>
                  {statusText}
                </span>,
                <span className="text-fg-muted">{bytes(u.users_data_usage ?? 0)}</span>,
                <span className="text-fg-muted">{u.expire_at ? u.expire_at.slice(0, 10) : t("groups.never")}</span>,
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
