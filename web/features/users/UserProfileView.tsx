"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, CircleUser, Globe, Layers, Link as LinkIcon, Pencil, Power, RotateCcw, Smartphone } from "lucide-react";
import { useState } from "react";
import { type UserRead } from "@/lib/api";
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

const USER_TABS = [
  ["info", "Details"],
  ["services", "Services"],
  ["subscription", "Subscription"],
  ["nodes", "Nodes Usage"],
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
  const [tab, setTab] = useState<string>("info");
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();

  return (
    <div className="w-full px-4 pb-6 pt-0">
      <div className="warp-breadcrumbs">
        <div className="track">
          <button
            type="button"
            className="warp-breadcrumbs-back"
            aria-label="Back"
            onClick={onBack}
          >
            <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
          </button>
          <span className="warp-breadcrumbs-divider" />
          <div className="links">
            <button type="button" className="crumb" onClick={onBack}>
              Users
            </button>
            <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
            <span className="crumb active">{user.username}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" className="warp-tb-button" onClick={() => setEditing(true)}>
              <Pencil size={14} aria-hidden /> Edit
            </button>
            <button type="button" className="warp-tb-button" onClick={onReset}>
              <RotateCcw size={14} aria-hidden /> Reset usage
            </button>
            <button type="button" className="warp-tb-button" onClick={onToggle}>
              <Power size={14} aria-hidden /> {user.is_active ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
      </div>
      <div className="warp-pd-tabs warp-profile-tabs">
        {USER_TABS.map(([key, label]) => (
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
          <SettingsSection icon={CircleUser} title="General" description="Account details and usage limits for this user.">
            <div className="warp-pd-form">
              <PdRow label="Username" value={user.username} />
              <PdRow label="Name" value={user.full_name || "—"} />
              <PdRow label="Email" value={user.email || "—"} />
              <PdRow label="Status" value={
                !user.is_active ? <Badge variant="critical">Disabled</Badge>
                  : user.on_hold ? <Badge variant="warning">On-hold</Badge>
                  : (user.expire_at && Date.parse(user.expire_at) < Date.now()) ? <Badge variant="critical">Expired</Badge>
                  : <Badge variant="success">Active</Badge>
              } />
              <PdRow label="Expiration" value={
                user.expire_at ? new Date(user.expire_at).toLocaleDateString() : "Never"
              } />
              <PdRow label="Data limit" value={
                user.data_limit_bytes ? bytes(user.data_limit_bytes) : "Unlimited"
              } />
              <PdRow label="Used traffic" value={bytes(user.users_data_usage ?? 0)} />
              <PdRow label="Device limit" value={
                user.device_limit != null ? String(user.device_limit) : "Unlimited"
              } />
              <PdRow label="Owner" value={user.owner_id ? user.owner_id.slice(0, 8) : "—"} />
              <PdRow label="Created" value={
                user.created_at ? new Date(user.created_at).toLocaleString() : "—"
              } />
            </div>
          </SettingsSection>
          <SettingsSection divider icon={Smartphone} title="Devices" description="Devices currently bound to this user.">
            <UserDevicesTable userId={user.id} deviceLimit={user.device_limit} />
          </SettingsSection>
        </div>
      ) : null}

      {tab === "services" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Layers} title="Services" description="Services and inbounds granted to this user.">
            <AccessManager userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "subscription" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={LinkIcon} title="Subscription" description="Subscription link and client configuration for this user.">
            <UserSubscriptionPanel userId={user.id} />
          </SettingsSection>
        </div>
      ) : null}
      {tab === "nodes" ? (
        <div className="warp-settings-card">
          <SettingsSection icon={Globe} title="Nodes usage" description="Per-node traffic usage for this user.">
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
