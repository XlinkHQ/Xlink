"use client";

import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createInboundHost,
  createProfile,
  generateProfileKeys,
  listProviders,
  scanRealityTargets,
  type NodeRead,
  type ProfileRead,
  updateProfile,
} from "@/lib/api";
import { Field } from "@/shared/parts";
import { InlineEditPanel } from "@/shared/settings-kit";
import { useT } from "@/lib/i18n";
import { PROTOCOLS, PROVIDERS, protocolsFor } from "./util";
import { BOOL_KEYS, NUMERIC_KEYS, type TField, TRANSPORT_KEYS, transportFields } from "./transport";

const TOP_KEYS = ["remark", "host", "port"];
const SECURITY_KEYS = new Set([
  "security",
  "sni",
  "dest",
  "privateKey",
  "publicKey",
  "shortId",
  "fingerprint",
  "alpn",
  "allowInsecure",
  "flow",
  "obfs",
  "obfsPassword",
  "shadowtls_version",
  "shadowtls_password",
]);
const CAMOUFLAGE_KEYS = new Set(["fragment", "noise", "randomUserAgent"]);
const MUX_KEYS = new Set(["mux"]);

export function ProfileDialog({
  profile,
  nodes,
  onClose,
  onSaved,
  variant = "modal",
}: {
  profile: ProfileRead | null;
  nodes: NodeRead[];
  onClose: () => void;
  onSaved: () => void;
  variant?: "modal" | "inline";
}) {
  const t = useT();
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: listProviders });
  const providerKinds =
    providersQuery.data && providersQuery.data.length > 0
      ? [...new Set(providersQuery.data.map((p) => p.kind))]
      : PROVIDERS;

  const [name, setName] = useState(profile?.name ?? "");
  const [slug, setSlug] = useState(profile?.slug ?? "");
  const [provider, setProvider] = useState(profile?.provider_kind ?? PROVIDERS[0]);
  const [nodeId, setNodeId] = useState(profile?.node_id ?? nodes[0]?.id ?? "");
  const [protocol, setProtocol] = useState(profile?.protocol ?? PROTOCOLS[0]);
  const initialSettings = (profile?.settings ?? {}) as Record<string, unknown>;
  const [cfg, setCfg] = useState<Record<string, string>>(() => {
    const c: Record<string, string> = {};
    for (const [k, v] of Object.entries(initialSettings)) {
      if (TRANSPORT_KEYS.includes(k)) c[k] = typeof v === "boolean" ? String(v) : String(v ?? "");
    }
    return c;
  });
  const [advanced, setAdvanced] = useState(() => {
    const extra = Object.fromEntries(
      Object.entries(initialSettings).filter(
        ([k]) => !TRANSPORT_KEYS.includes(k) && k !== "hosts",
      ),
    );
    return Object.keys(extra).length > 0 ? JSON.stringify(extra, null, 2) : "";
  });
  const [busy, setBusy] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const [jsonEdit, setJsonEdit] = useState(false);
  const advancedValid = (() => {
    if (!advanced.trim()) return true;
    try {
      const p = JSON.parse(advanced);
      return Boolean(p && typeof p === "object" && !Array.isArray(p));
    } catch {
      return false;
    }
  })();
  const existingHosts = Array.isArray((initialSettings as { hosts?: unknown }).hosts)
    ? (initialSettings as { hosts: unknown[] }).hosts
    : null;

  const setField = (k: string, v: string) => setCfg((c) => ({ ...c, [k]: v }));

  const generate = async () => {
    setGenBusy(true);
    try {
      const keys = await generateProfileKeys(protocol, cfg.security || "none");
      setCfg((c) => ({ ...c, ...keys }));
      toast("success", t("profiles.keysGenerated"));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("profiles.keysGenerateFailed"));
    } finally {
      setGenBusy(false);
    }
  };

  const [scanBusy, setScanBusy] = useState(false);
  const scanTarget = async () => {
    const target = (cfg.dest || cfg.sni || "").split(",")[0].trim();
    if (!target) {
      toast("error", t("profiles.realityScanEmpty"));
      return;
    }
    setScanBusy(true);
    try {
      const [r] = await scanRealityTargets([target]);
      if (r?.ok) {
        toast("success", t("profiles.realityScanOk", { ms: Math.round(r.latency_ms ?? 0) }));
      } else {
        toast("error", t("profiles.realityScanBad", { problems: r?.problems.join(", ") ?? "" }));
      }
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("profiles.realityScanBad", { problems: "" }));
    } finally {
      setScanBusy(false);
    }
  };

  const buildSettings = (): Record<string, unknown> => {
    const parsed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(cfg)) {
      if (v === "" || v == null) continue;
      if (NUMERIC_KEYS.has(k)) {
        const n = Number(v);
        if (!Number.isNaN(n)) parsed[k] = n;
      } else if (BOOL_KEYS.has(k)) {
        parsed[k] = v === "true";
      } else {
        parsed[k] = v;
      }
    }
    if (advanced.trim()) {
      try {
        Object.assign(parsed, JSON.parse(advanced));
      } catch {
      }
    }
    return parsed;
  };

  const previewJson = (() => {
    try {
      return JSON.stringify(buildSettings(), null, 2);
    } catch {
      return "{}";
    }
  })();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const parsed: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(cfg)) {
        if (v === "" || v == null) continue;
        if (NUMERIC_KEYS.has(k)) {
          const n = Number(v);
          if (!Number.isNaN(n)) parsed[k] = n;
        } else if (BOOL_KEYS.has(k)) {
          parsed[k] = v === "true";
        } else {
          parsed[k] = v;
        }
      }
      if (advanced.trim()) {
        try {
          Object.assign(parsed, JSON.parse(advanced));
        } catch {
          throw new ApiError(t("profiles.advancedJsonInvalid"), 400);
        }
      }
      if (existingHosts && existingHosts.length > 0) parsed.hosts = existingHosts;
      if (parsed.port != null) {
        const p = Number(parsed.port);
        if (!Number.isInteger(p) || p < 1 || p > 65535) {
          throw new ApiError(t("profiles.portRange"), 400);
        }
      }
      if (profile) {
        await updateProfile(profile.id, { name: name.trim(), protocol, settings: parsed });
      } else {
        const created = (await createProfile({
          name: name.trim(),
          slug:
            slug.trim() ||
            name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") ||
            "profile",
          provider_kind: provider,
          node_id: nodeId,
          protocol,
          settings: parsed,
        })) as { id?: string };
        const node = nodes.find((n) => n.id === nodeId);
        if (created?.id && node) {
          try {
            await createInboundHost({
              profile_id: created.id,
              remark: name.trim(),
              address: node.host,
              port: node.port,
            });
          } catch {
          }
        }
      }
      toast("success", profile ? t("profiles.updated") : t("profiles.created"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const seen = new Set<string>();
  const fields = transportFields(protocol, cfg).filter((f) => !seen.has(f.key) && seen.add(f.key));
  const pick = (keys: Set<string> | string[]) => {
    const set = Array.isArray(keys) ? new Set(keys) : keys;
    return fields.filter((f) => set.has(f.key));
  };
  const top = TOP_KEYS.map((k) => fields.find((f) => f.key === k)).filter(Boolean) as TField[];
  const security = pick(SECURITY_KEYS);
  const camouflage = pick(CAMOUFLAGE_KEYS);
  const mux = pick(MUX_KEYS);
  const used = new Set<string>([
    ...TOP_KEYS,
    ...security.map((f) => f.key),
    ...camouflage.map((f) => f.key),
    ...mux.map((f) => f.key),
  ]);
  const network = fields.filter((f) => !used.has(f.key));
  const showGenerate = cfg.security === "reality" || protocol === "wireguard";

  const Shell = variant === "inline" ? InlineEditPanel : Modal;
  return (
    <Shell
      title={profile ? t("profiles.editInbound") : t("profiles.addInbound")}
      onClose={onClose}
      onSubmit={submit}
      width="sm:w-[40rem]"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !name.trim() || (!profile && !nodeId)}
          >
            {busy ? t("common.saving") : profile ? t("action.save") : t("profiles.addInbound")}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">{t("profiles.tabGeneral")}</p>
      {!profile ? (
        <>
          <div className="warp-dlg-2col">
            <Field label={t("common.name")}>
              <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="off" />
            </Field>
            <Field label={t("profiles.slug")} hint={t("profiles.slugHint")}>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder={t("profiles.slugPlaceholder")} autoComplete="off" />
            </Field>
          </div>
          <div className="warp-dlg-2col">
            <Field label={t("profiles.providerCore")}>
              <Select
                value={provider}
                onChange={(e) => {
                  const next = e.target.value;
                  setProvider(next);
                  const allowed = protocolsFor(next);
                  if (!allowed.includes(protocol)) setProtocol(allowed[0]);
                }}
              >
                {providerKinds.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("profiles.node")}>
              <Select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                {nodes
                  .filter((n) => n.status?.toLowerCase() !== "disabled" || n.id === nodeId)
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name}
                    </option>
                  ))}
              </Select>
            </Field>
          </div>
          <Field label={t("profiles.protocol")}>
            <Select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
              {protocolsFor(provider).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
        </>
      ) : (
        <>
          <div className="warp-dlg-2col">
            <Field label={t("common.name")}>
              <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="off" />
            </Field>
            <Field label={t("profiles.protocol")}>
              <Select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
                {protocolsFor(provider).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <p className="text-[11px] text-fg-muted">
            {t("profiles.coreLabel")} <span className="font-medium text-fg">{provider}</span> · {t("profiles.node")}{" "}
            <span className="font-medium text-fg">
              {nodes.find((n) => n.id === nodeId)?.name ?? "—"}
            </span>
          </p>
        </>
      )}

      {top.length > 0 ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">{t("profiles.connection")}</p>
          <Grid fields={top} cfg={cfg} setField={setField} />
        </>
      ) : null}

      {network.length > 0 ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">{t("profiles.networkSettings")}</p>
          <Grid fields={network} cfg={cfg} setField={setField} />
        </>
      ) : null}

      {security.length > 0 ? (
        <>
          <div className="warp-dlg-divider" />
          <div className="flex items-center justify-between gap-3">
            <p className="warp-dlg-section-title">{t("profiles.securitySettings")}</p>
            <div className="flex items-center gap-3">
              {cfg.security === "reality" ? (
                <button
                  type="button"
                  onClick={scanTarget}
                  disabled={scanBusy}
                  className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
                >
                  {scanBusy ? t("profiles.realityScanning") : t("profiles.realityScan")}
                </button>
              ) : null}
              {showGenerate ? (
                <button
                  type="button"
                  onClick={generate}
                  disabled={genBusy}
                  className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
                >
                  {genBusy ? t("profiles.generating") : t("profiles.generateKeys")}
                </button>
              ) : null}
            </div>
          </div>
          <Grid fields={security} cfg={cfg} setField={setField} />
        </>
      ) : null}

      {camouflage.length > 0 ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">{t("profiles.camouflageSettings")}</p>
          <Grid fields={camouflage} cfg={cfg} setField={setField} />
        </>
      ) : null}

      {mux.length > 0 ? (
        <>
          <div className="warp-dlg-divider" />
          <p className="warp-dlg-section-title">{t("profiles.multiplexing")}</p>
          <Grid fields={mux} cfg={cfg} setField={setField} />
        </>
      ) : null}

      <div className="warp-dlg-divider" />
      <div className="flex items-center justify-between">
        <p className="warp-dlg-section-title" style={{ margin: 0 }}>
          {t("profiles.advancedJson")}
        </p>
        <button
          type="button"
          className="warp-cpe-tab"
          onClick={() => setJsonEdit((v) => !v)}
        >
          {jsonEdit ? t("profiles.preview") : t("action.edit")}
        </button>
      </div>
      {jsonEdit ? (
        <Field
          label={t("profiles.fullSettingsJson")}
          hint={t("profiles.fullSettingsJsonHint")}
        >
          <JsonArea value={advanced || previewJson} onChange={setAdvanced} invalid={!advancedValid} />
        </Field>
      ) : (
        <JsonArea value={previewJson} readOnly />
      )}
    </Shell>
  );
}

