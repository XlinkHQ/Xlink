"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { ApiError, listUserDevices, resetUserDevices } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { WarpEmpty, WarpError, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { relTimeShort } from "./helpers";

export function UserDevicesTable({ userId, deviceLimit }: { userId: string; deviceLimit: number | null }) {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-devices", userId], queryFn: () => listUserDevices(userId) });
  const devices = q.data ?? [];
  const reset = async () => {
    if (!(await confirmDialog({ title: t("users.devices.resetConfirmTitle"), message: t("users.devices.resetConfirmMessage"), confirmLabel: t("users.devices.reset"), danger: true }))) return;
    try {
      await resetUserDevices(userId);
      toast("success", t("users.devices.resetSuccess"));
      qc.invalidateQueries({ queryKey: ["user-devices", userId] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("users.devices.resetFailed"));
    }
  };
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-fg-muted">
          {devices.length}{deviceLimit != null ? ` / ${deviceLimit}` : ""} {t("users.devices.bound")}
        </span>
        <button type="button" className="warp-dg-btn secondary" onClick={reset} disabled={devices.length === 0}>
          {t("users.devices.resetDevices")}
        </button>
      </div>
      <WarpTableCard className="warp-users-table warp-devices-table">
        <WarpHead cols={[t("users.devices.device"), t("users.devices.userAgent"), t("users.devices.lastSeen")]} />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : devices.length === 0 ? (
          <WarpEmpty>{t("users.devices.empty")}</WarpEmpty>
        ) : (
          devices.map((d) => (
            <WarpRow
              key={d.id}
              cells={[
                <span className="warp-tb-mono">{d.device_hash.slice(0, 12)}</span>,
                <span className="text-fg-muted" title={d.user_agent}>{d.user_agent || "—"}</span>,
                <span className="text-fg-muted">{relTimeShort(d.last_seen_at)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>
    </>
  );
}
