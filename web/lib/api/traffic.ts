import { apiFetch } from "./core";
import { query } from "./internal";

export type TrafficTotals = {
  total_bytes: number;
  upload_bytes: number;
  download_bytes: number;
  record_count: number;
};

export type MetricRead = { name: string; value: number; labels: Record<string, string> };

export type MetricsSnapshotRead = {
  metrics: MetricRead[];
  collected_at: string;
};

export function trafficSummary() {
  return apiFetch<TrafficTotals>("/traffic/summary");
}

export function trafficThroughput(windowSeconds = 120) {
  return apiFetch<TrafficTotals>(`/traffic/throughput${query({ window_seconds: windowSeconds })}`);
}

export function onlineUsers(windowSeconds = 45) {
  return apiFetch<{ user_ids: string[]; window_seconds: number }>(
    `/traffic/online${query({ window_seconds: windowSeconds })}`,
  );
}

export function assignmentTraffic(assignmentId: string) {
  return apiFetch<{
    assignment_id: string;
    upload_bytes: number;
    download_bytes: number;
    total_bytes: number;
    sample_count: number;
  }>(`/traffic/assignments/${assignmentId}`);
}

export function nodeTrafficUsage() {
  return apiFetch<{ node_id: string; total_bytes: number }[]>("/traffic/nodes");
}

export function userNodeUsage(userId: string) {
  return apiFetch<{ node_id: string; node_name: string; total_bytes: number }[]>(
    `/traffic/users/${userId}/nodes`,
  );
}

export function userUsageSeries(userId: string, days = 14) {
  return apiFetch<{ date: string; upload_bytes: number; download_bytes: number; total_bytes: number }[]>(
    `/traffic/users/${userId}/usage-series${query({ days })}`,
  );
}

export type UsageSeriesPoint = { ts: string; upload_bytes: number; download_bytes: number; total_bytes: number };

export function nodeUsageSeries(nodeId: string, hours = 24) {
  return apiFetch<UsageSeriesPoint[]>(`/traffic/nodes/${nodeId}/usage-series${query({ hours })}`);
}

export function profileUsageSeries(profileId: string, hours = 24) {
  return apiFetch<UsageSeriesPoint[]>(`/traffic/profiles/${profileId}/usage-series${query({ hours })}`);
}

export function profileUsageTotal(profileId: string) {
  return apiFetch<{ total_bytes: number }>(`/traffic/profiles/${profileId}/usage`);
}

export function resetUserUsage(userId: string) {
  return apiFetch<{ reset_assignments: number }>(`/traffic/users/${userId}/reset`, {
    method: "POST",
  });
}

export type UserUsage = {
  user_id: string;
  used_bytes: number;
  limit_bytes: number;
  unlimited: boolean;
};

export function usersUsage(userIds: string[]) {
  return apiFetch<UserUsage[]>("/traffic/users/usage", {
    method: "POST",
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export function usersLastSeen(userIds: string[]) {
  return apiFetch<{ user_id: string; last_seen_at: string }[]>("/traffic/users/last-seen", {
    method: "POST",
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export type RetentionRead = { enabled: boolean; retention_days: number; interval_seconds: number };
export function trafficRetention() {
  return apiFetch<RetentionRead>("/traffic/retention");
}
export function trafficCleanup(retentionDays: number) {
  return apiFetch<{ deleted: number; retention_days: number }>("/traffic/cleanup", {
    method: "POST",
    body: JSON.stringify({ retention_days: retentionDays }),
  });
}
