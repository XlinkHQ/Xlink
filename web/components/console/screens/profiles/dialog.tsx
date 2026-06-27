"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createInboundHost,
  createProfile,
  generateProfileKeys,
  listProviders,
  type NodeRead,
  type ProfileRead,
  updateProfile,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Field } from "../parts";
import { PROTOCOLS, PROVIDERS, protocolsFor } from "./util";
import { BOOL_KEYS, NUMERIC_KEYS, type TField, TRANSPORT_KEYS, transportFields } from "../transport";

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
}: {
  profile: ProfileRead | null;
  nodes: NodeRead[];
  onClose: () => void;
  onSaved: () => void;
}) {
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
  const existingHosts = Array.isArray((initialSettings as { hosts?: unknown }).hosts)
    ? (initialSettings as { hosts: unknown[] }).hosts
    : null;

  const setField = (k: string, v: string) => setCfg((c) => ({ ...c, [k]: v }));

  const generate = async () => {
    setGenBusy(true);
    try {
      const keys = await generateProfileKeys(protocol, cfg.security || "none");
      setCfg((c) => ({ ...c, ...keys }));
      toast("success", "Keys generated.");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not generate keys.");
    } finally {
      setGenBusy(false);
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
        /* preview ignores invalid json */
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
          throw new ApiError("Advanced settings must be valid JSON.", 400);
        }
      }
      if (existingHosts && existingHosts.length > 0) parsed.hosts = existingHosts;
      if (parsed.port != null) {
        const p = Number(parsed.port);
        if (!Number.isInteger(p) || p < 1 || p > 65535) {
          throw new ApiError("Port must be between 1 and 65535.", 400);
        }
      }
      if (profile) {
        await updateProfile(profile.id, { name: name.trim(), protocol, settings: parsed });
      } else {
        const created = (await createProfile({
          name: name.trim(),
          slug: slug.trim() || name.trim().toLowerCase().replace(/\s+/g, "-"),
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
            /* default address is optional */
          }
        }
      }
      toast("success", profile ? "Inbound updated." : "Inbound created.");
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Save failed.");
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

  return (
    <div className="warp-dlg-overlay" onMouseDown={onClose}>
      <form className="warp-dlg" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="warp-dlg-header">
          <span className="warp-dlg-grab" />
          <p>{profile ? "Edit Inbound" : "Add Inbound"}</p>
        </div>

        <div className="warp-dlg-body warp-dlg-body-flow">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        {!profile ? (
          <>
            <Field label="Slug">
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="auto from name" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Provider (core)">
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
              <Field label="Node">
                <Select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                  {nodes.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </>
        ) : (
          <div className="rounded-md bg-subtle px-2.5 py-1.5 text-[11px] text-fg-muted">
            Core <span className="font-medium text-fg">{provider}</span> · Node{" "}
            <span className="font-medium text-fg">
              {nodes.find((n) => n.id === nodeId)?.name ?? "—"}
            </span>
          </div>
        )}
        <Field label="Protocol">
          <Select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
            {protocolsFor(provider).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>
        </Field>

        {/* Common fields — always visible */}
        {top.length > 0 ? <Grid fields={top} cfg={cfg} setField={setField} /> : null}

        <div>
        {network.length > 0 ? (
          <Section title="Network settings" defaultOpen>
            <Grid fields={network} cfg={cfg} setField={setField} />
          </Section>
        ) : null}
        {security.length > 0 ? (
          <Section
            title="Security settings"
            action={
              showGenerate ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    generate();
                  }}
                  disabled={genBusy}
                  className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
                >
                  {genBusy ? "Generating…" : "Generate keys"}
                </button>
              ) : null
            }
          >
            <Grid fields={security} cfg={cfg} setField={setField} />
          </Section>
        ) : null}
        {camouflage.length > 0 ? (
          <Section title="Camouflage settings">
            <Grid fields={camouflage} cfg={cfg} setField={setField} />
          </Section>
        ) : null}
        {mux.length > 0 ? (
          <Section title="Multiplexing">
            <Grid fields={mux} cfg={cfg} setField={setField} />
          </Section>
        ) : null}
        <Section title="Advanced (JSON)">
          <textarea
            value={advanced}
            onChange={(e) => setAdvanced(e.target.value)}
            placeholder='{ "extraKey": "value" }'
            className="h-24 w-full resize-y rounded border border-hairline bg-transparent p-2.5 font-mono text-[11px] text-fg outline-none focus:border-primary"
          />
        </Section>
        <Section title="Settings preview">
          <pre className="max-h-48 overflow-auto rounded border border-hairline bg-muted p-2.5 font-mono text-[11px] leading-relaxed text-fg-muted">
            {previewJson}
          </pre>
        </Section>
        </div>
        </div>

        <div className="warp-dlg-footer">
          <button type="button" className="warp-tb-button" onClick={onClose}>Cancel</button>
          <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy || !name.trim() || (!profile && !nodeId)}>
            {busy ? "Saving…" : profile ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Section({
  title,
  action,
  defaultOpen,
  children,
}: {
  title: string;
  action?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
        className="flex w-full cursor-pointer select-none items-center justify-between gap-2 py-3 text-sm font-medium text-fg"
      >
        <span>{title}</span>
        <span className="flex items-center gap-3">
          {action}
          <ChevronDown
            className={cn("h-4 w-4 text-fg-muted transition-transform", open && "rotate-180")}
          />
        </span>
      </div>
      {open ? <div className="pb-4">{children}</div> : null}
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
    <div className="grid grid-cols-2 gap-3">
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