function JsonArea({
  value,
  onChange,
  readOnly,
  invalid,
}: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  invalid?: boolean;
}) {
  const lines = Math.max(1, value.split("\n").length);
  return (
    <div className={`warp-json-area${invalid ? " is-invalid" : ""}`}>
      <div className="warp-json-gutter" aria-hidden>
        {Array.from({ length: lines }, (_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
      <textarea
        value={value}
        onChange={onChange ? (e) => onChange(e.target.value) : undefined}
        readOnly={readOnly}
        spellCheck={false}
        rows={Math.min(24, Math.max(8, lines))}
        className="warp-json-input"
      />
    </div>
  );
}

function Grid({
  fields,
  cfg,
  setField,
}: {
  fields: TField[];
  cfg: Record<string, string>;
  setField: (k: string, v: string) => void;
}) {
  return (
    <div className="warp-dlg-2col">
      {fields.map((f) =>
        f.type === "bool" ? (
          <label key={f.key} className="col-span-2 flex items-center gap-2 text-xs text-fg">
            <input
              type="checkbox"
              checked={cfg[f.key] === "true"}
              onChange={(e) => setField(f.key, e.target.checked ? "true" : "")}
            />
            {f.label}
          </label>
        ) : (
          <Field key={f.key} label={f.label}>
            {f.type === "select" ? (
              <Select value={cfg[f.key] ?? ""} onChange={(e) => setField(f.key, e.target.value)}>
                {(f.options ?? []).map((o) => (
                  <option key={o} value={o}>
                    {o === "" ? "—" : o}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                type={f.type === "password" ? "password" : f.type === "number" ? "number" : "text"}
                value={cfg[f.key] ?? ""}
                onChange={(e) => setField(f.key, e.target.value)}
                placeholder={f.placeholder}
                autoComplete="off"
                {...(f.key === "port" ? { min: 1, max: 65535 } : {})}
              />
            )}
          </Field>
        ),
      )}
    </div>
  );
}
