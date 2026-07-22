"use client";

import { useQuery } from "@tanstack/react-query";
import { GitCommitVertical } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { type GitOpsRecordRead, gitopsRecords } from "@/lib/api";
import { SettingsSection } from "@/components/console/screens/settings-kit";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/components/console/screens/warp-table";

function relTime(iso: string): string {
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
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
  const q = useQuery({ queryKey: ["gitops-records"], queryFn: () => gitopsRecords(100) });
  const records = q.data ?? [];
  const [detail, setDetail] = useState<GitOpsRecordRead | null>(null);

  return (
    <div className="w-full">
      <SettingsSection
        icon={GitCommitVertical}
        title="Change history"
        description="Config snapshots and diffs committed across the panel — click a record to view its diff."
      >
        <WarpTableCard className="warp-users-table warp-edge-table warp-gitops-table">
          <WarpHead cols={["When", "Entity", "Action", "Actor", "Message"]} />
          {q.isLoading ? (
            <WarpSkeleton />
          ) : records.length === 0 ? (
            <WarpEmpty icon="fa-code-branch">No config changes recorded yet.</WarpEmpty>
          ) : (
            records.map((r) => (
              <WarpRow
                key={r.id}
                onClick={() => setDetail(r)}
                cells={[
                  <span className="text-fg-muted" title={new Date(r.created_at).toLocaleString()}>{relTime(r.created_at)}</span>,
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
              Close
            </button>
          }
        >
          <p className="text-sm text-fg-muted" style={{ marginBottom: 12 }}>
            {detail.actor ? `By ${detail.actor} · ` : ""}{new Date(detail.created_at).toLocaleString()}
            {detail.message ? ` · ${detail.message}` : ""}
          </p>
          <DiffBlock title="Added" tone="success" obj={detail.diff.added} />
          <DiffBlock title="Changed" tone="warning" obj={detail.diff.changed} />
          <DiffBlock title="Removed" tone="critical" obj={detail.diff.removed} />
          {!detail.diff.added && !detail.diff.changed && !detail.diff.removed ? (
            <p className="text-sm text-fg-muted">No field-level diff recorded for this change.</p>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
