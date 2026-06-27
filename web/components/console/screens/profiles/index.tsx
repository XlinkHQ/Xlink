"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Plus, Trash } from "lucide-react";
import {
  ApiError,
  deleteInboundHost,
  deleteProfile,
  disableProfile,
  type InboundHostRead,
  listInboundHosts,
  listNodes,
  listProfiles,
  type NodeRead,
  profileUsageSeries,
  profileUsageTotal,
  type ProfileRead,
} from "@/lib/api";
import { bytes } from "@/lib/format";
import { Drawer } from "../parts";
import { UsageAreaChart } from "../usage-chart";
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
import { ProfileDialog } from "./dialog";
import { HostDialog } from "./host-dialog";

function protoBadge(p: string): string {
  switch (p.toLowerCase()) {
    case "vless": return "is-blue";
    case "vmess": return "is-indigo";
    case "trojan": return "is-pink";
    case "shadowsocks": return "is-purple";
    case "wireguard": return "is-orange";
    case "hysteria":
    case "hysteria2": return "is-teal";
    case "tuic": return "is-cyan";
    default: return "is-slate";
  }
}

export function ProfilesScreen() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["profiles"], queryFn: () => listProfiles() });
  const nodesQuery = useQuery({ queryKey: ["nodes"], queryFn: () => listNodes() });
  const hostsQuery = useQuery({ queryKey: ["inbound-hosts", "all"], queryFn: () => listInboundHosts() });
  const profiles = (query.data?.items ?? []) as ProfileRead[];
  const nodes = (nodesQuery.data?.items ?? []) as NodeRead[];
  const allHosts = (hostsQuery.data ?? []) as InboundHostRead[];
  const nodeName = (id: string) => nodes.find((n) => n.id === id)?.name ?? id.slice(0, 8);
  const hostCount = (profileId: string) => allHosts.filter((h) => h.profile_id === profileId).length;

  const [search, setSearch] = useState("");
  const [editingInbound, setEditingInbound] = useState<ProfileRead | "new" | null>(null);
  const [detail, setDetail] = useState<ProfileRead | null>(null);

  const refreshInbounds = () => {
    qc.invalidateQueries({ queryKey: ["profiles"] });
    qc.invalidateQueries({ queryKey: ["inbound-hosts", "all"] });
  };

  const disableInbound = async (p: ProfileRead) => {
    if (!(await confirmDialog({ title: `Disable inbound "${p.name}"?`, confirmLabel: "Disable", danger: true }))) return;
    try {
      await disableProfile(p.id);
      toast("success", "Inbound disabled.");
      refreshInbounds();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const removeInbound = async (p: ProfileRead) => {
    if (!(await confirmDialog({ title: `Delete inbound "${p.name}"?`, message: "This permanently removes it. Assignments must be removed first.", confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteProfile(p.id);
      toast("success", "Inbound deleted.");
      refreshInbounds();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed.");
    }
  };

  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? profiles.filter((p) =>
        [p.name, p.protocol, nodeName(p.node_id)].some((v) =>
          String(v).toLowerCase().includes(needle),
        ),
      )
    : profiles;
  const totalHosts = allHosts.length;

  return (
    <div className="mx-auto w-full max-w-6xl">
      <WarpStatRow>
        <WarpStat label="Inbounds" value={profiles.length} />
        <WarpStat label="Addresses" value={totalHosts} />
        <WarpStat label="Nodes" value={nodes.length} />
      </WarpStatRow>

      <WarpTableCard
        toolbar={
          <>
            <WarpButton primary onClick={() => setEditingInbound("new")}>
              <Plus size={14} /> Add Inbound
            </WarpButton>
            <input
              className="warp-tb-search warp-tb-spacer"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search inbounds…"
            />
          </>
        }
      >
        <WarpHead cols={["#", "Name", "Node", "Protocol", "Addresses"]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : filtered.length === 0 ? (
          <WarpEmpty icon="fa-globe">
            {search ? "No matches." : "No inbounds yet."}
          </WarpEmpty>
        ) : (
          filtered.map((p, i) => (
            <WarpRow
              key={p.id}
              onClick={() => setDetail(p)}
              menu={[
                { label: "Edit", icon: "edit", onClick: () => setEditingInbound(p) },
                { label: "Disable", icon: "disable", disabled: !p.is_active, onClick: () => disableInbound(p) },
                { label: "Delete", icon: "trash", danger: true, onClick: () => removeInbound(p) },
              ]}
              cells={[
                i + 1,
                <span className="font-medium capitalize">{p.name}</span>,
                <span className="warp-tb-mono">{nodeName(p.node_id)}</span>,
                <span className={`warp-proto-badge ${protoBadge(p.protocol)}`}>{p.protocol}</span>,
                <WarpBadge tone={hostCount(p.id) > 0 ? "blue" : "gray"}>{hostCount(p.id)}</WarpBadge>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {detail ? (
        <HostsDrawer
          profile={detail}
          nodeName={nodeName(detail.node_id)}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setEditingInbound(detail);
            setDetail(null);
          }}
        />
      ) : null}

      {editingInbound ? (
        <ProfileDialog
          profile={editingInbound === "new" ? null : editingInbound}
          nodes={nodes}
          onClose={() => setEditingInbound(null)}
          onSaved={() => {
            setEditingInbound(null);
            refreshInbounds();
          }}
        />
      ) : null}
    </div>
  );
}

function HostsDrawer({
  profile,
  nodeName,
  onClose,
  onEdit,
}: {
  profile: ProfileRead;
  nodeName: string;
  onClose: () => void;
  onEdit: () => void;
}) {
  const qc = useQueryClient();
  const hostsQuery = useQuery({
    queryKey: ["inbound-hosts", profile.id],
    queryFn: () => listInboundHosts(profile.id),
  });
  const [hostDialog, setHostDialog] = useState<InboundHostRead | "new" | null>(null);
  const [search, setSearch] = useState("");

  const allHosts = (hostsQuery.data ?? []) as InboundHostRead[];
  const needle = search.trim().toLowerCase();
  const hosts = needle
    ? allHosts.filter((h) =>
        [h.remark, h.address, h.sni].some((v) => String(v ?? "").toLowerCase().includes(needle)),
      )
    : allHosts;

  const refreshHosts = () => {
    qc.invalidateQueries({ queryKey: ["inbound-hosts", profile.id] });
    qc.invalidateQueries({ queryKey: ["inbound-hosts", "all"] });
  };
  const removeHost = async (h: InboundHostRead) => {
    if (!(await confirmDialog({ title: `Delete host "${h.remark || h.address || h.id.slice(0, 8)}"?`, confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteInboundHost(h.id);
      toast("success", "Host deleted.");
      refreshHosts();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  return (
    <Drawer
      title={
        <span className="flex items-center gap-2">
          <span className="text-lg font-medium capitalize">{profile.name}</span>
          <WarpBadge tone="blue">{profile.protocol}</WarpBadge>
          <span className="text-sm text-fg-muted">· {nodeName}</span>
        </span>
      }
      width="w-[720px]"
      panelClassName="bg-canvas"
      onClose={onClose}
      onEdit={onEdit}
    >
      <div className="flex flex-col gap-4">
        <ProfileUsageCard profileId={profile.id} />
        <div className="flex items-center gap-2">
          <WarpButton onClick={() => setHostDialog("new")}>
            <Plus size={14} /> Add address
          </WarpButton>
          {allHosts.length > 3 ? (
            <input
              className="warp-tb-search ml-auto"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search addresses…"
            />
          ) : null}
        </div>

        <div>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left">
                <th className="px-3 py-2 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Remark</th>
                <th className="px-3 py-2 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Address</th>
                <th className="px-3 py-2 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Port</th>
                <th className="w-16 px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {hosts.map((h) => (
                <tr
                  key={h.id}
                  onClick={() => setHostDialog(h)}
                  className="cursor-pointer rounded-lg transition-colors hover:bg-muted"
                >
                  <td className="px-3 py-2.5 font-medium text-fg">
                    {h.remark || <span className="text-fg-muted">—</span>}
                    {h.is_universal ? (
                      <span className="ml-1.5">
                        <WarpBadge tone="blue">universal</WarpBadge>
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-fg-muted">{h.address ?? "—"}</td>
                  <td className="px-3 py-2.5">
                    <WarpBadge tone="gray">{h.port ?? "—"}</WarpBadge>
                  </td>
                  <td className="px-3 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      title="Delete"
                      className="warp-tb-rowicon warp-tb-del"
                      style={{ marginLeft: 0 }}
                      onClick={() => removeHost(h)}
                    >
                      <Trash size={12} />
                    </button>
                  </td>
                </tr>
              ))}
              {hosts.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-xs text-fg-muted">
                    No extra addresses — the inbound already works on the node address.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {hostDialog ? (
        <HostDialog
          profileId={profile.id}
          host={hostDialog === "new" ? null : hostDialog}
          onClose={() => setHostDialog(null)}
          onSaved={() => {
            setHostDialog(null);
            refreshHosts();
          }}
        />
      ) : null}
    </Drawer>
  );
}

function ProfileUsageCard({ profileId }: { profileId: string }) {
  const seriesQ = useQuery({
    queryKey: ["profile-usage-series", profileId],
    queryFn: () => profileUsageSeries(profileId, 24),
    refetchInterval: 15000,
  });
  const totalQ = useQuery({
    queryKey: ["profile-usage-total", profileId],
    queryFn: () => profileUsageTotal(profileId),
    refetchInterval: 15000,
  });
  const total = totalQ.data?.total_bytes ?? 0;

  return (
    <div>
      <div className="flex items-end justify-between gap-3 pb-3">
        <div>
          <h4 className="text-base font-medium text-fg">Inbound Traffic</h4>
          <p className="mt-1 text-sm text-fg-muted">Last 24 hours</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-2xl font-medium leading-none text-fg">{bytes(total)}</span>
          <span className="text-sm text-fg-muted">All-time total</span>
        </div>
      </div>
      <div className="py-2">
        <UsageAreaChart series={seriesQ.data ?? []} loading={seriesQ.isLoading} height={220} />
      </div>
    </div>
  );
}
