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
  refreshAsnDataset,
  updateInboundHost,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { Field } from "@/shared/parts";
import { InlineEditPanel } from "@/shared/settings-kit";
import { useT } from "@/lib/i18n";

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
  variant = "modal",
}: {
  profileId: string;
  host: InboundHostRead | null;
  onClose: () => void;
  onSaved: () => void;
  variant?: "modal" | "inline";
}) {
  const t = useT();
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
  const [asnText, setAsnText] = useState(() =>
    Object.entries(host?.asn_addresses ?? {})
      .map(([asn, ips]) => `${asn}: ${ips.join(", ")}`)
      .join("\n"),
  );
  const [asnBusy, setAsnBusy] = useState(false);
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
        asn_addresses: parseAsnMap(asnText),
        mux,
        is_universal: isUniversal,
        is_disabled: !enabled,
      };
      if (editing && host) await updateInboundHost(host.id, body);
      else await createInboundHost({ profile_id: profileId, ...body });
      toast("success", editing ? t("profiles.hostUpdated") : t("profiles.hostCreated"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const Shell = variant === "inline" ? InlineEditPanel : Modal;
  return (
    <Shell
      title={editing ? t("profiles.editAddress") : t("profiles.addAddress")}
      onClose={onClose}
      onSubmit={submit}
      width="sm:w-[40rem]"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button type="submit" variant="primary" disabled={busy || !remark.trim()}>
            {busy ? t("common.saving") : editing ? t("action.save") : t("action.create")}
          </Button>
        </>
      }
    >
      {}
      <label className="flex flex-col gap-1.5 text-sm font-medium text-fg">
        <span className="flex items-center justify-between gap-3">
          {t("common.name")}
          <span className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs font-normal text-fg-muted">
              <input
                type="checkbox"
                checked={isUniversal}
                onChange={(e) => setIsUniversal(e.target.checked)}
              />
              {t("profiles.universalLabel")}
            </label>
            <Switch checked={enabled} onChange={setEnabled} />
          </span>
        </span>
        <Input value={remark} onChange={(e) => setRemark(e.target.value)} autoFocus placeholder="CDN-FRA" />
      </label>

      {}
      <div className="grid grid-cols-4 gap-3">
        <div className="col-span-2">
          <Field label={t("profiles.address")}>
            <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="cdn.example.com" />
          </Field>
        </div>
        <Field label={t("profiles.port")}>
          <Input value={port} onChange={(e) => setPort(e.target.value)} type="number" placeholder="443" />
        </Field>
        <Field label={t("profiles.weight")}>
          <Input value={weight} onChange={(e) => setWeight(e.target.value)} type="number" />
        </Field>
      </div>

      {}
      <div>
        <Section title={t("profiles.networkSettings")} defaultOpen>
          <div className="warp-dlg-2col">
            <Field label={t("profiles.host")}>
              <Input value={hostHeader} onChange={(e) => setHostHeader(e.target.value)} placeholder={t("profiles.cdnDomainPlaceholder")} />
            </Field>
            <Field label={t("profiles.path")}>
              <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/" />
            </Field>
            <Field label={t("profiles.network")}>
              <Select value={network} onChange={(e) => setNetwork(e.target.value)}>
                {NETWORKS.map((n) => (
                  <option key={n} value={n}>
                    {n === "" ? t("profiles.inherit") : n}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </Section>

        <Section title={t("profiles.camouflageSettings")}>
          <div className="flex flex-col gap-3.5">
            <Field label={t("profiles.fragmentLabel")}>
              <Input value={fragment} onChange={(e) => setFragment(e.target.value)} placeholder="100-200,10-20,tlshello" />
            </Field>
            <Field label={t("profiles.noiseLabel")}>
              <Input value={noise} onChange={(e) => setNoise(e.target.value)} placeholder="rand:10-20,10-20" />
            </Field>
          </div>
        </Section>

        <Section title={t("profiles.asnTitle")}>
          <Field label={t("profiles.asnLabel")} hint={t("profiles.asnHint")}>
            <textarea
              value={asnText}
              onChange={(e) => setAsnText(e.target.value)}
              placeholder={"58224: 104.16.10.1, 104.17.20.2\n197207: 172.67.1.1"}
              className="h-24 w-full resize-y rounded border border-hairline bg-transparent p-2.5 font-mono text-[11px] text-fg outline-none focus:border-primary"
            />
          </Field>
          <button
            type="button"
            className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
            disabled={asnBusy}
            onClick={async () => {
              setAsnBusy(true);
              try {
                const s = await refreshAsnDataset();
                toast("success", t("profiles.asnRefreshed", { n: s.v4?.ranges ?? 0 }));
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
              } finally {
                setAsnBusy(false);
              }
            }}
          >
            {asnBusy ? t("common.loading") : t("profiles.asnRefresh")}
          </button>
        </Section>

        <Section title={t("profiles.muxSettings")}>
          <Toggle checked={mux} onChange={setMux} label={t("profiles.enableMux")} />
        </Section>

        <Section title={t("profiles.securitySettings")}>
          <Field label={t("profiles.security")}>
            <Select value={security} onChange={(e) => setSecurity(e.target.value)}>
              {SECURITIES.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? t("profiles.inherit") : s === "inbound_default" ? t("profiles.inboundDefault") : s.toUpperCase()}
                </option>
              ))}
            </Select>
          </Field>
          {extraSecurity ? (
            <div className="mt-3 flex flex-col gap-3.5">
              <Field label={t("profiles.sni")}>
                <Input value={sni} onChange={(e) => setSni(e.target.value)} />
              </Field>
              <div className="warp-dlg-2col">
                <Field label={t("profiles.alpn")}>
                  <Select value={alpn} onChange={(e) => setAlpn(e.target.value)}>
                    {ALPN_OPTIONS.map((a) => (
                      <option key={a} value={a}>
                        {a === "" ? "—" : a}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label={t("profiles.fingerprint")}>
                  <Select value={fingerprint} onChange={(e) => setFingerprint(e.target.value)}>
                    {FINGERPRINTS.map((f) => (
                      <option key={f} value={f}>
                        {f === "" ? "—" : f}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Toggle checked={allowInsecure} onChange={setAllowInsecure} label={t("profiles.allowInsecure")} />
            </div>
          ) : null}
        </Section>
      </div>
    </Shell>
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
        <ChevronDown className={cn("h-4 w-4 text-fg-muted transition-transform", open && "rotate-180")} aria-hidden />
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

/** "58224: 1.1.1.1, 2.2.2.2" per line → {"58224": ["1.1.1.1", "2.2.2.2"]}.
 * The panel validates and normalises; this only splits. */
function parseAsnMap(text: string): Record<string, string[]> | null {
  const out: Record<string, string[]> = {};
  for (const line of text.split("\n")) {
    const [asn, rest] = line.split(":", 2);
    if (!asn?.trim() || rest === undefined) continue;
    const ips = rest.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
    if (ips.length) out[asn.trim()] = ips;
  }
  return Object.keys(out).length ? out : null;
}
