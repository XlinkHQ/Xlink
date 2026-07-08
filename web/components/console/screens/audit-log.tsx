"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, X } from "lucide-react";
import { useState } from "react";
import { ApiError, type AuditEntry, downloadAuditCsv, listAudit } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { DatePicker } from "@/components/ui/calendar";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "./warp-table";
import { DgSearch } from "../dg-icons";

type BadgeVariant = "success" | "critical" | "neutral" | "warning" | "info";

function methodVariant(m: string): BadgeVariant {
  const u = m.toUpperCase();
  if (u === "GET") return "info";
  if (u === "POST" || u === "PUT") return "success";
  if (u === "DELETE") return "critical";
  return "neutral";
}

function relTime(iso: string): string {
  const d = Date.parse(iso);
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(d).toLocaleString();
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

export function AuditLogScreen() {
  const [actor, setActor] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const q = useQuery({
    queryKey: ["audit", actor, dateFrom, dateTo],
    queryFn: () =>
      listAudit({
        limit: 300,
        actor: actor.trim() || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    refetchInterval: 20000,
  });
  const entries = (q.data ?? []) as AuditEntry[];

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">Activity log</span>
        <div className="right">
          <div className="warp-daterange">
            <CalendarDays size={16} className="warp-daterange-ico" aria-hidden />
            <DatePicker value={dateFrom} onChange={setDateFrom} placeholder="From" />
            <span className="warp-daterange-sep">→</span>
            <DatePicker value={dateTo} onChange={setDateTo} placeholder="To" />
            {dateFrom || dateTo ? (
              <button
                type="button"
                className="warp-daterange-clear"
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                }}
                aria-label="Clear dates"
              >
                <X size={13} />
              </button>
            ) : null}
          </div>
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="Filter by admin"
            />
          </span>
          <button
            type="button"
            className="warp-tb-button"
            onClick={async () => {
              try {
                await downloadAuditCsv({
                  actor: actor.trim() || undefined,
                  dateFrom: dateFrom || undefined,
                  dateTo: dateTo || undefined,
                });
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : "Export failed.");
              }
            }}
          >
            Export CSV
          </button>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Date", "Admin", "Action", "Method", "Path", "IP"]} />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : entries.length === 0 ? (
          <WarpEmpty icon="shield-halved">
            {actor.trim() ? "No entries for this admin." : "No audit entries yet."}
          </WarpEmpty>
        ) : (
          <>
            {entries.map((e) => (
              <WarpRow
                key={e.id}
                cells={[
                  <span key="date" title={new Date(e.created_at).toLocaleString()}>
                    {relTime(e.created_at)}
                  </span>,
                  e.actor_username || "—",
                  cap(e.action),
                  <span key="method" className={`warp-badge ${methodVariant(e.method)}`}>
                    {e.method}
                  </span>,
                  <span key="path" className="warp-tb-mono text-fg-muted">
                    {e.path}
                  </span>,
                  <span key="ip" className="warp-tb-mono text-fg-muted">
                    {e.ip_address || "—"}
                  </span>,
                ]}
              />
            ))}
          </>
        )}
      </WarpTableCard>
    </div>
  );
}
