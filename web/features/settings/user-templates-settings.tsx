"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutTemplate, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createUserTemplate,
  deleteUserTemplate,
  listUserTemplates,
  type UserTemplateRead,
} from "@/lib/api";
import { fromGiB, toGiB } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { SettingsSection } from "@/shared/settings-kit";
import { WarpError } from "@/shared/warp-table";

export function UserTemplatesSettingsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-templates"], queryFn: () => listUserTemplates() });
  const templates = q.data ?? [];
  const [open, setOpen] = useState(false);

  const remove = async (tpl: UserTemplateRead) => {
    if (!(await confirmDialog({ title: t("userTemplates.deleteConfirmTitle", { name: tpl.name }), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await deleteUserTemplate(tpl.id);
      toast("success", t("userTemplates.deleted"));
      qc.invalidateQueries({ queryKey: ["user-templates"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("userTemplates.deleteFailed"));
    }
  };

  const fmt = (tpl: UserTemplateRead) => {
    const parts: string[] = [];
    parts.push(tpl.data_limit_bytes ? `${toGiB(tpl.data_limit_bytes).toFixed(0)} GiB` : t("userTemplates.unlimitedData"));
    parts.push(tpl.expire_days ? `${tpl.expire_days}d` : t("userTemplates.noExpiry"));
    parts.push(tpl.device_limit != null ? t("userTemplates.deviceCount", { n: tpl.device_limit }) : t("userTemplates.unlimitedDevices"));
    return parts.join(" · ");
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={LayoutTemplate}
        title={t("userTemplates.title")}
        description={t("userTemplates.description")}
      >
        <div className="warp-cert-actions">
          <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setOpen(true)}>
            <Plus size={14} aria-hidden /> {t("userTemplates.newTemplate")}
          </button>
        </div>
        {q.isLoading ? <p className="warp-cert-empty">{t("common.loading")}</p> : null}
        {q.isError && !q.isLoading ? <WarpError onRetry={() => q.refetch()} /> : null}
        {templates.length === 0 && !q.isLoading && !q.isError ? (
          <p className="warp-cert-empty">{t("userTemplates.empty")}</p>
        ) : null}
        <div className="warp-cert-list">
          {templates.map((tpl) => (
            <div key={tpl.id} className="warp-cert-row">
              <div className="warp-cert-row-head">
                <span className="warp-cert-name">{tpl.name}</span>
                <button type="button" className="warp-cert-del" onClick={() => remove(tpl)} aria-label={t("action.delete")}>
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="warp-cert-meta">
                <span>{fmt(tpl)}</span>
                {tpl.username_prefix ? (
                  <span>
                    {t("userTemplates.prefix")} <b>{tpl.username_prefix}</b>
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </SettingsSection>

      {open ? (
        <TemplateModal
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            qc.invalidateQueries({ queryKey: ["user-templates"] });
          }}
        />
      ) : null}
    </div>
  );
}

function TemplateModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [name, setName] = useState("");
  const [dataGib, setDataGib] = useState("");
  const [expireDays, setExpireDays] = useState("");
  const [devices, setDevices] = useState("");
  const [reset, setReset] = useState("no_reset");
  const [prefix, setPrefix] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await createUserTemplate({
        name: name.trim(),
        data_limit_bytes: dataGib ? fromGiB(Number(dataGib)) : null,
        expire_days: expireDays ? Number(expireDays) : null,
        device_limit: devices ? Number(devices) : null,
        data_reset_strategy: reset,
        username_prefix: prefix.trim(),
      });
      toast("success", t("userTemplates.created"));
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("userTemplates.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("userTemplates.newTemplateTitle")}
      width="w-[min(560px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button type="button" variant="primary" disabled={busy || !name.trim()} onClick={submit}>
            {busy ? t("common.saving") : t("userTemplates.createTemplate")}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">{t("common.name")}</p>
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("userTemplates.namePlaceholder")} autoFocus />
      <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("userTemplates.dataLimitLabel")}</span>
          <Input type="number" min="0" step="1" value={dataGib} onChange={(e) => setDataGib(e.target.value)} placeholder={t("userTemplates.unlimited")} />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("userTemplates.durationLabel")}</span>
          <Input type="number" min="0" value={expireDays} onChange={(e) => setExpireDays(e.target.value)} placeholder={t("userTemplates.noExpiryPlaceholder")} />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("userTemplates.deviceLimitLabel")}</span>
          <Input type="number" min="0" value={devices} onChange={(e) => setDevices(e.target.value)} placeholder={t("userTemplates.unlimited")} />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("userTemplates.autoReset")}</span>
          <Select value={reset} onChange={(e) => setReset(e.target.value)}>
            <option value="no_reset">{t("userTemplates.reset.noReset")}</option>
            <option value="day">{t("userTemplates.reset.daily")}</option>
            <option value="week">{t("userTemplates.reset.weekly")}</option>
            <option value="month">{t("userTemplates.reset.monthly")}</option>
          </Select>
        </label>
      </div>
      <label className="warp-field-row" style={{ marginTop: 12 }}>
        <span className="warp-field-label">{t("userTemplates.usernamePrefixLabel")}</span>
        <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder={t("userTemplates.prefixPlaceholder")} />
      </label>
    </Modal>
  );
}
