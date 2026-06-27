export const STATUSES = ["active", "maintenance", "offline", "disabled"];

export function isNodeOnline(status: string): boolean {
  return ["active", "online", "healthy"].includes(status.toLowerCase());
}

export function relativeTime(value: string | null): string {
  if (!value) return "never";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
