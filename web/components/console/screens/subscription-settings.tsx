"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileCode,
  ListFilter,
  Pencil,
  Plus,
  RotateCcw,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Tags,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Input, Select } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  getSubscriptionSettings,
  type SubscriptionRule,
  type SubscriptionRuleResult,
  updateSubscriptionSettings,
} from "@/lib/api";
import { CodeEditor } from "./code-editor";
import { Modal } from "@/components/ui/modal";
import { SettingsRow, useRegisterSave } from "./settings";
import { SettingsSection } from "./settings-kit";
import { WarpBadge } from "./warp-table";

const PREVIEW_VALUES: Record<string, string> = {
  title: "Excore",
  username: "demo_user",
  status: "Active",
  used: "1.5 GB",
  total: "50 GB",
  percent: "3",
  expire: "27 days",
  sub_url: "https://panel.example.com/sub/demo",
  support: "https://t.me/support",
  count: "2",
  configs:
    '<div class="x-config"><code>vless://demo@1.2.3.4:443#Server-1</code><button>Copy</button></div>' +
    '<div class="x-config"><code>vless://demo@5.6.7.8:443#Server-2</code><button>Copy</button></div>',
  configs_raw: "vless://demo@1.2.3.4:443#Server-1\nvless://demo@5.6.7.8:443#Server-2",
};

function previewHtml(template: string): string {
  if (!template.trim()) return "<html><body style='font-family:sans-serif;padding:20px;color:#888'>Empty — built-in page is used.</body></html>";
  return template.replace(/\{\{(\w+)\}\}/g, (m, k) => PREVIEW_VALUES[k] ?? m);
}

const CUSTOM_PAGE_STARTER = `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{title}}</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0f1115;color:#e7e9ee;margin:0;padding:28px 20px;max-width:480px}
  h1{font-size:22px;margin:0 0 4px}
  .muted{color:#8b93a7;font-size:13px}
  .bar{height:8px;background:#1d2130;border-radius:99px;overflow:hidden;margin:18px 0 6px}
  .bar > i{display:block;height:100%;width:{{percent}}%;background:#4f8cff}
  .cfg{display:flex;gap:8px;align-items:center;background:#171a23;border-radius:10px;padding:10px 12px;margin-top:8px}
  .cfg code{flex:1;min-width:0;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#cdd3e0}
  .cfg button{background:#4f8cff;border:0;color:#fff;border-radius:7px;padding:6px 12px;font-size:12px;cursor:pointer}
  a{color:#4f8cff}
</style></head><body>
  <h1>{{title}}</h1>
  <div class="muted">{{username}} · {{status}}</div>
  <div class="bar"><i></i></div>
  <div class="muted">{{used}} / {{total}} · expires {{expire}}</div>
  <h3>Servers · {{count}}</h3>
  {{configs}}
  <p style="margin-top:20px"><a href="{{support}}">Need help?</a></p>
</body></html>`;

const RULE_RESULTS: SubscriptionRuleResult[] = [
  "links",
  "base64",
  "xray",
  "singbox",
  "clash",
  "clash-meta",
  "block",
];

