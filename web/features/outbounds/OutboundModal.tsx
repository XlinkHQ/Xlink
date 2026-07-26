"use client";

import { Info } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createOutbound,
  createRoutingRule,
  importOutbound,
  type OutboundRead,
  pingOutbound,
  updateOutbound,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { HAS_ADDRESS, HAS_STREAM, TYPES } from "./constants";

export function OutboundModal({
  outbound,
  onClose,
  onSaved,
}: {
  outbound: OutboundRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const editing = outbound !== null;
  const st = (outbound?.settings ?? {}) as Record<string, unknown>;
  const sv = (k: string, d = "") => String(st[k] ?? d);

  const [tag, setTag] = useState(outbound?.tag ?? "");
  const [type, setType] = useState(outbound?.type ?? "vless");
  const [enabled, setEnabled] = useState(outbound?.enabled ?? true);
  const [busy, setBusy] = useState(false);

  const [address, setAddress] = useState(sv("address"));
  const [id, setId] = useState(sv("id"));
  const [password, setPassword] = useState(sv("password"));
  const [username, setUsername] = useState(sv("username"));
  const [method, setMethod] = useState(sv("method", "2022-blake3-aes-128-gcm"));
  const [flow, setFlow] = useState(sv("flow"));
  const [encryption, setEncryption] = useState(sv("encryption", "none"));

  const [network, setNetwork] = useState(sv("network", "tcp"));
  const [security, setSecurity] = useState(sv("security", "none"));
  const [sni, setSni] = useState(sv("sni"));
  const [path, setPath] = useState(sv("path"));
  const [host, setHost] = useState(sv("host"));
  const [fingerprint, setFingerprint] = useState(sv("fingerprint", "chrome"));
  const [publicKey, setPublicKey] = useState(sv("publicKey"));
  const [shortId, setShortId] = useState(sv("shortId"));
  const [serviceName, setServiceName] = useState(sv("serviceName"));

  const [secretKey, setSecretKey] = useState(sv("secretKey"));
  const [wgAddress, setWgAddress] = useState(sv("address", "172.16.0.2/32"));
  const [endpoint, setEndpoint] = useState(sv("endpoint"));
  const [reserved, setReserved] = useState(sv("reserved"));

  const [raw, setRaw] = useState(
    outbound?.type === "custom" ? JSON.stringify(st.raw ?? {}, null, 2) : "",
  );
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [pingMsg, setPingMsg] = useState("");
  const [makeRule, setMakeRule] = useState(false);
  const [ruleMatch, setRuleMatch] = useState("all");
  const [ruleValues, setRuleValues] = useState("");

  const doPing = async () => {
    if (!address.trim()) return;
    setPinging(true);
    setPingMsg("");
    try {
      const r = await pingOutbound(address.trim());
      setPingMsg((r.ok ? "✓ " : "✗ ") + r.detail);
    } catch {
      setPingMsg("✗ " + t("outbounds.modal.pingFailed"));
    } finally {
      setPinging(false);
    }
  };

  const doImport = async () => {
    if (!importText.trim()) return;
    setImporting(true);
    try {
      const r = await importOutbound(importText.trim());
      const s = r.settings as Record<string, string>;
      setType(r.type);
      setAddress(s.address ?? "");
      setId(s.id ?? "");
      setPassword(s.password ?? "");
      setUsername(s.username ?? "");
      setMethod(s.method ?? "aes-256-gcm");
      setFlow(s.flow ?? "");
      setEncryption(s.encryption ?? "none");
      setNetwork(s.network ?? "tcp");
      setSecurity(s.security ?? "none");
      setSni(s.sni ?? "");
      setPath(s.path ?? "");
      setHost(s.host ?? "");
      setFingerprint(s.fingerprint ?? "");
      setPublicKey(s.publicKey ?? "");
      setShortId(s.shortId ?? "");
      setServiceName(s.serviceName ?? "");
      setSecretKey(s.secretKey ?? "");
      setWgAddress(s.address ?? "172.16.0.2/32");
      setEndpoint(s.endpoint ?? "");
      setReserved(s.reserved ?? "");
      setImportText("");
      toast("success", t("outbounds.modal.detected", { type: r.type }));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("outbounds.modal.importFailed"));
    } finally {
      setImporting(false);
    }
  };

  const buildSettings = (): Record<string, unknown> | null => {
    if (type === "custom") {
      try {
        return { raw: JSON.parse(raw || "{}") };
      } catch {
        toast("error", t("outbounds.modal.invalidJson"));
        return null;
      }
    }
    const s: Record<string, unknown> = {};
    if (HAS_ADDRESS.has(type)) s.address = address;
    if (type === "vless" || type === "vmess") {
      s.id = id;
      if (type === "vless") { s.encryption = encryption; if (flow) s.flow = flow; }
    }
    if (type === "trojan" || type === "shadowsocks") s.password = password;
    if (type === "shadowsocks") s.method = method;
    if ((type === "socks" || type === "http") && username) { s.username = username; s.password = password; }
    if (HAS_STREAM.has(type) && network !== "tcp") s.network = network;
    else if (HAS_STREAM.has(type)) s.network = "tcp";
    if (HAS_STREAM.has(type) && security !== "none") {
      s.security = security;
      if (sni) s.sni = sni;
      if (fingerprint) s.fingerprint = fingerprint;
      if (security === "reality") { if (publicKey) s.publicKey = publicKey; if (shortId) s.shortId = shortId; }
    }
    if (HAS_STREAM.has(type)) {
      if (network === "ws" || network === "httpupgrade") { if (path) s.path = path; if (host) s.host = host; }
      if (network === "grpc" && serviceName) s.serviceName = serviceName;
    }
    if (type === "wireguard") {
      s.secretKey = secretKey; s.address = wgAddress; s.endpoint = endpoint;
      if (publicKey) s.publicKey = publicKey;
      if (reserved) s.reserved = reserved;
    }
    if (type === "freedom" && sni) s.domainStrategy = sni;
    return s;
  };

  const submit = async () => {
    const settings = buildSettings();
    if (settings === null) return;
    if (!editing && makeRule && ruleMatch !== "all" && !ruleValues.trim()) {
      toast("error", t("outbounds.modal.enterMatchValues"));
      return;
    }
    setBusy(true);
    try {
      const body = { tag: tag.trim(), type, settings, enabled };
      if (editing && outbound) {
        await updateOutbound(outbound.id, body);
        toast("success", t("outbounds.toast.updated"));
      } else {
        await createOutbound(body);
        if (makeRule) {
          const isAll = ruleMatch === "all";
          try {
            await createRoutingRule({
              name: t("outbounds.modal.ruleName", { tag: tag.trim() }),
              match_type: isAll ? "domain" : ruleMatch,
              match_values: isAll ? "geosite:geolocation-!cn" : ruleValues.trim(),
              outbound: tag.trim(),
              enabled: true,
              priority: 0,
            });
            toast("success", t("outbounds.toast.addedWithRule"));
          } catch (e) {
            toast(
              "error",
              t("outbounds.toast.ruleFailed", { error: e instanceof ApiError ? e.message : t("common.unknownError") }),
            );
          }
        } else {
          toast("success", t("outbounds.toast.added"));
        }
      }
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("outbounds.toast.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const field = (label: string, node: React.ReactNode) => (
    <label className="warp-field-row" style={{ marginTop: 12 }}>
      <span className="warp-field-label">{label}</span>
      {node}
    </label>
  );

  return (
    <Modal
      title={editing ? t("outbounds.modal.editTitle") : t("outbounds.modal.addTitle")}
      width="w-[min(620px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>{t("action.cancel")}</Button>
          <Button type="button" variant="primary" disabled={busy || !tag.trim()} onClick={submit}>
            {busy ? t("common.saving") : editing ? t("action.saveChanges") : t("outbounds.addOutbound")}
          </Button>
        </>
      }
    >
      <div className="warp-rt-form-info">
        <Info size={16} />
        <span>{t("outbounds.modal.info")}</span>
      </div>

      <label className="warp-field-row" style={{ marginTop: 4 }}>
        <span className="warp-field-label">{t("outbounds.modal.importLabel")}</span>
        <div style={{ display: "flex", gap: 8 }}>
          <Input
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="vless:// · vmess:// · trojan:// · ss:// · or paste Xray JSON"
          />
          <Button type="button" variant="outline" onClick={doImport} disabled={importing || !importText.trim()}>
            {importing ? "…" : t("outbounds.modal.detect")}
          </Button>
        </div>
        <span className="warp-field-helper">{t("outbounds.modal.importHelper")}</span>
      </label>

      <div className="warp-dlg-2col">
        <label className="warp-field-row">
          <span className="warp-field-label">{t("outbounds.col.tag")}</span>
          <Input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="my-outbound" autoFocus />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">{t("outbounds.field.protocol")}</span>
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
          </Select>
        </label>
      </div>

      {HAS_ADDRESS.has(type) ? (
        <label className="warp-field-row" style={{ marginTop: 12 }}>
          <span className="warp-field-label">{t("outbounds.field.address")}</span>
          <div style={{ display: "flex", gap: 8 }}>
            <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="1.2.3.4:443" />
            <Button type="button" variant="outline" onClick={doPing} disabled={pinging || !address.trim()}>
              {pinging ? "…" : t("outbounds.field.ping")}
            </Button>
          </div>
          {pingMsg ? <span className="warp-field-helper">{pingMsg}</span> : null}
        </label>
      ) : null}
      {(type === "vless" || type === "vmess") ? field(t("outbounds.field.uuid"), <Input value={id} onChange={(e) => setId(e.target.value)} placeholder={t("outbounds.field.uuidPlaceholder")} />) : null}
      {type === "vless" ? (
        <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
          <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.flow")}</span>
            <Select value={flow} onChange={(e) => setFlow(e.target.value)}>
              <option value="">{t("common.none")}</option><option value="xtls-rprx-vision">xtls-rprx-vision</option>
            </Select></label>
          <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.encryption")}</span>
            <Input value={encryption} onChange={(e) => setEncryption(e.target.value)} placeholder="none" /></label>
        </div>
      ) : null}
      {type === "trojan" ? field(t("outbounds.field.password"), <Input value={password} onChange={(e) => setPassword(e.target.value)} />) : null}
      {type === "shadowsocks" ? (
        <>
          {field(t("outbounds.field.method"), <Select value={method} onChange={(e) => setMethod(e.target.value)}>
            {["2022-blake3-aes-128-gcm","2022-blake3-aes-256-gcm","2022-blake3-chacha20-poly1305","aes-256-gcm","chacha20-ietf-poly1305"].map((m)=><option key={m} value={m}>{m}</option>)}
          </Select>)}
          {field(t("outbounds.field.password"), <Input value={password} onChange={(e) => setPassword(e.target.value)} />)}
        </>
      ) : null}
      {(type === "socks" || type === "http") ? (
        <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
          <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.usernameOptional")}</span><Input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.passwordOptional")}</span><Input value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        </div>
      ) : null}

      {type === "wireguard" ? (
        <>
          {field(t("outbounds.field.secretKey"), <Input value={secretKey} onChange={(e) => setSecretKey(e.target.value)} />)}
          {field(t("outbounds.field.interfaceAddress"), <Input value={wgAddress} onChange={(e) => setWgAddress(e.target.value)} placeholder="172.16.0.2/32" />)}
          {field(t("outbounds.field.peerPublicKey"), <Input value={publicKey} onChange={(e) => setPublicKey(e.target.value)} />)}
          {field(t("outbounds.field.endpoint"), <Input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="engage.cloudflareclient.com:2408" />)}
          {field(t("outbounds.field.reserved"), <Input value={reserved} onChange={(e) => setReserved(e.target.value)} placeholder="1,2,3" />)}
        </>
      ) : null}

      {HAS_STREAM.has(type) ? (
        <>
          <div className="warp-dlg-divider" />
          <div className="warp-dlg-2col">
            <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.transport")}</span>
              <Select value={network} onChange={(e) => setNetwork(e.target.value)}>
                {["tcp","ws","grpc","httpupgrade","xhttp"].map((n)=><option key={n} value={n}>{n}</option>)}
              </Select></label>
            <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.security")}</span>
              <Select value={security} onChange={(e) => setSecurity(e.target.value)}>
                {["none","tls","reality"].map((s)=><option key={s} value={s}>{s}</option>)}
              </Select></label>
          </div>
          {(network === "ws" || network === "httpupgrade") ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.path")}</span><Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/" /></label>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.host")}</span><Input value={host} onChange={(e) => setHost(e.target.value)} /></label>
            </div>
          ) : null}
          {network === "grpc" ? field(t("outbounds.field.grpcServiceName"), <Input value={serviceName} onChange={(e) => setServiceName(e.target.value)} />) : null}
          {security === "tls" || security === "reality" ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.sni")}</span><Input value={sni} onChange={(e) => setSni(e.target.value)} /></label>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.fingerprint")}</span>
                <Select value={fingerprint} onChange={(e) => setFingerprint(e.target.value)}>
                  {["chrome","firefox","safari","ios","edge","random","randomized"].map((f)=><option key={f} value={f}>{f}</option>)}
                </Select></label>
            </div>
          ) : null}
          {security === "reality" ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.realityPublicKey")}</span><Input value={publicKey} onChange={(e) => setPublicKey(e.target.value)} /></label>
              <label className="warp-field-row"><span className="warp-field-label">{t("outbounds.field.shortId")}</span><Input value={shortId} onChange={(e) => setShortId(e.target.value)} /></label>
            </div>
          ) : null}
        </>
      ) : null}

      {type === "freedom" ? field(t("outbounds.field.domainStrategy"), <Select value={sni} onChange={(e) => setSni(e.target.value)}>{["","UseIP","UseIPv4","UseIPv6","ForceIP"].map((v)=><option key={v} value={v}>{v||"AsIs"}</option>)}</Select>) : null}

      {type === "custom" ? field(t("outbounds.field.rawOutbound"),
        <textarea className="warp-cert-textarea" rows={9} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder={'{ "protocol": "vless", "settings": { ... }, "streamSettings": { ... } }'} />
      ) : null}

      {!editing ? (
        <>
          <div className="warp-dlg-divider" />
          <label className="warp-switch warp-switch-inline" style={{ marginBottom: makeRule ? 12 : 0 }}>
            <input type="checkbox" checked={makeRule} onChange={() => setMakeRule((v) => !v)} />
            <span className="warp-switch-track" />
            <span className="warp-switch-label">{t("outbounds.modal.alsoCreateRule")}</span>
          </label>
          {makeRule ? (
            <div className="warp-dlg-2col">
              <label className="warp-field-row">
                <span className="warp-field-label">{t("outbounds.modal.route")}</span>
                <Select value={ruleMatch} onChange={(e) => setRuleMatch(e.target.value)}>
                  <option value="all">{t("outbounds.modal.routeAll")}</option>
                  <option value="domain">{t("outbounds.modal.routeDomains")}</option>
                  <option value="ip">{t("outbounds.modal.routeIps")}</option>
                  <option value="port">{t("outbounds.modal.routePorts")}</option>
                </Select>
              </label>
              {ruleMatch !== "all" ? (
                <label className="warp-field-row">
                  <span className="warp-field-label">{t("outbounds.modal.valuesLabel")}</span>
                  <Input value={ruleValues} onChange={(e) => setRuleValues(e.target.value)} placeholder="geosite:google, 1.2.3.0/24" />
                </label>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </Modal>
  );
}
