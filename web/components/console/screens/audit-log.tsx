"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { type AuditEntry, listAudit } from "@/lib/api";
import { WarpBadge } from "./warp-table";

function methodTone(m: string): "green" | "blue" | "orange" | "red" | "gray" {
  if (m === "POST") return "green";
  if (m === "PUT" || m === "PATCH") return "blue";
  if (m === "DELETE") return "red";
  return "gray";
}

function relTime(iso: string): string {
  const d = Date.parse(iso);
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(d).toLocaleString();
}

export function AuditLogScreen() {
  const [actor, setActor] = useState("");
  const q = useQuery({
    queryKey: ["audit", actor],
    queryFn: () => listAudit({ limit: 300, actor: actor.trim() || undefined }),
    refetchInterval: 20000,
  });
  const entries = (q.data ?? []) as AuditEntry[];

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center justify-end gap-2">
        <span className="warp-tb-search-wrap" style={{ maxWidth: 220, flex: "none" }}>
          <Search style={{ position: "absolute", left: 14, color: "#707070", pointerEvents: "none" }} size={13} />
          <input
            className="warp-tb-search"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Filter by admin"
          />
        </span>
      </div>

      <div className="-mx-4 w-[calc(100%+2rem)] overflow-x-auto">
        <table className="w-full table-fixed border-collapse text-sm">
          <thead>
            <tr className="warp-thead text-left">
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">When</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Admin</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Action</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Method</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Path</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">IP</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-fg-muted">Loading…</td></tr>
            ) : entries.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-fg-muted">{actor ? "No audit entries for this admin." : "No audit entries yet."}</td></tr>
            ) : (
              entries.map((e) => (
                <tr key={e.id} className="hover:bg-muted">
                  <td className="px-4 py-2.5 text-fg-muted" title={new Date(e.created_at).toLocaleString()}>{relTime(e.created_at)}</td>
                  <td className="truncate px-4 py-2.5 font-medium text-fg">{e.actor_username || "—"}</td>
                  <td className="px-4 py-2.5 capitalize">{e.action}</td>
                  <td className="px-4 py-2.5"><WarpBadge tone={methodTone(e.method)}>{e.method}</WarpBadge></td>
                  <td className="truncate px-4 py-2.5 warp-tb-mono text-xs">{e.path}</td>
                  <td className="px-4 py-2.5 warp-tb-mono text-xs text-fg-muted">{e.ip_address || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
