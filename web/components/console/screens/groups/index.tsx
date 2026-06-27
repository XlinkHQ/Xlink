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
  listAssignments,
  listGroups,
  listNodes,
  listProfiles,
  type NodeRead,
  type ProfileRead,
} from "@/lib/api";
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
import { Plus } from "lucide-react";
import { GroupDialog } from "./dialog";
import { ServiceSettings } from "./settings";

export function GroupsScreen() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const nodesQuery = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const assignmentsQuery = useQuery({ queryKey: ["assignments"], queryFn: () => listAssignments() });
  const groups = query.data ?? [];
  const profiles = (profilesQuery.data?.items ?? []) as ProfileRead[];
  const nodes = (nodesQuery.data?.items ?? []) as NodeRead[];
  const assignments = (assignmentsQuery.data?.items ?? []) as AssignmentRead[];
  const nodeName = (id: string) => nodes.find((n) => n.id === id)?.name ?? id.slice(0, 8);

  const usersForGroup = (g: GroupRead) => {
    const inbounds = new Set(g.profile_ids);
    const users = new Set<string>();
    for (const a of assignments) if (inbounds.has(a.profile_id)) users.add(a.user_id);
    return users.size;
  };

  const [editing, setEditing] = useState<GroupRead | "new" | null>(null);
  const [detail, setDetail] = useState<GroupRead | null>(null);
  const [search, setSearch] = useState("");

  const refresh = () => qc.invalidateQueries({ queryKey: ["groups"] });
  const remove = async (g: GroupRead) => {
    if (!(await confirmDialog({ title: `Delete service "${g.name}"?`, confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteGroup(g.id);
      toast("success", "Service deleted.");
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle ? groups.filter((g) => g.name.toLowerCase().includes(needle)) : groups;
  const totalInbounds = groups.reduce((n, g) => n + g.profile_ids.length, 0);
  const totalUsers = (() => {
    const ids = new Set<string>();
    const inbounds = new Set(groups.flatMap((g) => g.profile_ids));
    for (const a of assignments) if (inbounds.has(a.profile_id)) ids.add(a.user_id);
    return ids.size;
  })();

  return (
    <div className="mx-auto w-full max-w-6xl">
      <WarpStatRow>
        <WarpStat label="Total Services" value={groups.length} />
        <WarpStat label="Total Users" value={totalUsers} />
        <WarpStat label="Total Inbounds" value={totalInbounds} />
      </WarpStatRow>

      <WarpTableCard
        toolbar={
          <>
            <WarpButton primary onClick={() => setEditing("new")}>
              <Plus size={14} /> Add Service
            </WarpButton>
            <input
              className="warp-tb-search warp-tb-spacer"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search services…"
            />
          </>
        }
      >
        <WarpHead cols={["#", "Name", "Users", "Inbounds"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-layer-group">
            {search ? "No matches." : "No services yet."}
          </WarpEmpty>
        ) : (
          filtered.map((g, i) => (
            <WarpRow
              key={g.id}
              onClick={() => setDetail(g)}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setEditing(g) },
                { label: "Delete", icon: "delete", danger: true, onClick: () => remove(g) },
              ]}
              cells={[
                i + 1,
                <span className="font-medium">{g.name}</span>,
                <WarpBadge tone="blue">{usersForGroup(g)}</WarpBadge>,
                <WarpBadge tone="green">{g.profile_ids.length}</WarpBadge>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {detail ? (
        <ServiceSettings
          group={detail}
          profiles={profiles}
          nodeName={nodeName}
          assignments={assignments}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setEditing(detail);
            setDetail(null);
          }}
          onSaved={() => {
            refresh();
            setDetail(null);
          }}
        />
      ) : null}

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
