"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { ApiError, listUserDevices, resetUserDevices } from "@/lib/api";
import { WarpEmpty, WarpHead, WarpRow, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";
import { relTimeShort } from "./helpers";

export function UserDevicesTable({ userId, deviceLimit }: { userId: string; deviceLimit: number | null }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-devices", userId], queryFn: () => listUserDevices(userId) });
  const devices = q.data ?? [];
  const reset = async () => {
    if (!(await confirmDialog({ title: "Reset this user's devices?", message: "All device bindings are removed; the user can re-bind up to the limit.", confirmLabel: "Reset", danger: true }))) return;
    try {
      await resetUserDevices(userId);
      toast("success", "Devices reset.");
      qc.invalidateQueries({ queryKey: ["user-devices", userId] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Reset failed.");
    }
  };
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-fg-muted">
          {devices.length}{deviceLimit != null ? ` / ${deviceLimit}` : ""} bound
        </span>
        <button type="button" className="warp-dg-btn secondary" onClick={reset} disabled={devices.length === 0}>
          Reset devices
        </button>
      </div>
      <WarpTableCard className="warp-users-table warp-devices-table">
        <WarpHead cols={["Device", "User agent", "Last seen"]} />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : devices.length === 0 ? (
          <WarpEmpty icon="fa-mobile">No devices bound.</WarpEmpty>
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
