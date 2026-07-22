"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { toast } from "@/components/ui/toast";
import { monitoringMetrics } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { SettingsRow } from "./settings";
import { SettingsSection } from "@/components/console/screens/settings-kit";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/components/console/screens/warp-table";

function prometheusUrl(): string {
  if (typeof window === "undefined") return "";
  const env = process.env.NEXT_PUBLIC_API_URL;
  const base = env ? env.replace(/\/+$/, "") : `${window.location.origin}/api/v1`;
  return `${base}/monitoring/prometheus`;
}

export function MetricsSettingsScreen() {
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
        title="Metrics"
        description="Live panel metrics. Scrape the Prometheus endpoint for dashboards and alerting."
      >
        <SettingsRow label="Prometheus endpoint" hint="Point your Prometheus scrape config at this URL.">
          <button
            type="button"
            className="warp-tb-button"
            onClick={async () => {
              const ok = await copyText(url);
              toast(ok ? "success" : "error", ok ? "Prometheus URL copied." : "Copy failed.");
            }}
          >
            Copy URL
          </button>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection divider icon={Activity} title="Current values" description={q.data?.collected_at ? `Collected ${new Date(q.data.collected_at).toLocaleString()}.` : "Snapshot of the latest metric values."}>
        <WarpTableCard className="warp-users-table warp-edge-table">
          <WarpHead cols={["Metric", "Labels", "Value"]} />
          {q.isLoading ? (
            <WarpSkeleton />
          ) : metrics.length === 0 ? (
            <WarpEmpty icon="fa-chart-line">No metrics reported yet.</WarpEmpty>
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
