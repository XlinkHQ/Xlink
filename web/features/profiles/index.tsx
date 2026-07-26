"use client";
import { protoBadge } from "@/lib/proto";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Activity, ArrowLeft, ChevronRight, Gauge, Pencil, Plus } from "lucide-react";
import {
  ApiError,
  deleteInboundHost,
  deleteProfile,
  disableProfile,
  updateProfile,
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
import { UsageAreaChart } from "@/shared/usage-chart";
import {
  WarpBadge,
  WarpButton,
  WarpEmpty,
  WarpError,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { ProfileDialog } from "./dialog";
import { HostDialog } from "./host-dialog";
import { DgSearch } from "@/components/console/dg-icons";
import { SettingsSection } from "@/shared/settings-kit";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export function ProfilesScreen() {
  const t = useT();
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
  const [detailId, setDetailId] = useState<string | null>(null);
  const [editInline, setEditInline] = useState(false);
  const detail = detailId ? (profiles.find((p) => p.id === detailId) ?? null) : null;

  const refreshInbounds = () => {
    qc.invalidateQueries({ queryKey: ["profiles"] });
    qc.invalidateQueries({ queryKey: ["inbound-hosts", "all"] });
  };

  const disableInbound = async (p: ProfileRead) => {
    if (!(await confirmDialog({ title: t("profiles.disableConfirm", { name: p.name }), confirmLabel: t("action.disable"), danger: true }))) return;
    try {
      await disableProfile(p.id);
      toast("success", t("profiles.disabled"));
      refreshInbounds();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
    }
  };

  const enableInbound = async (p: ProfileRead) => {
    try {
      await updateProfile(p.id, { is_active: true });
      toast("success", t("profiles.enabled"));
      refreshInbounds();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
    }
  };

  const removeInbound = async (p: ProfileRead) => {
    if (!(await confirmDialog({ title: t("profiles.deleteConfirm", { name: p.name }), message: t("profiles.deleteConfirmMessage"), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteProfile(p.id);
      toast("success", t("profiles.deleted"));
      refreshInbounds();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
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

  if (detail) {
    return (
      <HostsDrawer
        profile={detail}
        nodeName={nodeName(detail.node_id)}
        onClose={() => {
          setDetailId(null);
          setEditInline(false);
        }}
        editing={editInline}
        onEdit={() => setEditInline((v) => !v)}
        editForm={
          editInline ? (
            <ProfileDialog
              variant="inline"
              profile={detail}
              nodes={nodes}
              onClose={() => setEditInline(false)}
              onSaved={() => {
                setEditInline(false);
                refreshInbounds();
              }}
            />
          ) : null
        }
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("profiles.allHosts")}</span>
        <div className="right">
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("profiles.findHost")}
            />
          </span>
          <WarpButton primary onClick={() => setEditingInbound("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("profiles.addInbound")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("profiles.node"), t("profiles.protocol"), t("profiles.addresses")]} actions />
        {query.isLoading ? (
          <WarpSkeleton />
        ) : query.isError ? (
          <WarpError onRetry={() => query.refetch()} />
        ) : filtered.length === 0 ? (
          <WarpEmpty>
            {search ? t("common.noMatches") : t("profiles.noInboundsYet")}
          </WarpEmpty>
        ) : (
          filtered.map((p) => (
            <WarpRow
              key={p.id}
              onClick={() => setDetailId(p.id)}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setEditingInbound(p) },
                p.is_active
                  ? { label: t("action.disable"), icon: "disable", onClick: () => disableInbound(p) }
                  : { label: t("action.enable"), icon: "check", onClick: () => enableInbound(p) },
                { label: t("action.delete"), icon: "trash", danger: true, onClick: () => removeInbound(p) },
              ]}
              cells={[
                <span className="font-medium capitalize">{p.name}</span>,
                <span className="warp-tb-mono">{nodeName(p.node_id)}</span>,
                <span className={`warp-proto-badge ${protoBadge(p.protocol)}`}>{p.protocol}</span>,
                <WarpBadge tone={hostCount(p.id) > 0 ? "blue" : "gray"}>{hostCount(p.id)}</WarpBadge>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

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
  editing = false,
  editForm = null,
}: {
  profile: ProfileRead;
  nodeName: string;
  onClose: () => void;
  onEdit: () => void;
  editing?: boolean;
  editForm?: React.ReactNode;
}) {
  const t = useT();
  const qc = useQueryClient();
  const hostsQuery = useQuery({
    queryKey: ["inbound-hosts", profile.id],
    queryFn: () => listInboundHosts(profile.id),
  });
  const [hostDialog, setHostDialog] = useState<InboundHostRead | "new" | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"general" | "traffic" | "addresses">("general");

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
    if (!(await confirmDialog({ title: t("profiles.deleteHostConfirm", { name: h.remark || h.address || h.id.slice(0, 8) }), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteInboundHost(h.id);
      toast("success", t("profiles.hostDeleted"));
      refreshHosts();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.deleteFailed"));
    }
  };

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
              {t("profiles.hosts")}
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{profile.name}</span>
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
        {([["general", t("profiles.tabGeneral")], ["traffic", t("profiles.tabInboundTraffic")], ["addresses", t("profiles.tabAddresses")]] as const).map(([key, label]) => (
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

      {tab === "general" ? (
      <div className="warp-settings-card">
        <SettingsSection icon={Gauge} title={t("profiles.tabGeneral")} description={t("profiles.generalDescription")}>
          <PdRow label={t("profiles.protocol")} value={<span className={`warp-proto-badge ${protoBadge(profile.protocol)}`}>{profile.protocol}</span>} />
          <PdRow label={t("profiles.node")} value={nodeName} />
          <PdRow label={t("profiles.addresses")} value={String(allHosts.length)} />
        </SettingsSection>
      </div>
      ) : null}

      {tab === "traffic" ? (
      <div className="warp-settings-card">
        <SettingsSection icon={Activity} title={t("profiles.tabInboundTraffic")} description={t("profiles.trafficDescription")}>
          <ProfileUsageCard profileId={profile.id} />
        </SettingsSection>
      </div>
      ) : null}

      {tab === "addresses" ? (
        <>
          <div className="warp-table-top">
            <span className="title">{t("profiles.addresses")}</span>
            <div className="right">
              {allHosts.length > 3 ? (
                <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
                  <DgSearch size={16} />
                  <input
                    className="warp-tb-search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("profiles.findAddress")}
                  />
                </span>
              ) : null}
              <WarpButton primary onClick={() => setHostDialog("new")}>
                <Plus size={16} strokeWidth={1.8} aria-hidden /> {t("profiles.addAddress")}
              </WarpButton>
            </div>
          </div>
          <WarpTableCard className="warp-users-table">
            <WarpHead cols={[t("profiles.remark"), t("profiles.address"), t("profiles.port")]} actions />
            {hostsQuery.isLoading ? (
              <WarpSkeleton />
            ) : hostsQuery.isError ? (
              <WarpError onRetry={() => hostsQuery.refetch()} />
            ) : hosts.length === 0 ? (
              <WarpEmpty>{t("profiles.noExtraAddresses")}</WarpEmpty>
            ) : (
              hosts.map((h) => (
                <WarpRow
                  key={h.id}
                  onClick={() => setHostDialog(h)}
                  menu={[
                    { label: t("action.edit"), icon: "edit", onClick: () => setHostDialog(h) },
                    { label: t("action.delete"), icon: "delete", danger: true, onClick: () => removeHost(h) },
                  ]}
                  cells={[
                    <span className="font-medium">
                      {h.remark || "—"}
                      {h.is_universal ? <span className="ml-1.5 warp-badge info">{t("profiles.universal")}</span> : null}
                    </span>,
                    <span className="text-fg-muted">{h.address ?? "—"}</span>,
                    <span className="text-fg-muted">{h.port ?? "—"}</span>,
                  ]}
                />
              ))
            )}
          </WarpTableCard>
        </>
      ) : null}

      {hostDialog ? (
        <HostDialog
          variant="inline"
          profileId={profile.id}
          host={hostDialog === "new" ? null : hostDialog}
          onClose={() => setHostDialog(null)}
          onSaved={() => {
            setHostDialog(null);
            refreshHosts();
          }}
        />
      ) : null}

      {editForm}
    </div>
  );
}

function PdRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="warp-pd-row">
      <span className="warp-pd-row-label">{label}</span>
      <span className="warp-pd-row-value">{value}</span>
    </div>
  );
}

function ProfileUsageCard({ profileId }: { profileId: string }) {
  const t = useT();
  const seriesQ = useQuery({
    queryKey: ["profile-usage-series", profileId],
    queryFn: () => profileUsageSeries(profileId, 24),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });
  const totalQ = useQuery({
    queryKey: ["profile-usage-total", profileId],
    queryFn: () => profileUsageTotal(profileId),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });
  const total = totalQ.data?.total_bytes ?? 0;

  return (
    <div>
      <div className="flex items-end justify-between gap-3 pb-3">
        <div>
          <h4 className="text-base font-medium text-fg">{t("profiles.tabInboundTraffic")}</h4>
          <p className="mt-1 text-sm text-fg-muted">{t("profiles.last24Hours")}</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-2xl font-medium leading-none text-fg">{bytes(total)}</span>
          <span className="text-sm text-fg-muted">{t("profiles.allTimeTotal")}</span>
        </div>
      </div>
      <div className="py-2">
        <UsageAreaChart series={seriesQ.data ?? []} loading={seriesQ.isLoading} height={220} />
      </div>
    </div>
  );
}
