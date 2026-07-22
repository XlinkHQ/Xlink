"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseZap } from "lucide-react";
import { useEffect, useState } from "react";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { trafficCleanup, trafficRetention } from "@/lib/api";
import { SettingsRow } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

function intervalText(seconds: number): string {
  if (!seconds || seconds <= 0) return "never";
  const hours = seconds / 3600;
  if (hours < 24) {
    const h = Math.round(hours);
    return `${h} ${h === 1 ? "hour" : "hours"}`;
  }
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"}`;
}

export function RetentionSettingsScreen() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["traffic-retention"], queryFn: () => trafficRetention() });

  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // One-time latch so a background refetch can't clobber an in-progress edit.
    if (q.data && !loaded) {
      setDays(q.data.retention_days);
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const status = q.data
    ? q.data.enabled
      ? `Enabled every ${q.data.retention_days} ${q.data.retention_days === 1 ? "day" : "days"} (runs every ${intervalText(q.data.interval_seconds)})`
      : "Disabled"
    : "Loading…";

  const cleanup = async () => {
    if (
      !(await confirmDialog({
        title: `Delete traffic records older than ${days} days?`,
        message: "This permanently removes old traffic records and cannot be undone.",
        confirmLabel: "Clean up",
        danger: true,
      }))
    )
      return;
    setBusy(true);
    try {
      const res = await trafficCleanup(days);
      toast("success", `Deleted ${res.deleted} records.`);
      qc.invalidateQueries({ queryKey: ["traffic-retention"] });
    } catch (e) {
      toast("error", e instanceof Error ? e.message : "Cleanup failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={DatabaseZap}
        title="Data retention"
        description="How long traffic records are kept before automatic cleanup."
      >
        <SettingsRow label="Automatic cleanup" hint="Current retention policy applied by the server.">
          <span className="text-sm text-fg">{status}</span>
        </SettingsRow>
        <SettingsRow label="Clean up now" hint="Delete traffic records older than the given days.">
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
              {busy ? "Cleaning…" : "Clean up"}
            </button>
          </span>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
