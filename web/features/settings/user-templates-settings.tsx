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
import { SettingsSection } from "@/components/console/screens/settings-kit";

export function UserTemplatesSettingsScreen() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-templates"], queryFn: () => listUserTemplates() });
  const templates = q.data ?? [];
  const [open, setOpen] = useState(false);

  const remove = async (t: UserTemplateRead) => {
    if (!(await confirmDialog({ title: `Delete template "${t.name}"?`, confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteUserTemplate(t.id);
      toast("success", "Template deleted.");
      qc.invalidateQueries({ queryKey: ["user-templates"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  const fmt = (t: UserTemplateRead) => {
    const parts: string[] = [];
    parts.push(t.data_limit_bytes ? `${(t.data_limit_bytes / 1024 ** 3).toFixed(0)} GiB` : "∞ data");
    parts.push(t.expire_days ? `${t.expire_days}d` : "no expiry");
    parts.push(t.device_limit != null ? `${t.device_limit} devices` : "∞ devices");
    return parts.join(" · ");
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={LayoutTemplate}
        title="User templates"
        description="Presets for creating users fast — data limit, duration, device limit. Pick one in the Add user dialog."
      >
        <div className="warp-cert-actions">
          <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setOpen(true)}>
            <Plus size={14} aria-hidden /> New template
          </button>
        </div>
        {q.isLoading ? <p className="warp-cert-empty">Loading…</p> : null}
        {templates.length === 0 && !q.isLoading ? (
          <p className="warp-cert-empty">No templates yet. Create one to speed up user creation.</p>
        ) : null}
        <div className="warp-cert-list">
          {templates.map((t) => (
            <div key={t.id} className="warp-cert-row">
              <div className="warp-cert-row-head">
                <span className="warp-cert-name">{t.name}</span>
                <button type="button" className="warp-cert-del" onClick={() => remove(t)} aria-label="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="warp-cert-meta">
                <span>{fmt(t)}</span>
                {t.username_prefix ? (
                  <span>
                    Prefix: <b>{t.username_prefix}</b>
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
        data_limit_bytes: dataGib ? Math.round(Number(dataGib) * 1024 ** 3) : null,
        expire_days: expireDays ? Number(expireDays) : null,
        device_limit: devices ? Number(devices) : null,
        data_reset_strategy: reset,
        username_prefix: prefix.trim(),
      });
      toast("success", "Template created.");
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Create failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New user template"
      width="w-[min(560px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" variant="primary" disabled={busy || !name.trim()} onClick={submit}>
            {busy ? "Saving…" : "Create template"}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">Name</p>
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. 30-day 50GB" autoFocus />
      <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
        <label className="warp-field-row">
          <span className="warp-field-label">Data limit (GiB)</span>
          <Input type="number" min="0" step="1" value={dataGib} onChange={(e) => setDataGib(e.target.value)} placeholder="unlimited" />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">Duration (days)</span>
          <Input type="number" min="0" value={expireDays} onChange={(e) => setExpireDays(e.target.value)} placeholder="no expiry" />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">Device limit</span>
          <Input type="number" min="0" value={devices} onChange={(e) => setDevices(e.target.value)} placeholder="unlimited" />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">Auto-reset</span>
          <Select value={reset} onChange={(e) => setReset(e.target.value)}>
            <option value="no_reset">No reset</option>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
          </Select>
        </label>
      </div>
      <label className="warp-field-row" style={{ marginTop: 12 }}>
        <span className="warp-field-label">Username prefix (optional)</span>
        <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="e.g. vip_" />
      </label>
    </Modal>
  );
}
