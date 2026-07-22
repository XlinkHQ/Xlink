"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";

export function protoBadge(p: string): string {
  switch (p.toLowerCase()) {
    case "vless": return "is-blue";
    case "vmess": return "is-indigo";
    case "trojan": return "is-pink";
    case "shadowsocks": return "is-purple";
    case "wireguard": return "is-orange";
    case "hysteria":
    case "hysteria2": return "is-teal";
    case "tuic": return "is-cyan";
    default: return "is-slate";
  }
}

const XRAY_DEFAULT_TEMPLATE = JSON.stringify(
  {
    log: { loglevel: "warning" },
    dns: { servers: ["1.1.1.1", "8.8.8.8", "localhost"] },
    outbounds: [
      { protocol: "freedom", tag: "direct", settings: { domainStrategy: "UseIP" } },
      { protocol: "blackhole", tag: "blocked" },
    ],
    routing: {
      domainStrategy: "IPIfNonMatch",
      rules: [
        { type: "field", protocol: ["bittorrent"], outboundTag: "blocked" },
        { type: "field", ip: ["geoip:private"], outboundTag: "blocked" },
      ],
    },
  },
  null,
  2,
);

export const CORE_DEFAULTS: Record<string, string> = {
  xray: XRAY_DEFAULT_TEMPLATE,
  "sing-box": JSON.stringify(
    {
      log: { level: "warn" },
      dns: { servers: [{ tag: "cf", address: "1.1.1.1" }] },
      outbounds: [
        { type: "direct", tag: "direct" },
        { type: "block", tag: "block" },
      ],
    },
    null,
    2,
  ),
  hysteria: JSON.stringify(
    {
      bandwidth: { up: "100 mbps", down: "100 mbps" },
      ignoreClientBandwidth: false,
      masquerade: { type: "proxy", proxy: { url: "https://news.ycombinator.com/", rewriteHost: true } },
    },
    null,
    2,
  ),
  wireguard: JSON.stringify(
    {
      Interface: { MTU: 1420, DNS: ["1.1.1.1"] },
    },
    null,
    2,
  ),
};

export const CORE_PLACEHOLDERS: Record<string, string> = {
  xray: '{ "dns": { "servers": ["1.1.1.1"] }, "routing": { "rules": [] } }',
  "sing-box": '{ "log": { "level": "warn" }, "outbounds": [] }',
  hysteria: '{ "bandwidth": { "up": "100 mbps", "down": "100 mbps" } }',
  wireguard: '{ "Interface": { "MTU": 1420 } }',
};

function apiOrigin(): string {
  if (typeof window === "undefined") return "";
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env.replace(/\/+$/, "");
  return `${window.location.origin}/api/v1`;
}

export const INSTALLABLE_CORES = ["xray", "singbox", "hysteria", "wireguard"] as const;

export function installCommand(nodeId: string, token: string, cores: string[]): string {
  const base = apiOrigin();
  // No env-var prefix before sudo — it sets the var on the sudo process (often
  // stripped by sudoers) not the child bash. The installer derives the agent URL
  // from the panel URL positional arg, so it's redundant anyway.
  // Pass --cores only when it's a strict subset, so the default (all) stays clean.
  const all = INSTALLABLE_CORES.length;
  const flag =
    cores.length && cores.length < all ? ` --cores=${cores.join(",")}` : "";
  return `curl -fsSL ${base}/agent/install.sh | sudo -E bash -s ${window.location.origin} ${nodeId} ${token}${flag}`;
}

export const CORE_LABELS: Record<string, string> = {
  xray: "Xray",
  "sing-box": "sing-box",
  hysteria: "Hysteria",
  wireguard: "WireGuard",
};

export function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="warp-copyfield">
      <span className="warp-copyfield-label">{label}</span>
      <div className="warp-copyfield-row">
        <div className="warp-copyfield-box">
          <span className="warp-copyfield-val">{value}</span>
        </div>
        <button
          type="button"
          className={cn("warp-copyfield-btn", copied && "is-copied")}
          onClick={async () => {
            const ok = await copyText(value);
            if (!ok) return;
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
