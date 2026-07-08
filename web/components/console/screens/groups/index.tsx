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
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "../warp-table";
import { Plus } from "lucide-react";
import { DgSearch } from "../../dg-icons";
import { GroupDialog } from "./dialog";
import { ServiceSettings } from "./settings";

export function GroupsScreen() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["groups"], queryFn: () => listGroups() });
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const nodesQuery = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  // listAllAssignments walks the cursor — a single page misses members past 100.
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
  if (detail) {
    return (
      <>
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
      </>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">All services</span>
        <div className="right">
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Find service"
            />
          </span>
          <WarpButton primary onClick={() => setEditing("new")}>
            <Plus size={16} strokeWidth={1.8} /> Add Service
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Name", "Users", "Inbounds"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-layer-group">
            {search ? "No matches." : "No services yet."}
          </WarpEmpty>
        ) : (
          filtered.map((g) => (
            <WarpRow
              key={g.id}
              onClick={() => setDetail(g)}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setEditing(g) },
                { label: "Delete", icon: "delete", danger: true, onClick: () => remove(g) },
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
