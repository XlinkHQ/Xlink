"use client";

import { useQuery } from "@tanstack/react-query";
import { GitCommitVertical } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { type GitOpsRecordRead, gitopsRecords } from "@/lib/api";
import { useT, type TranslateFn } from "@/lib/i18n";
import { SettingsSection } from "@/shared/settings-kit";
import { WarpEmpty, WarpError, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { formatDate, formatDateTime } from "@/lib/format";

function relTime(iso: string, t: TranslateFn): string {
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return t("common.relTime.seconds", { n: s });
  if (s < 3600) return t("common.relTime.minutes", { n: Math.floor(s / 60) });
  if (s < 86400) return t("common.relTime.hours", { n: Math.floor(s / 3600) });
  if (s < 2592000) return t("common.relTime.days", { n: Math.floor(s / 86400) });
  return formatDate(iso);
}

function actionVariant(a: string): string {
  const u = a.toLowerCase();
  if (u.includes("delete") || u.includes("remove")) return "critical";
  if (u.includes("commit") || u.includes("create")) return "success";
  return "info";
}

function DiffBlock({ title, tone, obj }: { title: string; tone: string; obj: Record<string, unknown> | undefined }) {
  const keys = obj ? Object.keys(obj) : [];
  if (keys.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      <p className="warp-totp-label" style={{ marginBottom: 6 }}>
        <span className={`warp-badge ${tone}`}>{title}</span>
      </p>
      <pre className="warp-tb-mono" style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12, color: "var(--fg-muted)" }}>
        {JSON.stringify(obj, null, 2)}
      </pre>
    </div>
  );
}

export function GitOpsSettingsScreen() {
  const t = useT();
  const q = useQuery({ queryKey: ["gitops-records"], queryFn: () => gitopsRecords(100) });
  const records = q.data ?? [];
  const [detail, setDetail] = useState<GitOpsRecordRead | null>(null);

  return (
    <div className="w-full">
      <SettingsSection
        icon={GitCommitVertical}
        title={t("gitops.title")}
        description={t("gitops.description")}
      >
        <WarpTableCard className="warp-users-table warp-edge-table warp-gitops-table">
          <WarpHead cols={[t("gitops.col.when"), t("gitops.col.entity"), t("action.title"), t("gitops.col.actor"), t("gitops.col.message")]} />
          {q.isLoading ? (
            <WarpSkeleton />
          ) : q.isError ? (
            <WarpError onRetry={() => q.refetch()} />
          ) : records.length === 0 ? (
            <WarpEmpty>{t("gitops.empty")}</WarpEmpty>
          ) : (
            records.map((r) => (
              <WarpRow
                key={r.id}
                onClick={() => setDetail(r)}
                cells={[
                  <span className="text-fg-muted" title={formatDateTime(r.created_at)}>{relTime(r.created_at, t)}</span>,
                  <span className="font-medium">{r.entity_type}</span>,
                  <span className={`warp-badge ${actionVariant(r.action)}`}>{r.action}</span>,
                  <span className="text-fg-muted">{r.actor || "—"}</span>,
                  <span className="text-fg-muted">{r.message || "—"}</span>,
                ]}
              />
            ))
          )}
        </WarpTableCard>
      </SettingsSection>

      {detail ? (
        <Modal
          title={`${detail.entity_type} · ${detail.action}`}
          width="sm:w-[40rem]"
          onClose={() => setDetail(null)}
          footer={
            <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setDetail(null)}>
              {t("action.close")}
            </button>
          }
        >
          <p className="text-sm text-fg-muted" style={{ marginBottom: 12 }}>
            {detail.actor ? `${t("gitops.by", { actor: detail.actor })} · ` : ""}{formatDateTime(detail.created_at)}
            {detail.message ? ` · ${detail.message}` : ""}
          </p>
          <DiffBlock title={t("gitops.diff.added")} tone="success" obj={detail.diff.added} />
          <DiffBlock title={t("gitops.diff.changed")} tone="warning" obj={detail.diff.changed} />
          <DiffBlock title={t("gitops.diff.removed")} tone="critical" obj={detail.diff.removed} />
          {!detail.diff.added && !detail.diff.changed && !detail.diff.removed ? (
            <p className="text-sm text-fg-muted">{t("gitops.noDiff")}</p>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
