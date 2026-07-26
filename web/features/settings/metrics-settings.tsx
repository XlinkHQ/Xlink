"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { toast } from "@/components/ui/toast";
import { monitoringMetrics } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { useT } from "@/lib/i18n";
import { SettingsRow } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";
import { WarpEmpty, WarpError, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";

function prometheusUrl(): string {
  if (typeof window === "undefined") return "";
  const env = process.env.NEXT_PUBLIC_API_URL;
  const base = env ? env.replace(/\/+$/, "") : `${window.location.origin}/api/v1`;
  return `${base}/monitoring/prometheus`;
}

export function MetricsSettingsScreen() {
  const t = useT();
  const q = useQuery({
    queryKey: ["monitoring-metrics"],
    queryFn: () => monitoringMetrics(),
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
  });
  const metrics = q.data?.metrics ?? [];
  const url = prometheusUrl();

  return (
    <div className="w-full">
      <SettingsSection
        icon={Activity}
        title={t("metrics.title")}
        description={t("metrics.description")}
      >
        <SettingsRow label={t("metrics.endpointLabel")} hint={t("metrics.endpointHint")}>
          <button
            type="button"
            className="warp-tb-button"
            onClick={async () => {
              const ok = await copyText(url);
              toast(ok ? "success" : "error", ok ? t("metrics.urlCopied") : t("common.copyFailed"));
            }}
          >
            {t("metrics.copyUrl")}
          </button>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection divider icon={Activity} title={t("metrics.currentValues")} description={q.data?.collected_at ? t("metrics.collectedAt", { time: new Date(q.data.collected_at).toLocaleString() }) : t("metrics.currentValuesDescription")}>
        <WarpTableCard className="warp-users-table warp-edge-table">
          <WarpHead cols={[t("metrics.col.metric"), t("metrics.col.labels"), t("metrics.col.value")]} />
          {q.isLoading ? (
            <WarpSkeleton />
          ) : q.isError ? (
            <WarpError onRetry={() => q.refetch()} />
          ) : metrics.length === 0 ? (
            <WarpEmpty>{t("metrics.empty")}</WarpEmpty>
          ) : (
            metrics.map((m, i) => (
              <WarpRow
                key={`${m.name}-${i}`}
                cells={[
                  <span className="warp-tb-mono font-medium">{m.name}</span>,
                  <span className="text-fg-muted warp-tb-mono">
                    {Object.keys(m.labels).length
                      ? Object.entries(m.labels).map(([k, v]) => `${k}=${v}`).join(", ")
                      : "—"}
                  </span>,
                  <span className="font-medium">{m.value}</span>,
                ]}
              />
            ))
          )}
        </WarpTableCard>
      </SettingsSection>
    </div>
  );
}
