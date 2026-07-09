// SEPARATE RUNTIME MIRROR. This is the TypeScript bundle; it cannot import the
// panel's Python source. The single source of truth for which provider core
// supports which protocol is app/protocols.py (PROTOCOLS -> provider_protocols).
// Keep PROVIDER_PROTOCOLS / PROTOCOLS below in sync with it: the drift guard is
// app/subscription/tests/test_protocol_source.py, which reads THIS file and the
// Python source and fails in CI if they diverge.
export const PROVIDERS = ["xray", "wireguard", "sing-box", "hysteria"];
export const PROTOCOLS = [
  "vless",
  "vmess",
  "trojan",
  "shadowsocks",
  "shadowsocks2022",
  "shadowtls",
  "wireguard",
  "hysteria2",
  "tuic",
  "naive",
  "socks",
];

const PROVIDER_PROTOCOLS: Record<string, string[]> = {
  xray: ["vless", "vmess", "trojan", "shadowsocks", "shadowsocks2022"],
  "sing-box": [
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "shadowsocks2022",
    "shadowtls",
    "hysteria2",
    "tuic",
    "naive",
    "socks",
  ],
  hysteria: ["hysteria2"],
  wireguard: ["wireguard"],
};

export function protocolsFor(provider: string): string[] {
  return PROVIDER_PROTOCOLS[provider] ?? PROTOCOLS;
}
