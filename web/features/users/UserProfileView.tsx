"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, CircleUser, Globe, Layers, Link as LinkIcon, Pencil, Power, RotateCcw, Smartphone } from "lucide-react";
import { useState } from "react";
import { type UserRead } from "@/lib/api";
import { useT, type TranslateFn } from "@/lib/i18n";
import { userStatus } from "@/lib/status";
import { cn } from "@/lib/cn";
import { bytes } from "@/lib/format";
import { SettingsSection } from "@/shared/settings-kit";
import {
  AccessManager,
  UserNodesUsagePanel,
  UserSubscriptionPanel,
} from "./access";
import { EditUserDialog } from "./dialogs";
import { Badge, PdRow } from "./components";
import { UserDevicesTable } from "./UserDevicesTable";

const userTabs = (t: TranslateFn) =>
  [
    ["info", t("users.tab.details")],
    ["services", t("users.tab.services")],
    ["subscription", t("users.tab.subscription")],
    ["nodes", t("users.tab.nodesUsage")],
  ] as const;

export function UserProfileView({
  user,
  onBack,
  onReset,
  onToggle,
}: {
  user: UserRead;
  onBack: () => void;
  onReset: () => void;
  onToggle: () => void;
}) {
  const t = useT();
  const [tab, setTab] = useState<string>("info");
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();
  const s = userStatus(user);

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-breadcrumbs">
        <div className="track">
          <button
            type="button"
            className="warp-breadcrumbs-back"
            aria-label={t("action.back")}
            onClick={onBack}
          >
            <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
          </button>
          <span className="warp-breadcrumbs-divider" />
          <div className="links">
            <button type="button" className="crumb" onClick={onBack}>
              {t("nav.users")}
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{user.username}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" className="warp-tb-button" onClick={() => setEditing(true)}>
              <Pencil size={14} aria-hidden /> {t("action.edit")}
            </button>
            <button type="button" className="warp-tb-button" onClick={onReset}>
              <RotateCcw size={14} aria-hidden /> {t("users.resetUsage")}
            </button>
            <button type="button" className="warp-tb-button" onClick={onToggle}>
              <Power size={14} aria-hidden /> {user.is_active ? t("action.disable") : t("action.enable")}
            </button>
          </div>
        </div>
      </div>
      <div className="warp-pd-tabs warp-profile-tabs">
        {userTabs(t).map(([key, label]) => (
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

      {tab === "info" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={CircleUser} title={t("users.section.general")} description={t("users.section.generalDesc")}>
            <div className="warp-pd-form">
              <PdRow label={t("users.field.username")} value={user.username} />
              <PdRow label={t("common.name")} value={user.full_name || "—"} />
              <PdRow label={t("users.field.email")} value={user.email || "—"} />
              <PdRow label={t("common.status")} value={
                s === "disabled" ? <Badge variant="critical">{t("users.status.disabled")}</Badge>
                  : s === "onhold" ? <Badge variant="warning">{t("users.status.onHold")}</Badge>
                  : s === "expired" ? <Badge variant="critical">{t("users.status.expired")}</Badge>
                  : s === "limited" ? <Badge variant="critical">{t("users.status.limited")}</Badge>
                  : <Badge variant="success">{t("users.status.active")}</Badge>
              } />
              <PdRow label={t("users.field.expiration")} value={
                user.expire_at ? new Date(user.expire_at).toLocaleDateString() : t("users.value.never")
              } />
              <PdRow label={t("users.field.dataLimit")} value={
                user.data_limit_bytes ? bytes(user.data_limit_bytes) : t("users.value.unlimited")
              } />
              <PdRow label={t("users.field.usedTraffic")} value={bytes(user.users_data_usage ?? 0)} />
              <PdRow label={t("users.field.deviceLimit")} value={
                user.device_limit != null ? String(user.device_limit) : t("users.value.unlimited")
              } />
              <PdRow label={t("users.field.owner")} value={user.owner_id ? user.owner_id.slice(0, 8) : "—"} />
              <PdRow label={t("users.field.created")} value={
                user.created_at ? new Date(user.created_at).toLocaleString() : "—"
              } />
            </div>
          </SettingsSection>
          <SettingsSection divider icon={Smartphone} title={t("users.section.devices")} description={t("users.section.devicesDesc")}>
            <UserDevicesTable userId={user.id} deviceLimit={user.device_limit} />
          </SettingsSection>
        </div>
      ) : null}

      {tab === "services" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Layers} title={t("users.tab.services")} description={t("users.section.servicesDesc")}>
            <AccessManager userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "subscription" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={LinkIcon} title={t("users.tab.subscription")} description={t("users.section.subscriptionDesc")}>
            <UserSubscriptionPanel userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "nodes" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Globe} title={t("users.section.nodesUsage")} description={t("users.section.nodesUsageDesc")}>
            <UserNodesUsagePanel userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}

      {editing ? (
        <EditUserDialog
          user={user}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            qc.invalidateQueries({ queryKey: ["users"] });
          }}
        />
      ) : null}
    </div>
  );
}
