"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Modal } from "@/components/ui/modal";
import { Input, Select } from "@/components/ui/input";
import { Field } from "@/shared/parts";
import {
  ApiError,
  type ClientTemplate,
  createClientTemplate,
  deleteClientTemplate,
  listClientTemplates,
  type TemplateFormat,
  updateClientTemplate,
} from "@/lib/api";
import {
  WarpButton,
  WarpEmpty,
  WarpError,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { DgAddUser } from "@/components/console/dg-icons";
import { JsonEditor } from "@/features/nodes/json-editor";
import { useT } from "@/lib/i18n";
import { formatDate } from "@/lib/format";

const FORMATS: TemplateFormat[] = ["clash", "mihomo", "singbox"];

const STARTERS: Record<TemplateFormat, string> = {
  clash: `mixed-port: 7890
allow-lan: false
mode: rule
dns:
  enable: true
  nameserver: [1.1.1.1, 8.8.8.8]
proxy-groups:
  - name: Auto
    type: url-test
    url: https://cp.cloudflare.com
    interval: 300
    proxies: ["{ALL}"]
  - name: PROXY
    type: select
    proxies: [Auto, "{ALL}", DIRECT]
rules:
  - GEOIP,private,DIRECT
  - MATCH,PROXY
`,
  mihomo: "",
  singbox: `{
  "log": { "level": "warn" },
  "dns": { "servers": [{ "tag": "remote", "address": "https://1.1.1.1/dns-query" }] },
  "inbounds": [{ "type": "tun", "tag": "tun-in", "address": ["172.19.0.1/30"], "auto_route": true }],
  "outbounds": [
    { "type": "urltest", "tag": "auto", "outbounds": ["{ALL}"] },
    { "type": "selector", "tag": "proxy", "outbounds": ["auto", "{ALL}"] },
    { "type": "direct", "tag": "direct" }
  ],
  "route": { "final": "proxy", "auto_detect_interface": true }
}
`,
};
STARTERS.mihomo = STARTERS.clash;

export function ClientTemplatesScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["client-templates"], queryFn: () => listClientTemplates() });
  const rows = (q.data ?? []) as ClientTemplate[];
  const [editing, setEditing] = useState<ClientTemplate | "new" | null>(null);

  const reload = () => qc.invalidateQueries({ queryKey: ["client-templates"] });

  const remove = async (tpl: ClientTemplate) => {
    if (
      !(await confirmDialog({
        title: t("templates.deleteTitle", { name: tpl.name }),
        message: t("templates.deleteMessage"),
        confirmLabel: t("action.delete"),
        danger: true,
      }))
    )
      return;
    try {
      await deleteClientTemplate(tpl.id);
      toast("success", t("templates.deleted"));
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
    }
  };

  const makeDefault = async (tpl: ClientTemplate) => {
    try {
      await updateClientTemplate(tpl.id, { is_default: !tpl.is_default });
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("nav.clientTemplates")}</span>
        <div className="right">
          <WarpButton primary onClick={() => setEditing("new")}>
            <DgAddUser size={16} /> {t("templates.add")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead
          cols={[t("common.name"), t("templates.format"), t("templates.default"), t("common.updated")]}
          actions
        />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : rows.length === 0 ? (
          <WarpEmpty>{t("templates.empty")}</WarpEmpty>
        ) : (
          rows.map((tpl) => (
            <WarpRow
              key={tpl.id}
              onClick={() => setEditing(tpl)}
              menu={[
                { label: t("action.edit"), icon: "edit", onClick: () => setEditing(tpl) },
                {
                  label: tpl.is_default ? t("templates.unsetDefault") : t("templates.setDefault"),
                  icon: tpl.is_default ? "disable" : "check",
                  onClick: () => makeDefault(tpl),
                },
                { label: t("action.delete"), icon: "trash", danger: true, onClick: () => remove(tpl) },
              ]}
              cells={[
                <span className="font-medium">{tpl.name}</span>,
                <span className="text-fg-muted">{tpl.format}</span>,
                <span className="text-fg-muted">{tpl.is_default ? t("templates.yes") : "—"}</span>,
                <span className="text-fg-muted">{formatDate(tpl.updated_at)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

      {editing ? (
        <TemplateDialog
          template={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
    </div>
  );
}

function TemplateDialog({
  template,
  onClose,
  onSaved,
}: {
  template: ClientTemplate | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(template?.name ?? "");
  const [format, setFormat] = useState<TemplateFormat>(template?.format ?? "clash");
  const [content, setContent] = useState(template?.content ?? STARTERS.clash);
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (template) {
        await updateClientTemplate(template.id, { name: name.trim(), content, is_default: isDefault });
      } else {
        await createClientTemplate({ name: name.trim(), format, content, is_default: isDefault });
      }
      toast("success", t("templates.saved"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={template ? t("templates.edit") : t("templates.add")}
      onClose={onClose}
      onSubmit={submit}
      width="sm:w-[46rem]"
      footer={
        <>
          <button type="button" className="warp-tb-button" onClick={onClose} disabled={busy}>
            {t("action.cancel")}
          </button>
          <button
            type="submit"
            className="warp-tb-button warp-tb-button-primary"
            disabled={busy || !name.trim() || content.trim().length < 2}
          >
            {busy ? t("common.saving") : t("action.save")}
          </button>
        </>
      }
    >
      <div className="warp-dlg-2col">
        <Field label={t("common.name")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="off" />
        </Field>
        <Field label={t("templates.format")}>
          <Select
            value={format}
            disabled={!!template}
            onChange={(e) => {
              const next = e.target.value as TemplateFormat;
              // Swap the starter only while it is still untouched.
              if (content === STARTERS[format]) setContent(STARTERS[next]);
              setFormat(next);
            }}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label={t("templates.content")} hint={t("templates.contentHint")}>
        <JsonEditor value={content} onChange={setContent} rows={18} />
      </Field>
      <label className="flex items-center gap-2 text-sm text-fg">
        <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
        {t("templates.useAsDefault")}
      </label>
    </Modal>
  );
}
