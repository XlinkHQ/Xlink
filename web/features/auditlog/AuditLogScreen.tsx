"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, X } from "lucide-react";
import { useState } from "react";
import { ApiError, type AuditEntry, downloadAuditCsv, listAudit } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { DatePicker } from "@/components/ui/calendar";
import { WarpEmpty, WarpError, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { DgSearch } from "@/components/console/dg-icons";
import { type TranslateFn, useT } from "@/lib/i18n";
import { formatDateTime } from "@/lib/format";

type BadgeVariant = "success" | "critical" | "neutral" | "warning" | "info";

function methodVariant(m: string): BadgeVariant {
  const u = m.toUpperCase();
  if (u === "GET") return "info";
  if (u === "POST" || u === "PUT") return "success";
  if (u === "DELETE") return "critical";
  return "neutral";
}

function relTime(iso: string, t: TranslateFn): string {
  const d = Date.parse(iso);
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return t("common.secondsAgo", { n: s });
  if (s < 3600) return t("common.minutesAgo", { n: Math.floor(s / 60) });
  if (s < 86400) return t("common.hoursAgo", { n: Math.floor(s / 3600) });
  return formatDateTime(d);
}

function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

export function AuditLogScreen() {
  const t = useT();
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
    refetchIntervalInBackground: false,
  });
  const entries = (q.data ?? []) as AuditEntry[];

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("auditlog.title")}</span>
        <div className="right">
          <div className="warp-daterange">
            <CalendarDays size={16} className="warp-daterange-ico" aria-hidden />
            <DatePicker value={dateFrom} onChange={setDateFrom} placeholder={t("auditlog.from")} />
            <span className="warp-daterange-sep">→</span>
            <DatePicker value={dateTo} onChange={setDateTo} placeholder={t("auditlog.to")} />
            {dateFrom || dateTo ? (
              <button
                type="button"
                className="warp-daterange-clear"
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                }}
                aria-label={t("auditlog.clearDates")}
              >
                <X size={13} aria-hidden />
              </button>
            ) : null}
          </div>
          <span className="warp-tb-search-wrap" style={{ maxWidth: 321, flex: 1 }}>
            <DgSearch size={16} />
            <input
              className="warp-tb-search"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder={t("auditlog.filterByAdmin")}
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
                toast("error", e instanceof ApiError ? e.message : t("auditlog.exportFailed"));
              }
            }}
          >
            {t("auditlog.exportCsv")}
          </button>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("auditlog.date"), t("auditlog.admin"), t("auditlog.action"), t("auditlog.method"), t("auditlog.path"), t("auditlog.ip")]} />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : entries.length === 0 ? (
          <WarpEmpty>
            {actor.trim() ? t("auditlog.noEntriesForAdmin") : t("auditlog.noEntries")}
          </WarpEmpty>
        ) : (
          <>
            {entries.map((e) => (
              <WarpRow
                key={e.id}
                cells={[
                  <span key="date" title={formatDateTime(e.created_at)}>
                    {relTime(e.created_at, t)}
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
