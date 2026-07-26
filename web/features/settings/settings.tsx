"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { useT, type TranslateFn } from "@/lib/i18n";
import { type SaveReg, SettingsSaveContext } from "./save-context";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { BrandingSettingsScreen } from "./branding-settings";
import { BackupScreen } from "./panels";
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

function tabLabel(t: TranslateFn, tab: (typeof TAB_LIST)[number]): string {
  switch (tab) {
    case "General":
      return t("settings.tab.general");
    case "Security":
      return t("settings.tab.security");
    case "Backup":
      return t("settings.tab.backup");
    case "Monitoring":
      return t("settings.tab.monitoring");
  }
}

function buildSections(t: TranslateFn): Section[] {
  return [
    {
      key: "subscription",
      label: t("settings.subscription.label"),
      description: t("settings.subscription.desc"),
      tab: "General",
      image: `${IMG}/customization.png`,
      Comp: SubscriptionSettingsScreen,
    },
    {
      key: "user-templates",
      label: t("settings.userTemplates.label"),
      description: t("settings.userTemplates.desc"),
      tab: "General",
      image: `${IMG}/customization.png`,
      Comp: UserTemplatesSettingsScreen,
    },
    {
      key: "branding",
      label: t("settings.branding.label"),
      description: t("settings.branding.desc"),
      tab: "General",
      image: `${IMG}/custom-settings.png`,
      Comp: BrandingSettingsScreen,
    },
    {
      key: "security",
      label: t("settings.security.label"),
      description: t("settings.security.desc"),
      tab: "Security",
      image: `${IMG}/providers.png`,
      Comp: SecuritySettingsScreen,
    },
    {
      key: "certificates",
      label: t("settings.certificates.label"),
      description: t("settings.certificates.desc"),
      tab: "Security",
      image: `${IMG}/providers.png`,
      Comp: CertificatesSettingsScreen,
    },
    {
      key: "backup",
      label: t("settings.backup.label"),
      description: t("settings.backup.desc"),
      tab: "Backup",
      image: `${IMG}/vector.png`,
      Comp: BackupScreen,
    },
    {
      key: "retention",
      label: t("settings.retention.label"),
      description: t("settings.retention.desc"),
      tab: "Backup",
      image: `${IMG}/vector.png`,
      Comp: RetentionSettingsScreen,
    },
    {
      key: "notifications",
      label: t("settings.notifications.label"),
      description: t("settings.notifications.desc"),
      tab: "Monitoring",
      image: `${IMG}/logstash.png`,
      Comp: NotificationsSettingsScreen,
    },
    {
      key: "warp",
      label: t("settings.warp.label"),
      description: t("settings.warp.desc"),
      tab: "Monitoring",
      image: `${IMG}/logstash.png`,
      Comp: WarpSettingsScreen,
    },
    {
      key: "scheduler",
      label: t("settings.scheduler.label"),
      description: t("settings.scheduler.desc"),
      tab: "Monitoring",
      image: `${IMG}/logstash.png`,
      Comp: SchedulerSettingsScreen,
    },
    {
      key: "metrics",
      label: t("settings.metrics.label"),
      description: t("settings.metrics.desc"),
      tab: "Monitoring",
      image: `${IMG}/logstash.png`,
      Comp: MetricsSettingsScreen,
    },
    {
      key: "gitops",
      label: t("settings.gitops.label"),
      description: t("settings.gitops.desc"),
      tab: "Monitoring",
      image: `${IMG}/logstash.png`,
      Comp: GitOpsSettingsScreen,
    },
  ];
}

export function SettingsScreen() {
  const t = useT();
  const [section, setSection] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TAB_LIST)[number]>("General");
  const [saveReg, setSaveReg] = useState<SaveReg>(null);

  const sections = buildSections(t);
  const active = sections.find((s) => s.key === section) ?? null;
  const tabSections = sections.filter((s) => s.tab === tab);

  return (
    <div className="w-full px-4 pb-6 pt-0">
      {active ? (
        <>
          <div className="warp-breadcrumbs">
            <div className="track">
              <button
                type="button"
                className="warp-breadcrumbs-back"
                aria-label={t("action.back")}
                onClick={() => setSection(null)}
              >
                <ArrowLeft size={20} strokeWidth={1.9} aria-hidden />
              </button>
              <span className="warp-breadcrumbs-divider" />
              <div className="links">
                <button type="button" className="crumb" onClick={() => setSection(null)}>
                  {tabLabel(t, active.tab)}
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
                  {saveReg.busy ? t("common.saving") : t("action.save")}
                </button>
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <>
        <div className="warp-pd-tabs warp-settings-tabs" role="tablist">
          {TAB_LIST.map((tabName) => (
            <button
              key={tabName}
              type="button"
              role="tab"
              aria-selected={tabName === tab}
              className={cn("warp-pd-tab", tabName === tab && "is-active")}
              onClick={() => setTab(tabName)}
            >
              {tabLabel(t, tabName)}
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
