import {
  type AssignmentRead,
  type CursorPage,
  type NodeRead,
  type ProfileRead,
  type ProviderRead,
  type UserRead,
  listAssignments,
  listNodes,
  listProfiles,
  listProviders,
  listUsers,
  monitoringSummary,
  trafficSummary,
} from "@/lib/api";

export type LiveColumn = {
  header: string;
  accessor: (row: Record<string, unknown>) => string;
};

export type LiveSection = {
  columns: LiveColumn[];
  fetch: () => Promise<CursorPage<Record<string, unknown>>>;
  statusOf: (row: Record<string, unknown>) => string;
};

function shortId(value: unknown): string {
  return typeof value === "string" ? value.slice(0, 8) : "";
}

function date(value: unknown): string {
  return typeof value === "string" ? value.slice(0, 10) : "";
}

function bytes(value: unknown): string {
  if (typeof value !== "number") return "—";
  if (value < 1024) return `${value} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
}

const nodeSection: LiveSection = {
  columns: [
    { header: "Name", accessor: (r) => String((r as unknown as NodeRead).name ?? "") },
    { header: "Host", accessor: (r) => String((r as unknown as NodeRead).host ?? "") },
    { header: "Port", accessor: (r) => String((r as unknown as NodeRead).port ?? "") },
    { header: "Status", accessor: (r) => String((r as unknown as NodeRead).status ?? "") },
    { header: "Users", accessor: (r) => String((r as unknown as NodeRead).current_users ?? 0) },
    { header: "Max", accessor: (r) => String((r as unknown as NodeRead).max_users ?? 0) },
    { header: "Updated", accessor: (r) => date((r as unknown as NodeRead).updated_at) },
  ],
  fetch: async () => (await listNodes()) as CursorPage<Record<string, unknown>>,
  statusOf: (r) => String((r as unknown as NodeRead).status ?? "active"),
};

const assignmentSection: LiveSection = {
  columns: [
    { header: "Assignment", accessor: (r) => shortId((r as unknown as AssignmentRead).id) },
    { header: "User", accessor: (r) => shortId((r as unknown as AssignmentRead).user_id) },
    { header: "Profile", accessor: (r) => shortId((r as unknown as AssignmentRead).profile_id) },
    { header: "Node", accessor: (r) => shortId((r as unknown as AssignmentRead).node_id) },
    {
      header: "Provider",
      accessor: (r) => String((r as unknown as AssignmentRead).provider_kind ?? ""),
    },
    {
      header: "Limit",
      accessor: (r) => bytes((r as unknown as AssignmentRead).traffic_limit_bytes),
    },
    { header: "Status", accessor: (r) => String((r as unknown as AssignmentRead).status ?? "") },
    { header: "Expires", accessor: (r) => date((r as unknown as AssignmentRead).expires_at) },
  ],
  fetch: async () => (await listAssignments()) as CursorPage<Record<string, unknown>>,
  statusOf: (r) => String((r as unknown as AssignmentRead).status ?? "active"),
};

const profileSection: LiveSection = {
  columns: [
    { header: "Name", accessor: (r) => String((r as unknown as ProfileRead).name ?? "") },
    {
      header: "Provider",
      accessor: (r) => String((r as unknown as ProfileRead).provider_kind ?? ""),
    },
    { header: "Protocol", accessor: (r) => String((r as unknown as ProfileRead).protocol ?? "") },
    { header: "Node", accessor: (r) => shortId((r as unknown as ProfileRead).node_id) },
    { header: "Active", accessor: (r) => ((r as unknown as ProfileRead).is_active ? "yes" : "no") },
    { header: "Version", accessor: (r) => String((r as unknown as ProfileRead).version ?? "") },
    { header: "Updated", accessor: (r) => date((r as unknown as ProfileRead).updated_at) },
  ],
  fetch: async () => (await listProfiles()) as CursorPage<Record<string, unknown>>,
  statusOf: (r) => ((r as unknown as ProfileRead).is_active ? "active" : "disabled"),
};

const userSection: LiveSection = {
  columns: [
    { header: "Username", accessor: (r) => String((r as unknown as UserRead).username ?? "") },
    { header: "Email", accessor: (r) => String((r as unknown as UserRead).email ?? "") },
    { header: "Role", accessor: (r) => String((r as unknown as UserRead).role ?? "") },
    { header: "Active", accessor: (r) => ((r as unknown as UserRead).is_active ? "yes" : "no") },
    {
      header: "Verified",
      accessor: (r) => ((r as unknown as UserRead).is_verified ? "yes" : "no"),
    },
    { header: "Created", accessor: (r) => date((r as unknown as UserRead).created_at) },
  ],
  fetch: async () => (await listUsers()) as CursorPage<Record<string, unknown>>,
  statusOf: (r) => ((r as unknown as UserRead).is_active ? "active" : "disabled"),
};

const trafficSection: LiveSection = {
  columns: [
    { header: "Metric", accessor: (r) => String(r.metric ?? "") },
    { header: "Value", accessor: (r) => String(r.value ?? "") },
  ],
  fetch: async () => {
    const t = await trafficSummary();
    const rows: Record<string, unknown>[] = [
      { metric: "Total", value: bytes(t.total_bytes) },
      { metric: "Upload", value: bytes(t.upload_bytes) },
      { metric: "Download", value: bytes(t.download_bytes) },
      { metric: "Records", value: String(t.record_count) },
    ];
    return { items: rows, next_cursor: null, size: rows.length };
  },
  statusOf: () => "active",
};

const monitoringSection: LiveSection = {
  columns: [
    { header: "Metric", accessor: (r) => String(r.name ?? "") },
    { header: "Value", accessor: (r) => String(r.value ?? "") },
    { header: "Labels", accessor: (r) => JSON.stringify(r.labels ?? {}) },
  ],
  fetch: async () => {
    const snap = await monitoringSummary();
    const rows = snap.metrics.map((m) => m as unknown as Record<string, unknown>);
    return { items: rows, next_cursor: null, size: rows.length };
  },
  statusOf: () => "active",
};

const overviewSection: LiveSection = {
  columns: [
    { header: "Metric", accessor: (r) => String(r.metric ?? "") },
    { header: "Value", accessor: (r) => String(r.value ?? "") },
  ],
  fetch: async () => {
    const [nodes, profiles, assignments, users, traffic, monitoring] = await Promise.all([
      listNodes(),
      listProfiles(),
      listAssignments(),
      listUsers(),
      trafficSummary(),
      monitoringSummary(),
    ]);
    const rows: Record<string, unknown>[] = [
      { metric: "Total Nodes", value: String(nodes.size), raw: nodes.size },
      { metric: "Total Profiles", value: String(profiles.size), raw: profiles.size },
      { metric: "Total Assignments", value: String(assignments.size), raw: assignments.size },
      { metric: "Total Users", value: String(users.size), raw: users.size },
      { metric: "Total Traffic", value: bytes(traffic.total_bytes), raw: traffic.total_bytes },
      { metric: "Upload", value: bytes(traffic.upload_bytes), raw: traffic.upload_bytes },
      { metric: "Download", value: bytes(traffic.download_bytes), raw: traffic.download_bytes },
      { metric: "Metrics Collected", value: String(monitoring.metrics.length), raw: monitoring.metrics.length },
    ];
    return { items: rows, next_cursor: null, size: rows.length };
  },
  statusOf: () => "active",
};

const providerSection: LiveSection = {
  columns: [
    { header: "Name", accessor: (r) => String((r as unknown as ProviderRead).name ?? "") },
    { header: "Kind", accessor: (r) => String((r as unknown as ProviderRead).kind ?? "") },
    { header: "Version", accessor: (r) => String((r as unknown as ProviderRead).version ?? "") },
    {
      header: "Capabilities",
      accessor: (r) => {
        const caps = (r as unknown as ProviderRead).capabilities;
        return Array.isArray(caps) ? caps.join(", ") : "";
      },
    },
  ],
  fetch: async () => {
    const items = await listProviders();
    return { items: items as unknown as Record<string, unknown>[], next_cursor: null, size: items.length };
  },
  statusOf: () => "active",
};

export const LIVE_SECTIONS: Record<string, LiveSection> = {
  Overview: overviewSection,
  Nodes: nodeSection,
  Assignments: assignmentSection,
  Profiles: profileSection,
  Users: userSection,
  Traffic: trafficSection,
  Monitoring: monitoringSection,
  Providers: providerSection,
};
