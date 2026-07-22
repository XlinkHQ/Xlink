"use client";

import { useMemo } from "react";
import { type UserRead } from "@/lib/api";
import { userStatus } from "@/lib/status";
import type { SortCol, SortDir } from "./components";

type UsageEntry = { user_id: string; used_bytes: number };

export function useUserFilters(args: {
  users: UserRead[];
  search: string;
  statusFilter: string;
  sortCol: SortCol | null;
  sortDir: SortDir;
  usageMap: Map<string, UsageEntry>;
  onlineSet: Set<string>;
}): { filtered: UserRead[]; maxUsed: number } {
  const { users, search, statusFilter, sortCol, sortDir, usageMap, onlineSet } = args;
  const needle = search.trim().toLowerCase();

  const filtered = useMemo(() => {
    const now = Date.now();
    const matchStatus = (u: UserRead): boolean => {
      if (statusFilter === "all") return true;
      const used = usageMap.get(u.id)?.used_bytes ?? 0;
      const reached = u.data_limit_bytes != null && used >= u.data_limit_bytes;
      const expired = u.expire_at != null && Date.parse(u.expire_at) < now;
      const s = userStatus(u, used);
      switch (statusFilter) {
        case "online": return onlineSet.has(u.id);
        case "active": return u.is_active && !expired && !reached;
        case "disabled": return s === "disabled";
        case "expired": return expired;
        case "limited": return reached;
        default: return false;
      }
    };
    return users
      .filter((u) => (needle ? [u.username, u.email, u.role].some((v) => String(v).toLowerCase().includes(needle)) : true))
      .filter(matchStatus)
      .sort((a, b) => {
        if (!sortCol) return Date.parse(b.created_at) - Date.parse(a.created_at);
        const dir = sortDir === "asc" ? 1 : -1;
        const ua = usageMap.get(a.id)?.used_bytes ?? 0;
        const ub = usageMap.get(b.id)?.used_bytes ?? 0;
        switch (sortCol) {
          case "name": return (a.full_name || a.username).localeCompare(b.full_name || b.username) * dir;
          case "email": return String(a.email ?? "").localeCompare(String(b.email ?? "")) * dir;
          case "username": return a.username.localeCompare(b.username) * dir;
          case "online": return ((onlineSet.has(b.id) ? 1 : 0) - (onlineSet.has(a.id) ? 1 : 0)) * dir;
          case "status": return ((a.is_active ? 1 : 0) - (b.is_active ? 1 : 0)) * dir;
          case "traffic": return (ua - ub) * dir;
          case "expiration": return ((a.expire_at ? Date.parse(a.expire_at) : Infinity) - (b.expire_at ? Date.parse(b.expire_at) : Infinity)) * dir;
          default: return 0;
        }
      });
  }, [users, needle, statusFilter, sortCol, sortDir, usageMap, onlineSet]);

  const maxUsed = useMemo(
    () => users.reduce((m, u) => Math.max(m, usageMap.get(u.id)?.used_bytes ?? 0), 0),
    [users, usageMap],
  );

  return { filtered, maxUsed };
}
