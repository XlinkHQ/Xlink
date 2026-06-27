"use client";

import { ChevronDown } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createInboundHost,
  type InboundHostRead,
  updateInboundHost,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Field } from "../parts";

const NETWORKS = ["", "tcp", "ws", "grpc", "httpupgrade", "xhttp", "splithttp", "kcp"];
const SECURITIES = ["", "none", "tls", "reality", "inbound_default"];
const ALPN_OPTIONS = ["", "none", "h2", "h3", "h3,h2", "http/1.1", "h2,http/1.1", "h3,h2,http/1.1"];
const FINGERPRINTS = [
  "",
  "none",
  "chrome",
  "firefox",
  "safari",
  "ios",
  "android",
  "edge",
  "360",
  "qq",
  "random",
  "randomized",
];

export function HostDialog({
  profileId,
  host,
  onClose,
  onSaved,
}: {
  profileId: string;
  host: InboundHostRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const editing = !!host;
  const [remark, setRemark] = useState(host?.remark ?? "");
  const [enabled, setEnabled] = useState(host ? !host.is_disabled : true);
  const [isUniversal, setIsUniversal] = useState(host?.is_universal ?? false);
  const [address, setAddress] = useState(host?.address ?? "");
  const [port, setPort] = useState(host?.port != null ? String(host.port) : "");
  const [weight, setWeight] = useState(String(host?.weight ?? 1));
  const [hostHeader, setHostHeader] = useState(host?.host ?? "");
  const [path, setPath] = useState(host?.path ?? "");
  const [network, setNetwork] = useState(host?.network ?? "");
  const [fragment, setFragment] = useState(host?.fragment ?? "");
  const [noise, setNoise] = useState(host?.noise ?? "");
  const [mux, setMux] = useState(host?.mux ?? false);
  const [security, setSecurity] = useState(host?.security ?? "");
  const [sni, setSni] = useState(host?.sni ?? "");
  const [alpn, setAlpn] = useState(host?.alpn ?? "");
  const [fingerprint, setFingerprint] = useState(host?.fingerprint ?? "");
  const [allowInsecure, setAllowInsecure] = useState(host?.allow_insecure ?? false);
  const [busy, setBusy] = useState(false);

  const extraSecurity = ["tls", "reality", "inbound_default"].includes(security);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        remark: remark.trim(),
        address: address.trim() || null,
        port: port ? Number(port) : null,
        weight: weight ? Number(weight) : 1,
        host: hostHeader.trim() || null,
        path: path.trim() || null,
        network: network || null,
        security: security || null,
        sni: extraSecurity ? sni.trim() || null : null,
        alpn: extraSecurity ? alpn || null : null,
        fingerprint: extraSecurity ? fingerprint || null : null,
        allow_insecure: extraSecurity ? allowInsecure : false,
        fragment: fragment.trim() || null,
        noise: noise.trim() || null,
        mux,
        is_universal: isUniversal,
        is_disabled: !enabled,
      };
      if (editing && host) await updateInboundHost(host.id, body);
      else await createInboundHost({ profile_id: profileId, ...body });
      toast("success", editing ? "Host updated." : "Host created.");
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="warp-dlg-overlay" onMouseDown={onClose}>
      <form className="warp-dlg" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="warp-dlg-header">
          <span className="warp-dlg-grab" />
          <p>{editing ? "Edit address" : "Add address"}</p>
        </div>

        <div className="warp-dlg-body warp-dlg-body-flow">
      {/* Name (with enable switch + universal, like marzneshin's remark row) */}
      <label className="flex flex-col gap-1.5 text-sm font-medium text-fg">
        <span className="flex items-center justify-between gap-3">
          Name
          <span className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs font-normal text-fg-muted">
              <input
                type="checkbox"
                checked={isUniversal}
                onChange={(e) => setIsUniversal(e.target.checked)}
              />
              Universal
            </label>
            <Switch checked={enabled} onChange={setEnabled} />
          </span>
        </span>
        <Input value={remark} onChange={(e) => setRemark(e.target.value)} autoFocus placeholder="CDN-FRA" />
      </label>

      {/* Address / Port / Weight */}
      <div className="grid grid-cols-4 gap-3">
        <div className="col-span-2">
          <Field label="Address">
            <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="cdn.example.com" />
          </Field>
        </div>
        <Field label="Port">
          <Input value={port} onChange={(e) => setPort(e.target.value)} type="number" placeholder="443" />
        </Field>
        <Field label="Weight">
          <Input value={weight} onChange={(e) => setWeight(e.target.value)} type="number" />
        </Field>
      </div>

      {/* Accordion sections — marzneshin order: network, camouflage, mux, security */}
      <div>
        <Section title="Network settings" defaultOpen>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Host">
              <Input value={hostHeader} onChange={(e) => setHostHeader(e.target.value)} placeholder="cdn domain" />
            </Field>
            <Field label="Path">
              <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/" />
            </Field>
            <Field label="Network">
              <Select value={network} onChange={(e) => setNetwork(e.target.value)}>
                {NETWORKS.map((n) => (
                  <option key={n} value={n}>
                    {n === "" ? "— inherit —" : n}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </Section>

        <Section title="Camouflage settings">
          <div className="flex flex-col gap-3">
            <Field label="Fragment (len,interval,packets)">
              <Input value={fragment} onChange={(e) => setFragment(e.target.value)} placeholder="100-200,10-20,tlshello" />
            </Field>
            <Field label="Noise (packets,delay)">
              <Input value={noise} onChange={(e) => setNoise(e.target.value)} placeholder="rand:10-20,10-20" />
            </Field>
          </div>
        </Section>

        <Section title="Mux settings">
          <Toggle checked={mux} onChange={setMux} label="Enable mux" />
        </Section>

        <Section title="Security settings">
          <Field label="Security">
            <Select value={security} onChange={(e) => setSecurity(e.target.value)}>
              {SECURITIES.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? "— inherit —" : s === "inbound_default" ? "Inbound Default" : s.toUpperCase()}
                </option>
              ))}
            </Select>
          </Field>
          {extraSecurity ? (
            <div className="mt-3 flex flex-col gap-3">
              <Field label="SNI">
                <Input value={sni} onChange={(e) => setSni(e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="ALPN">
                  <Select value={alpn} onChange={(e) => setAlpn(e.target.value)}>
                    {ALPN_OPTIONS.map((a) => (
                      <option key={a} value={a}>
                        {a === "" ? "—" : a}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Fingerprint">
                  <Select value={fingerprint} onChange={(e) => setFingerprint(e.target.value)}>
                    {FINGERPRINTS.map((f) => (
                      <option key={f} value={f}>
                        {f === "" ? "—" : f}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Toggle checked={allowInsecure} onChange={setAllowInsecure} label="Allow insecure" />
            </div>
          ) : null}
        </Section>
      </div>
        </div>

        <div className="warp-dlg-footer">
          <button type="button" className="warp-tb-button" onClick={onClose}>Cancel</button>
          <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy || !remark.trim()}>
            {busy ? "Saving…" : editing ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Section({
  title,
  defaultOpen,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 py-3 text-sm font-medium text-fg"
      >
        <span>{title}</span>
        <ChevronDown className={cn("h-4 w-4 text-fg-muted transition-transform", open && "rotate-180")} />
      </button>
      {open ? <div className="pb-4">{children}</div> : null}
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors",
        checked ? "bg-primary" : "bg-hairline",
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-4" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-fg">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
