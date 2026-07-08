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
  xray: ["vless", "vmess", "trojan", "shadowsocks", "shadowsocks2022", "socks"],
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
