"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { type BulkAction, bulkUserAction } from "@/lib/api";
import { useT } from "@/lib/i18n";
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
  const t = useT();
  const [limitGb, setLimitGb] = useState("");
  const [expMode, setExpMode] = useState<"date" | "extend">("date");
  const [expDate, setExpDate] = useState("");
  const [extendDays, setExtendDays] = useState("30");
  const [strategy, setStrategy] = useState("no_reset");

  const title =
    kind === "limit"
      ? t("users.bulk.setDataLimit")
      : kind === "expiry"
        ? t("users.bulk.setExpiry")
        : t("users.bulk.autoResetUsage");

  const apply = () => {
    if (kind === "limit") {
      const gb = Number(limitGb);
      onApply(
        "set_data_limit",
        { data_limit_bytes: limitGb.trim() === "" ? null : fromGiB(gb) },
        t("users.bulk.dataLimitSet"),
      );
    } else if (kind === "expiry") {
      if (expMode === "extend") {
        onApply("extend_expiry", { extend_days: Number(extendDays) || 0 }, t("users.bulk.expiryExtended"));
      } else {
        onApply(
          "set_expiry",
          { expire_at: expDate ? new Date(expDate + "T23:59:59").toISOString() : null },
          t("users.bulk.expirySet"),
        );
      }
    } else {
      onApply("set_reset_strategy", { data_reset_strategy: strategy }, t("users.bulk.autoResetSet"));
    }
  };

  return (
    <Modal
      title={`${title} · ${count === 1 ? t("users.bulk.userCountOne", { n: count }) : t("users.bulk.userCountMany", { n: count })}`}
      width="w-[min(460px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>{t("action.cancel")}</Button>
          <Button type="button" variant="primary" onClick={apply}>{t("action.apply")}</Button>
        </>
      }
    >
      {kind === "limit" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">{t("users.field.dataLimitGib")}</span>
          <Input
            type="number"
            min="0"
            value={limitGb}
            onChange={(e) => setLimitGb(e.target.value)}
            placeholder={t("users.bulk.leaveEmptyUnlimited")}
            autoFocus
          />
          <span className="warp-field-helper">{t("users.bulk.dataLimitHelper")}</span>
        </label>
      ) : null}

      {kind === "expiry" ? (
        <>
          <label className="warp-field-row">
            <span className="warp-field-label">{t("users.bulk.mode")}</span>
            <Select value={expMode} onChange={(e) => setExpMode(e.target.value as "date" | "extend")}>
              <option value="date">{t("users.bulk.setFixedDate")}</option>
              <option value="extend">{t("users.bulk.extendByDays")}</option>
            </Select>
          </label>
          {expMode === "date" ? (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">{t("users.bulk.expiryDate")}</span>
              <Input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} />
              <span className="warp-field-helper">{t("users.bulk.expiryDateHelper")}</span>
            </label>
          ) : (
            <label className="warp-field-row" style={{ marginTop: 12 }}>
              <span className="warp-field-label">{t("users.bulk.extendByDaysLabel")}</span>
              <Input type="number" min="1" value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
              <span className="warp-field-helper">{t("users.bulk.extendHelper")}</span>
            </label>
          )}
        </>
      ) : null}

      {kind === "reset" ? (
        <label className="warp-field-row">
          <span className="warp-field-label">{t("users.field.autoResetUsage")}</span>
          <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="no_reset">{t("users.reset.noReset")}</option>
            <option value="day">{t("users.reset.daily")}</option>
            <option value="week">{t("users.reset.weekly")}</option>
            <option value="month">{t("users.reset.monthly")}</option>
            <option value="year">{t("users.reset.yearly")}</option>
          </Select>
          <span className="warp-field-helper">{t("users.bulk.resetHelper")}</span>
        </label>
      ) : null}
    </Modal>
  );
}
