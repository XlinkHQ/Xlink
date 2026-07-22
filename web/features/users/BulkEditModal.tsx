"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { type BulkAction, bulkUserAction } from "@/lib/api";
import { fromGiB } from "@/lib/format";

export function BulkEditModal({
  kind,
  count,
  onClose,
  onApply,
}: {
  kind: "limit" | "expiry" | "reset";
  count: number;
  onClose: () => void;
  onApply: (
    action: BulkAction,
    params: Parameters<typeof bulkUserAction>[2],
    ok: string,
  ) => void;
}) {
  const [limitGb, setLimitGb] = useState("");
  const [expMode, setExpMode] = useState<"date" | "extend">("date");
  const [expDate, setExpDate] = useState("");
  const [extendDays, setExtendDays] = useState("30");
  const [strategy, setStrategy] = useState("no_reset");

  const title =
    kind === "limit" ? "Set data limit" : kind === "expiry" ? "Set expiry" : "Auto-reset usage";

  const apply = () => {
    if (kind === "limit") {
      const gb = Number(limitGb);
      onApply(
        "set_data_limit",
        { data_limit_bytes: limitGb.trim() === "" ? null : fromGiB(gb) },
        "Data limit set",
      );
    } else if (kind === "expiry") {
      if (expMode === "extend") {
        onApply("extend_expiry", { extend_days: Number(extendDays) || 0 }, "Expiry extended");
      } else {
        onApply(
          "set_expiry",
          { expire_at: expDate ? new Date(expDate + "T23:59:59").toISOString() : null },
          "Expiry set",
        );
      }
    } else {
      onApply("set_reset_strategy", { data_reset_strategy: strategy }, "Auto-reset set");
    }
  };

  return (
    <Modal
      title={`${title} · ${count} user${count === 1 ? "" : "s"}`}
      width="w-[min(460px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="primary" onClick={apply}>Apply</Button>
        </>
      }
    >
      {kind === "limit" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">Data limit (GiB)</span>
          <Input
            type="number"
            min="0"
            value={limitGb}
            onChange={(e) => setLimitGb(e.target.value)}
            placeholder="Leave empty for unlimited"
            autoFocus
          />
          <span className="warp-field-helper">Applies the same cap to every selected user. Empty = unlimited.</span>
        </label>
      ) : null}

      {kind === "expiry" ? (
        <>
          <label className="warp-field-row">
            <span className="warp-field-label">Mode</span>
            <Select value={expMode} onChange={(e) => setExpMode(e.target.value as "date" | "extend")}>
              <option value="date">Set a fixed date</option>
              <option value="extend">Extend by days</option>
            </Select>
          </label>
          {expMode === "date" ? (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">Expiry date</span>
              <Input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} />
              <span className="warp-field-helper">Empty clears the expiry (never expires).</span>
            </label>
          ) : (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">Extend by (days)</span>
              <Input type="number" min="1" value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
              <span className="warp-field-helper">Adds to each user&apos;s current expiry (or from now if none).</span>
            </label>
          )}
        </>
      ) : null}

      {kind === "reset" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">Auto-reset usage</span>
          <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="no_reset">No reset</option>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
            <option value="year">Yearly</option>
          </Select>
          <span className="warp-field-helper">Usage auto-zeroes each period for all selected users.</span>
        </label>
      ) : null}
    </Modal>
  );
}
