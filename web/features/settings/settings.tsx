"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { BrandingSettingsScreen } from "./branding-settings";
import { BackupScreen } from "@/components/console/screens/panels";
import { RetentionSettingsScreen } from "./retention-settings";
import { MetricsSettingsScreen } from "./metrics-settings";
import { GitOpsSettingsScreen } from "./gitops-settings";
import { SecuritySettingsScreen } from "./security-settings";
import { CertificatesSettingsScreen } from "./certificates-settings";
import { UserTemplatesSettingsScreen } from "./user-templates-settings";
import { WarpSettingsScreen } from "./warp-settings";
import { NotificationsSettingsScreen } from "./notifications-settings";
import { SchedulerSettingsScreen } from "./scheduler-settings";
import { SubscriptionSettingsScreen } from "./subscription-settings";

type SaveReg = { fn: () => Promise<void> | void; busy: boolean } | null;
const SettingsSaveContext = createContext<(reg: SaveReg) => void>(() => {});

export function useRegisterSave(fn: () => Promise<void> | void, busy = false): void {
  const register = useContext(SettingsSaveContext);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    register({ fn: () => fnRef.current(), busy });
    return () => register(null);
  }, [register, busy]);
}

const TAB_LIST = ["General", "Security", "Backup", "Monitoring"] as const;

type Section = {
  key: string;
  label: string;
  description: string;
  tab: (typeof TAB_LIST)[number];
  image: string;
  Comp: () => React.JSX.Element;
};

const IMG = "/settings-icons";
const SECTIONS: Section[] = [
  {
    key: "subscription",
    label: "Subscription",
    description: "Manage your plan, license and billing details.",
    tab: "General",
    image: `${IMG}/customization.png`,
    Comp: SubscriptionSettingsScreen,
  },
  {
    key: "user-templates",
    label: "User templates",
    description: "Presets for fast user creation (data limit, duration, device limit).",
    tab: "General",
    image: `${IMG}/customization.png`,
    Comp: UserTemplatesSettingsScreen,
  },
  {
    key: "branding",
    label: "Branding",
    description: "Customize the panel name, logo and colors.",
    tab: "General",
    image: `${IMG}/custom-settings.png`,
    Comp: BrandingSettingsScreen,
  },
  {
    key: "security",
    label: "Authentication",
    description: "Manage two-factor authentication for admin sign-in.",
    tab: "Security",
    image: `${IMG}/providers.png`,
    Comp: SecuritySettingsScreen,
  },
  {
    key: "certificates",
    label: "Certificates",
    description: "TLS and REALITY posture of every inbound.",
    tab: "Security",
    image: `${IMG}/providers.png`,
    Comp: CertificatesSettingsScreen,
  },
  {
    key: "backup",
    label: "Backup",
    description: "Create, restore and schedule panel backups.",
    tab: "Backup",
    image: `${IMG}/vector.png`,
    Comp: BackupScreen,
  },
  {
    key: "retention",
    label: "Data retention",
    description: "Automatic cleanup of old traffic records.",
    tab: "Backup",
    image: `${IMG}/vector.png`,
    Comp: RetentionSettingsScreen,
  },
  {
    key: "notifications",
    label: "Notifications",
    description: "Expiry, usage and node-down alerts across webhook, Discord and Telegram.",
    tab: "Monitoring",
    image: `${IMG}/logstash.png`,
    Comp: NotificationsSettingsScreen,
  },
  {
    key: "warp",
    label: "Cloudflare WARP",
    description: "WARP WireGuard outbound for geo-restricted destinations.",
    tab: "Monitoring",
    image: `${IMG}/logstash.png`,
    Comp: WarpSettingsScreen,
  },
  {
    key: "scheduler",
    label: "Scheduler",
    description: "Simulate node placement and see why the scheduler picks a node.",
    tab: "Monitoring",
    image: `${IMG}/logstash.png`,
    Comp: SchedulerSettingsScreen,
  },
  {
    key: "metrics",
    label: "Metrics",
    description: "Live panel metrics and Prometheus scrape endpoint.",
    tab: "Monitoring",
    image: `${IMG}/logstash.png`,
    Comp: MetricsSettingsScreen,
  },
  {
    key: "gitops",
    label: "Change history",
    description: "Config snapshots and diffs committed across the panel.",
    tab: "Monitoring",
    image: `${IMG}/logstash.png`,
    Comp: GitOpsSettingsScreen,
  },
];

export function SettingsRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="warp-set-row">
      <div className="warp-set-row-label">
        <h4>{label}</h4>
        {hint ? <p>{hint}</p> : null}
      </div>
      <div className="warp-set-row-control">{children}</div>
    </div>
  );
}

export function SettingsScreen() {
  const [section, setSection] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TAB_LIST)[number]>("General");
  const [saveReg, setSaveReg] = useState<SaveReg>(null);

  const active = SECTIONS.find((s) => s.key === section) ?? null;
  const tabSections = SECTIONS.filter((s) => s.tab === tab);

  return (
    <div className="w-full px-4 pb-6 pt-0">
      {active ? (
        <>
          <div className="warp-breadcrumbs">
            <div className="track">
              <button
                type="button"
                className="warp-breadcrumbs-back"
                aria-label="Back"
                onClick={() => setSection(null)}
              >
                <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
              </button>
              <span className="warp-breadcrumbs-divider" />
              <div className="links">
                <button type="button" className="crumb" onClick={() => setSection(null)}>
                  {active.tab}
                </button>
                <ChevronRight size={20} strokeWidth={2} className="crumb-sep" aria-hidden />
                <span className="crumb active">{active.label}</span>
              </div>
            </div>
          </div>

          <div className="warp-settings-card">
            <SettingsSaveContext.Provider value={setSaveReg}>
              <active.Comp />
            </SettingsSaveContext.Provider>

            {saveReg ? (
              <div className="controls">
                <button
                  type="button"
                  className="warp-dg-btn primary"
                  disabled={saveReg.busy}
                  onClick={() => saveReg.fn()}
                >
                  {saveReg.busy ? "Saving…" : "Save"}
                </button>
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <>
        <div className="warp-pd-tabs warp-settings-tabs" role="tablist">
          {TAB_LIST.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={t === tab}
              className={cn("warp-pd-tab", t === tab && "is-active")}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="warp-section-select-list">
          {tabSections.map((s) => {
            return (
              <button
                key={s.key}
                type="button"
                className="warp-section-select"
                onClick={() => setSection(s.key)}
              >
                <span className="warp-section-select-img">
                  <img src={s.image} alt="" draggable={false} />
                </span>
                <span className="warp-section-select-content">
                  <span className="warp-section-select-title">{s.label}</span>
                  <span className="warp-section-select-desc">{s.description}</span>
                </span>
                <span className="warp-section-select-arrow">
                  <ChevronRight size={20} strokeWidth={1.75} />
                </span>
              </button>
            );
          })}
        </div>
        </>
      )}
    </div>
  );
}
