"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseZap } from "lucide-react";
import { useEffect, useState } from "react";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { trafficCleanup, trafficRetention } from "@/lib/api";
import { useT, type TranslateFn } from "@/lib/i18n";
import { SettingsRow } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

function intervalText(seconds: number, t: TranslateFn): string {
  if (!seconds || seconds <= 0) return t("retention.never");
  const hours = seconds / 3600;
  if (hours < 24) {
    const h = Math.round(hours);
    return h === 1 ? t("retention.hour", { n: h }) : t("retention.hours", { n: h });
  }
  const days = Math.round(hours / 24);
  return days === 1 ? t("retention.day", { n: days }) : t("retention.days", { n: days });
}

export function RetentionSettingsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["traffic-retention"], queryFn: () => trafficRetention() });

  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (q.data && !loaded) {
      setDays(q.data.retention_days);
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const status = q.data
    ? q.data.enabled
      ? t("retention.enabledStatus", {
          days: q.data.retention_days === 1 ? t("retention.day", { n: q.data.retention_days }) : t("retention.days", { n: q.data.retention_days }),
          interval: intervalText(q.data.interval_seconds, t),
        })
      : t("common.disabled")
    : t("common.loading");

  const cleanup = async () => {
    if (
      !(await confirmDialog({
        title: t("retention.cleanupConfirmTitle", { days }),
        message: t("retention.cleanupConfirmMessage"),
        confirmLabel: t("retention.cleanUp"),
        danger: true,
      }))
    )
      return;
    setBusy(true);
    try {
      const res = await trafficCleanup(days);
      toast("success", t("retention.deletedRecords", { n: res.deleted }));
      qc.invalidateQueries({ queryKey: ["traffic-retention"] });
    } catch (e) {
      toast("error", e instanceof Error ? e.message : t("retention.cleanupFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={DatabaseZap}
        title={t("retention.title")}
        description={t("retention.description")}
      >
        <SettingsRow label={t("retention.automaticCleanup")} hint={t("retention.automaticCleanupHint")}>
          <span className="text-sm text-fg">{status}</span>
        </SettingsRow>
        <SettingsRow label={t("retention.cleanUpNow")} hint={t("retention.cleanUpNowHint")}>
          <span className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={3650}
              className="warp-set-input"
              value={days}
              onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 1))}
            />
            <button
              type="button"
              className="warp-tb-button warp-tb-button-danger"
              onClick={cleanup}
              disabled={busy}
            >
              {busy ? t("retention.cleaning") : t("retention.cleanUp")}
            </button>
          </span>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
