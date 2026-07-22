export function protoBadge(p: string): string {
  switch (p.toLowerCase()) {
    case "vless":
      return "is-blue";
    case "vmess":
      return "is-indigo";
    case "trojan":
      return "is-pink";
    case "shadowsocks":
      return "is-purple";
    case "wireguard":
      return "is-orange";
    case "hysteria":
    case "hysteria2":
      return "is-teal";
    case "tuic":
      return "is-cyan";
    default:
      return "is-slate";
  }
}
