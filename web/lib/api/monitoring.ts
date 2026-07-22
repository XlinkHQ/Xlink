import { apiFetch } from "./core";
import type { MetricsSnapshotRead } from "./traffic";

export type SystemStatsRead = {
  cpu_percent: number;
  cpu_cores: number;
  ram_used_bytes: number;
  ram_total_bytes: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  uptime_seconds: number;
  load_avg_1: number;
  load_avg_5: number;
  load_avg_15: number;
  swap_used_bytes: number;
  swap_total_bytes: number;
  process_count: number;
  hostname: string;
  os_name: string;
  os_slug: string;
  kernel: string;
  arch: string;
  ip_address: string;
  ip6_address: string;
  mac_address: string;
  python_version: string;
  app_version: string;
};

export function systemStats() {
  return apiFetch<SystemStatsRead>("/monitoring/system");
}

export function restartPanel() {
  return apiFetch<{ status: string }>("/monitoring/restart", { method: "POST" });
}

export function monitoringMetrics() {
  // /monitoring/metrics returns a bare MetricRead[]; the snapshot shape
  // ({metrics, collected_at}) the screen reads lives at /monitoring/summary.
  return apiFetch<MetricsSnapshotRead>("/monitoring/summary");
}
