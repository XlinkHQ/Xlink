"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  type AssignmentRead,
  deleteGroup,
  type GroupRead,
  listAllAssignments,
  listGroups,
  listNodes,
  listProfiles,
  type NodeRead,
  type ProfileRead,
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
import { Plus } from "lucide-react";
import { DgSearch } from "@/components/console/dg-icons";
import { GroupDialog } from "./dialog";
import { ServiceSettings } from "./settings";
import { useT } from "@/lib/i18n";

export function GroupsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const nodesQuery = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const assignmentsQuery = useQuery({ queryKey: ["assignments"], queryFn: () => listAllAssignments() });
  const groups = query.data ?? [];
  const profiles = (profilesQuery.data?.items ?? []) as ProfileRead[];
  const nodes = (nodesQuery.data?.items ?? []) as NodeRead[];
  const assignments = (assignmentsQuery.data ?? []) as AssignmentRead[];
  const nodeName = (id: string) => nodes.find((n) => n.id === id)?.name ?? id.slice(0, 8);

  const usersForGroup = (g: GroupRead) => {
    const inbounds = new Set(g.profile_ids);
    const users = new Set<string>();
    for (const a of assignments) if (inbounds.has(a.profile_id)) users.add(a.user_id);
    return users.size;
  };

  const [editing, setEditing] = useState<GroupRead | "new" | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [editInline, setEditInline] = useState(false);
  const [search, setSearch] = useState("");
  const detail = detailId ? (groups.find((g) => g.id === detailId) ?? null) : null;

  const refresh = () => qc.invalidateQueries({ queryKey: ["groups"] });
  const remove = async (g: GroupRead) => {
    if (!(await confirmDialog({ title: t("groups.deleteConfirm", { name: g.name }), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteGroup(g.id);
      toast("success", t("groups.deleted"));
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.deleteFailed"));
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle ? groups.filter((g) => g.name.toLowerCase().includes(needle)) : groups;
  if (detail) {
    return (
      <ServiceSettings
        group={detail}
        profiles={profiles}
        nodeName={nodeName}
        assignments={assignments}
        onClose={() => {
          setDetailId(null);
          setEditInline(false);
        }}
        editing={editInline}
        onEdit={() => setEditInline((v) => !v)}
        editForm={
          editInline ? (
            <GroupDialog
              variant="inline"
              group={detail}
              profiles={profiles}
              nodeName={nodeName}
              onClose={() => setEditInline(false)}
              onSaved={() => {
                setEditInline(false);
                refresh();
              }}
            />
          ) : null
        }
        onSaved={refresh}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("groups.allServices")}</span>
        <div className="right">
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("groups.findService")}
            />
          </span>
          <WarpButton primary onClick={() => setEditing("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("groups.addService")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("groups.users"), t("groups.inbounds")]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : query.isError ? (
          <WarpError onRetry={() => query.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {search ? t("common.noMatches") : t("groups.noServicesYet")}
          </WarpEmpty>
        ) : (
          filtered.map((g) => (
            <WarpRow
              key={g.id}
              onClick={() => setDetailId(g.id)}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setEditing(g) },
                { label: t("action.delete"), icon: "delete", danger: true, onClick: () => remove(g) },
              ]}
              cells={[
                <span className="font-medium">{g.name}</span>,
                <span className="warp-badge info">{usersForGroup(g)}</span>,
                <span className="warp-badge success">{g.profile_ids.length}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {editing ? (
        <GroupDialog
          group={editing === "new" ? null : editing}
          profiles={profiles}
          nodeName={nodeName}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}
