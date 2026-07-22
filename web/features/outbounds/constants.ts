export const TYPES = [
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

export const HAS_ADDRESS = new Set(["vless", "vmess", "trojan", "shadowsocks", "socks", "http"]);
export const HAS_STREAM = new Set(["vless", "vmess", "trojan", "socks", "http"]);