export function SubscriptionSettingsScreen() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sub-settings"], queryFn: () => getSubscriptionSettings() });
  const [title, setTitle] = useState("");
  const [support, setSupport] = useState("");
  const [interval, setIntervalH] = useState("12");
  const [remark, setRemark] = useState("");
  const [shuffle, setShuffle] = useState(false);
  const [placeholderOn, setPlaceholderOn] = useState(true);
  const [placeholderRemark, setPlaceholderRemark] = useState("");
  const [customHtml, setCustomHtml] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [rules, setRules] = useState<SubscriptionRule[]>([]);
  const [texts, setTexts] = useState({
    active: "Active",
    expired: "Expired",
    limited: "Limited",
    disabled: "Disabled",
    onhold: "On-Hold",
  });
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (q.data && !loaded) {
      setTitle(q.data.profile_title);
      setSupport(q.data.support_link);
      setIntervalH(String(q.data.update_interval_hours));
      setRemark(q.data.config_remark);
      setShuffle(q.data.shuffle_configs);
      setPlaceholderOn(q.data.placeholder_if_disabled);
      setPlaceholderRemark(q.data.placeholder_remark);
      setCustomHtml(q.data.custom_page_html ?? "");
      setRules(q.data.rules ?? []);
      setTexts({
        active: q.data.active_status_text,
        expired: q.data.expired_status_text,
        limited: q.data.limited_status_text,
        disabled: q.data.disabled_status_text,
        onhold: q.data.onhold_status_text,
      });
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const save = async () => {
    setBusy(true);
    try {
      const saved = await updateSubscriptionSettings({
        profile_title: title.trim() || "XLink",
        support_link: support.trim(),
        update_interval_hours: Math.max(1, Math.min(168, Number(interval) || 12)),
        active_status_text: texts.active.trim() || "Active",
        expired_status_text: texts.expired.trim() || "Expired",
        limited_status_text: texts.limited.trim() || "Limited",
        disabled_status_text: texts.disabled.trim() || "Disabled",
        onhold_status_text: texts.onhold.trim() || "On-Hold",
        config_remark: remark.trim(),
        shuffle_configs: shuffle,
        placeholder_if_disabled: placeholderOn,
        placeholder_remark: placeholderRemark.trim() || "Subscription disabled",
        custom_page_html: customHtml,
        rules: rules.filter((r) => r.pattern.trim() !== ""),
      });
      toast("success", "Subscription settings saved.");
      // Seed the cache with the server's normalized response instead of re-arming
      // the one-time latch (which would re-seed from stale cache and revert edits).
      qc.setQueryData(["sub-settings"], saved);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };
  useRegisterSave(save, busy);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Settings2}
        title="General"
        description="Core subscription details shown to clients when they load the profile."
      >
        <SettingsRow label="Profile title" hint="Shown as the subscription profile name in client apps.">
          <input className="warp-set-input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="XLink" />
        </SettingsRow>
        <SettingsRow label="Update interval" hint="How often clients refresh (hours).">
          <input className="warp-set-input" type="number" min="1" max="168" value={interval} onChange={(e) => setIntervalH(e.target.value)} />
        </SettingsRow>
        <SettingsRow label="Support link" hint="Shown to users on the subscription page.">
          <input className="warp-set-input" value={support} onChange={(e) => setSupport(e.target.value)} placeholder="https://t.me/yoursupport" />
        </SettingsRow>
        <SettingsRow label="Config name" hint="Template for each config's display name.">
          <input className="warp-set-input font-mono" value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="{PROTOCOL} | {USERNAME}" />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        divider
        icon={Tags}
        title="Status labels"
        description="Rename the label appended to each config for the user's current account state."
      >
        {(
          [
            ["active", "Active config label"],
            ["expired", "Expired config label"],
            ["limited", "Limited config label"],
            ["disabled", "Disabled config label"],
            ["onhold", "On-hold config label"],
          ] as Array<[keyof typeof texts, string]>
        ).map(([key, label]) => (
          <SettingsRow key={key} label={label}>
            <input className="warp-set-input" value={texts[key]} onChange={(e) => setTexts((t) => ({ ...t, [key]: e.target.value }))} placeholder={label} />
          </SettingsRow>
        ))}
      </SettingsSection>

      <SettingsSection
        divider
        icon={SlidersHorizontal}
        title="Delivery behavior"
        description="Control how configs are ordered and what inactive users receive."
      >
        <SettingsRow label="Shuffle configs" hint="Randomise config order on every fetch to spread client load.">
          <Switch checked={shuffle} onChange={setShuffle} />
        </SettingsRow>
        <SettingsRow label="Placeholder when disabled" hint="Serve one dummy config to expired/limited/disabled users.">
          <Switch checked={placeholderOn} onChange={setPlaceholderOn} />
        </SettingsRow>
        {placeholderOn ? (
          <SettingsRow label="Placeholder config name" hint="The dummy config name shown to inactive users.">
            <input className="warp-set-input" value={placeholderRemark} onChange={(e) => setPlaceholderRemark(e.target.value)} placeholder="Subscription expired — contact support" />
          </SettingsRow>
        ) : null}
      </SettingsSection>

      <SettingsSection
        divider
        icon={FileCode}
        title="Custom subscription page"
        description={
          customHtml.trim()
            ? "A custom HTML page is set — shown when the link opens in a browser."
            : "Leave empty to use the built-in page."
        }
      >
        <div className="flex items-center justify-end gap-1.5">
          {customHtml.trim() ? <WarpBadge tone="green">Custom</WarpBadge> : <WarpBadge tone="gray">Default</WarpBadge>}
          <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setEditorOpen(true)}>
            <Pencil size={14} /> Edit
          </button>
        </div>
      </SettingsSection>

      {editorOpen ? (
        <CustomPageEditor
          value={customHtml}
          onChange={setCustomHtml}
          onClose={() => setEditorOpen(false)}
        />
      ) : null}

      <SettingsSection
        divider
        icon={ListFilter}
        title="User-Agent rules"
        description="First match wins; regex on the client User-Agent maps to a format (or block)."
      >
          <div className="mb-2 flex items-center justify-end">
            <button
              type="button"
              className="warp-tb-button"
              onClick={() => setRules((r) => [...r, { pattern: "", result: "links" }])}
            >
              <Plus size={14} /> Add rule
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {rules.map((rule, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  className="h-9 flex-1 font-mono"
                  value={rule.pattern}
                  onChange={(e) =>
                    setRules((r) => r.map((x, j) => (j === i ? { ...x, pattern: e.target.value } : x)))
                  }
                  placeholder="(?i)^clash"
                />
                <Select
                  className="h-9 w-32"
                  value={rule.result}
                  onChange={(e) =>
                    setRules((r) =>
                      r.map((x, j) =>
                        j === i ? { ...x, result: e.target.value as SubscriptionRuleResult } : x,
                      ),
                    )
                  }
                >
                  {RULE_RESULTS.map((res) => (
                    <option key={res} value={res}>
                      {res}
                    </option>
                  ))}
                </Select>
                <button
                  type="button"
                  onClick={() => setRules((r) => r.filter((_, j) => j !== i))}
                  className="grid h-9 w-9 flex-none place-items-center rounded-md text-fg-muted hover:bg-muted hover:text-danger"
                  aria-label="Remove rule"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
      </SettingsSection>
    </div>
  );
}

export function Switch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={
        "relative inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors " +
        (checked ? "bg-primary" : "bg-line")
      }
    >
      <span
        className={
          "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform " +
          (checked ? "translate-x-4" : "translate-x-0.5")
        }
      />
    </button>
  );
}

function CheckRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-primary"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-fg">{label}</span>
        <span className="text-xs text-fg-muted">{description}</span>
      </span>
    </label>
  );
}

function CustomPageEditor({
  value,
  onChange,
  onClose,
}: {
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"code" | "preview">("code");
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  return (
    <Modal
      title="Custom subscription page"
      width="w-[min(960px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="warp-tb-button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            onClick={() => {
              onChange(draft);
              onClose();
            }}
          >
            Apply
          </button>
        </>
      }
    >
      <div className="flex items-center justify-between gap-2">
        <div className="warp-cpe-tabs">
          <button type="button" onClick={() => setMode("code")} className={`warp-cpe-tab ${mode === "code" ? "is-active" : ""}`}>
            Editor
          </button>
          <button type="button" onClick={() => setMode("preview")} className={`warp-cpe-tab ${mode === "preview" ? "is-active" : ""}`}>
            Preview
          </button>
        </div>
        {draft.trim() ? (
          <button type="button" className="warp-tb-button" onClick={() => setDraft("")}>
            <RotateCcw size={14} /> Clear
          </button>
        ) : (
          <button type="button" className="warp-tb-button" onClick={() => setDraft(CUSTOM_PAGE_STARTER)}>
            <Sparkles size={14} /> Starter
          </button>
        )}
      </div>

      {mode === "code" ? (
        <CodeEditor
          value={draft}
          onChange={setDraft}
          rows={20}
          light
          placeholder="<!DOCTYPE html> … use {{configs}} to inject the config list"
        />
      ) : (
        <iframe
          title="Custom page preview"
          className="warp-code-preview"
          sandbox="allow-scripts"
          srcDoc={previewHtml(draft)}
        />
      )}
    </Modal>
  );
}
