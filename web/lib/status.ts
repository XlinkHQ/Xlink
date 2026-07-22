export function isNodeOnline(status: string): boolean {
  return ["active", "online", "healthy"].includes(status.toLowerCase());
}

export type UserStatus = "disabled" | "onhold" | "expired" | "limited" | "active";

export function userStatus(
  user: {
    is_active: boolean;
    on_hold?: boolean | null;
    expire_at?: string | null;
    data_limit_bytes?: number | null;
    users_data_usage?: number | null;
  },
  usedBytes?: number,
): UserStatus {
  if (!user.is_active) return "disabled";
  if (user.on_hold) return "onhold";
  if (user.expire_at != null && Date.parse(user.expire_at) < Date.now()) return "expired";
  const used = usedBytes ?? user.users_data_usage ?? 0;
  if (user.data_limit_bytes != null && used >= user.data_limit_bytes) return "limited";
  return "active";
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
