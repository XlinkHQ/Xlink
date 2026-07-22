"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Plus } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  createOutbound,
  createRoutingRule,
  deleteOutbound,
  importOutbound,
  listOutbounds,
  type OutboundRead,
  pingOutbound,
  pingOutboundById,
  updateOutbound,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { WarpButton, WarpEmpty, WarpHead, WarpMenu, WarpSkeleton, WarpTableCard } from "@/shared/warp-table";

const TYPES = [
  { v: "vless", label: "VLESS" },
  { v: "vmess", label: "VMess" },
  { v: "trojan", label: "Trojan" },
  { v: "shadowsocks", label: "Shadowsocks" },
  { v: "wireguard", label: "WireGuard" },
  { v: "socks", label: "SOCKS" },
  { v: "http", label: "HTTP" },
  { v: "freedom", label: "Freedom (direct)" },
  { v: "block", label: "Blackhole (block)" },
  { v: "dns", label: "DNS" },
  { v: "custom", label: "Custom (raw JSON)" },
];

const HAS_ADDRESS = new Set(["vless", "vmess", "trojan", "shadowsocks", "socks", "http"]);
const HAS_STREAM = new Set(["vless", "vmess", "trojan", "socks", "http"]);

export function OutboundsScreen() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["outbounds"], queryFn: () => listOutbounds() });
  const outbounds = q.data ?? [];
  const [dialog, setDialog] = useState<OutboundRead | "new" | null>(null);
  const [pinging, setPinging] = useState<string | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["outbounds"] });
    qc.invalidateQueries({ queryKey: ["routing-rules"] });
  };

  const testable = (o: OutboundRead) => !["block", "dns"].includes(o.type);

  const ping = async (o: OutboundRead) => {
    if (pinging) return;
    setPinging(o.id);
    try {
      const r = await pingOutboundById(o.id);
      if (r.ok) {
        toast("success", `${o.tag} reachable · ${r.latency_ms ?? 0} ms`);
      } else {
        toast("error", `${o.tag} unreachable · ${r.detail}`);
      }
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Test failed.");
    } finally {
      setPinging(null);
    }
  };

  const remove = async (o: OutboundRead) => {
    if (!(await confirmDialog({ title: `Delete outbound "${o.tag}"?`, confirmLabel: "Delete", danger: true }))) return;
    try {
      await deleteOutbound(o.id);
      toast("success", "Outbound deleted.");
      refresh();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  const target = (o: OutboundRead) => {
    if (HAS_ADDRESS.has(o.type)) return String(o.settings.address ?? "");
    if (o.type === "wireguard") return String(o.settings.endpoint ?? "");
    if (o.type === "custom") return "raw JSON";
    return "—";
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">All outbounds</span>
        <div className="right">
          <WarpButton primary onClick={() => setDialog("new")}>
            <Plus size={16} strokeWidth={1.8} aria-hidden /> Add Outbound
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Tag", "Type", "Target", "Status"]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : outbounds.length === 0 ? (
          <WarpEmpty icon="fa-route">
            No custom outbounds yet. Rules can also use the builtins (block / direct / warp).
          </WarpEmpty>
        ) : (
          <>
            {outbounds.map((o) => (
              <div key={o.id} className={`warp-tb-row ${o.enabled ? "" : "warp-rt-off"}`}>
                <span className="warp-tb-cell warp-tb-cell-name font-medium">{o.tag}</span>
                <span className="warp-tb-cell"><Badge tone="neutral">{o.type}</Badge></span>
                <span className="warp-tb-cell warp-rt-matchcell">
                  <span className={o.type === "custom" ? "warp-rt-chip is-more" : "warp-rt-chip"}>{target(o)}</span>
                </span>
                <span className="warp-tb-cell">
                  <span className={`warp-rt-status ${o.enabled ? "is-on" : "is-off"}`}>
                    <span className="warp-rt-dot" />{o.enabled ? "Enabled" : "Disabled"}
                  </span>
                </span>
                <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
                  <WarpMenu
                    items={[
                      ...(testable(o) ? [{ label: pinging === o.id ? "Testing…" : "Test connection", icon: "ping", disabled: pinging === o.id, onClick: () => ping(o) }] : []),
                      { label: "Edit", icon: "edit", onClick: () => setDialog(o) },
                      { label: "Delete", icon: "delete", danger: true, onClick: () => remove(o) },
                    ]}
                  />
                </span>
              </div>
            ))}
          </>
        )}
      </WarpTableCard>

      {dialog ? (
        <OutboundModal
          outbound={dialog === "new" ? null : dialog}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function OutboundModal({
  outbound,
  onClose,
  onSaved,
}: {
  outbound: OutboundRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
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
      setPingMsg("✗ ping failed");
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
      // Reset every field first so a second import that omits a field doesn't
      // silently keep the previous value.
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
      toast("success", `Detected ${r.type} — fields filled.`);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  };

  const buildSettings = (): Record<string, unknown> | null => {
    if (type === "custom") {
      try {
        return { raw: JSON.parse(raw || "{}") };
      } catch {
        toast("error", "Invalid JSON.");
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
    // Validate the rule inputs BEFORE creating the outbound, so we don't persist
    // an outbound then fail the rule and leave an orphan.
    if (!editing && makeRule && ruleMatch !== "all" && !ruleValues.trim()) {
      toast("error", "Enter match values for the routing rule (or pick All traffic).");
      return;
    }
    setBusy(true);
    try {
      const body = { tag: tag.trim(), type, settings, enabled };
      if (editing && outbound) {
        await updateOutbound(outbound.id, body);
        toast("success", "Outbound updated.");
      } else {
        await createOutbound(body);
        if (makeRule) {
          const isAll = ruleMatch === "all";
          try {
            await createRoutingRule({
              name: `${tag.trim()} route`,
              match_type: isAll ? "domain" : ruleMatch,
              match_values: isAll ? "geosite:geolocation-!cn" : ruleValues.trim(),
              outbound: tag.trim(),
              enabled: true,
              priority: 0,
            });
            toast("success", "Outbound + routing rule added.");
          } catch (e) {
            // Outbound was created; surface the rule failure without losing it or
            // implying the whole save failed (retry would duplicate the outbound).
            toast(
              "error",
              `Outbound added, but the routing rule failed: ${e instanceof ApiError ? e.message : "unknown error"}`,
            );
          }
        } else {
          toast("success", "Outbound added.");
        }
      }
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Save failed.");
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
      title={editing ? "Edit outbound" : "Add outbound"}
      width="w-[min(620px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="primary" disabled={busy || !tag.trim()} onClick={submit}>
            {busy ? "Saving…" : editing ? "Save changes" : "Add outbound"}
          </Button>
        </>
      }
    >
      <div className="warp-rt-form-info">
        <Info size={16} />
        <span>Where matched traffic exits. Pick a protocol and fill its fields, or use Custom for a raw Xray outbound. Reference it by tag from a routing rule.</span>
      </div>

      <label className="warp-field-row" style={{ marginTop: 4 }}>
        <span className="warp-field-label">Import from link or config</span>
        <div style={{ display: "flex", gap: 8 }}>
          <Input
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="vless:// · vmess:// · trojan:// · ss:// · or paste Xray JSON"
          />
          <Button type="button" variant="outline" onClick={doImport} disabled={importing || !importText.trim()}>
            {importing ? "…" : "Detect"}
          </Button>
        </div>
        <span className="warp-field-helper">Auto-detects the protocol and fills the fields below.</span>
      </label>

      <div className="warp-dlg-2col">
        <label className="warp-field-row">
          <span className="warp-field-label">Tag</span>
          <Input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="my-outbound" autoFocus />
        </label>
        <label className="warp-field-row">
          <span className="warp-field-label">Protocol</span>
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
          </Select>
        </label>
      </div>

      {HAS_ADDRESS.has(type) ? (
        <label className="warp-field-row" style={{ marginTop: 12 }}>
          <span className="warp-field-label">Address (host:port)</span>
          <div style={{ display: "flex", gap: 8 }}>
            <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="1.2.3.4:443" />
            <Button type="button" variant="outline" onClick={doPing} disabled={pinging || !address.trim()}>
              {pinging ? "…" : "Ping"}
            </Button>
          </div>
          {pingMsg ? <span className="warp-field-helper">{pingMsg}</span> : null}
        </label>
      ) : null}
      {(type === "vless" || type === "vmess") ? field("UUID", <Input value={id} onChange={(e) => setId(e.target.value)} placeholder="client uuid" />) : null}
      {type === "vless" ? (
        <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
          <label className="warp-field-row"><span className="warp-field-label">Flow</span>
            <Select value={flow} onChange={(e) => setFlow(e.target.value)}>
              <option value="">none</option><option value="xtls-rprx-vision">xtls-rprx-vision</option>
            </Select></label>
          <label className="warp-field-row"><span className="warp-field-label">Encryption</span>
            <Input value={encryption} onChange={(e) => setEncryption(e.target.value)} placeholder="none" /></label>
        </div>
      ) : null}
      {type === "trojan" ? field("Password", <Input value={password} onChange={(e) => setPassword(e.target.value)} />) : null}
      {type === "shadowsocks" ? (
        <>
          {field("Method", <Select value={method} onChange={(e) => setMethod(e.target.value)}>
            {["2022-blake3-aes-128-gcm","2022-blake3-aes-256-gcm","2022-blake3-chacha20-poly1305","aes-256-gcm","chacha20-ietf-poly1305"].map((m)=><option key={m} value={m}>{m}</option>)}
          </Select>)}
          {field("Password", <Input value={password} onChange={(e) => setPassword(e.target.value)} />)}
        </>
      ) : null}
      {(type === "socks" || type === "http") ? (
        <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
          <label className="warp-field-row"><span className="warp-field-label">Username (optional)</span><Input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label className="warp-field-row"><span className="warp-field-label">Password (optional)</span><Input value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        </div>
      ) : null}

      {type === "wireguard" ? (
        <>
          {field("Secret key", <Input value={secretKey} onChange={(e) => setSecretKey(e.target.value)} />)}
          {field("Interface address", <Input value={wgAddress} onChange={(e) => setWgAddress(e.target.value)} placeholder="172.16.0.2/32" />)}
          {field("Peer public key", <Input value={publicKey} onChange={(e) => setPublicKey(e.target.value)} />)}
          {field("Endpoint (host:port)", <Input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="engage.cloudflareclient.com:2408" />)}
          {field("Reserved (WARP, optional)", <Input value={reserved} onChange={(e) => setReserved(e.target.value)} placeholder="1,2,3" />)}
        </>
      ) : null}

      {HAS_STREAM.has(type) ? (
        <>
          <div className="warp-dlg-divider" />
          <div className="warp-dlg-2col">
            <label className="warp-field-row"><span className="warp-field-label">Transport</span>
              <Select value={network} onChange={(e) => setNetwork(e.target.value)}>
                {["tcp","ws","grpc","httpupgrade","xhttp"].map((n)=><option key={n} value={n}>{n}</option>)}
              </Select></label>
            <label className="warp-field-row"><span className="warp-field-label">Security</span>
              <Select value={security} onChange={(e) => setSecurity(e.target.value)}>
                {["none","tls","reality"].map((s)=><option key={s} value={s}>{s}</option>)}
              </Select></label>
          </div>
          {(network === "ws" || network === "httpupgrade") ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">Path</span><Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/" /></label>
              <label className="warp-field-row"><span className="warp-field-label">Host</span><Input value={host} onChange={(e) => setHost(e.target.value)} /></label>
            </div>
          ) : null}
          {network === "grpc" ? field("gRPC serviceName", <Input value={serviceName} onChange={(e) => setServiceName(e.target.value)} />) : null}
          {security === "tls" || security === "reality" ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">SNI</span><Input value={sni} onChange={(e) => setSni(e.target.value)} /></label>
              <label className="warp-field-row"><span className="warp-field-label">Fingerprint</span>
                <Select value={fingerprint} onChange={(e) => setFingerprint(e.target.value)}>
                  {["chrome","firefox","safari","ios","edge","random","randomized"].map((f)=><option key={f} value={f}>{f}</option>)}
                </Select></label>
            </div>
          ) : null}
          {security === "reality" ? (
            <div className="warp-dlg-2col" style={{ marginTop: 12 }}>
              <label className="warp-field-row"><span className="warp-field-label">Reality public key</span><Input value={publicKey} onChange={(e) => setPublicKey(e.target.value)} /></label>
              <label className="warp-field-row"><span className="warp-field-label">Short ID</span><Input value={shortId} onChange={(e) => setShortId(e.target.value)} /></label>
            </div>
          ) : null}
        </>
      ) : null}

      {type === "freedom" ? field("Domain strategy", <Select value={sni} onChange={(e) => setSni(e.target.value)}>{["","UseIP","UseIPv4","UseIPv6","ForceIP"].map((v)=><option key={v} value={v}>{v||"AsIs"}</option>)}</Select>) : null}

      {type === "custom" ? field("Raw Xray outbound (JSON)",
        <textarea className="warp-cert-textarea" rows={9} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder={'{ "protocol": "vless", "settings": { ... }, "streamSettings": { ... } }'} />
      ) : null}

      {!editing ? (
        <>
          <div className="warp-dlg-divider" />
          <label className="warp-switch warp-switch-inline" style={{ marginBottom: makeRule ? 12 : 0 }}>
            <input type="checkbox" checked={makeRule} onChange={() => setMakeRule((v) => !v)} />
            <span className="warp-switch-track" />
            <span className="warp-switch-label">Also create a routing rule for this outbound</span>
          </label>
          {makeRule ? (
            <div className="warp-dlg-2col">
              <label className="warp-field-row">
                <span className="warp-field-label">Route</span>
                <Select value={ruleMatch} onChange={(e) => setRuleMatch(e.target.value)}>
                  <option value="all">All non-domestic traffic</option>
                  <option value="domain">Specific domains</option>
                  <option value="ip">Specific IPs / GeoIP</option>
                  <option value="port">Specific ports</option>
                </Select>
              </label>
              {ruleMatch !== "all" ? (
                <label className="warp-field-row">
                  <span className="warp-field-label">Values (comma-separated)</span>
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
