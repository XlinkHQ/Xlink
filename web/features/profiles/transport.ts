export type TField = {
  key: string;
  label: string;
  type?: "text" | "number" | "select" | "password" | "bool";
  options?: string[];
  placeholder?: string;
};

const XRAY = new Set(["vless", "vmess", "trojan"]);

export const TRANSPORT_KEYS = [
  "host",
  "port",
  "network",
  "security",
  "path",
  "serviceName",
  "mode",
  "sni",
  "remark",
  "dest",
  "fingerprint",
  "alpn",
  "publicKey",
  "shortId",
  "flow",
  "alterId",
  "cipher",
  "method",
  "password",
  "obfs",
  "obfsPassword",
  "allowInsecure",
  "congestionControl",
  "udpRelayMode",
  "address",
  "privateKey",
  "presharedKey",
  "allowedIPs",
  "dns",
  "mtu",
  "persistentKeepalive",
  "fragment",
  "noise",
  "mux",
  "randomUserAgent",
  "shadowtls_version",
  "shadowtls_password",
];

export const NUMERIC_KEYS = new Set(["port", "alterId", "mtu", "persistentKeepalive", "shadowtls_version"]);
export const BOOL_KEYS = new Set(["allowInsecure", "mux", "randomUserAgent"]);

const HOST: TField = { key: "host", label: "Host / address", placeholder: "example.com" };
const PORT: TField = { key: "port", label: "Port", type: "number", placeholder: "443" };

export function transportFields(protocol: string, s: Record<string, string>): TField[] {
  if (XRAY.has(protocol)) {
    const fields: TField[] = [
      HOST,
      PORT,
      { key: "address", label: "Address (CDN, optional)", placeholder: "node IP if empty" },
      {
        key: "network",
        label: "Network",
        type: "select",
        options: ["tcp", "ws", "grpc", "httpupgrade", "xhttp", "splithttp", "kcp"],
      },
      { key: "security", label: "Security", type: "select", options: ["none", "tls", "reality"] },
    ];
    const net = s.network || "tcp";
    const sec = s.security || "none";
    if (["ws", "httpupgrade", "xhttp", "splithttp"].includes(net)) {
      fields.push({ key: "path", label: "Path", placeholder: "/" });
      fields.push({ key: "host", label: "Host header", placeholder: "cdn domain" });
    }
    if (net === "xhttp") {
      fields.push({
        key: "mode",
        label: "XHTTP mode",
        type: "select",
        options: ["auto", "packet-up", "stream-up", "stream-one"],
      });
    }
    if (net === "grpc") fields.push({ key: "serviceName", label: "gRPC service name" });
    if (sec === "tls") {
      fields.push(
        { key: "sni", label: "SNI" },
        { key: "fingerprint", label: "Fingerprint", type: "select", options: ["", "chrome", "firefox", "safari", "random"] },
        { key: "alpn", label: "ALPN", placeholder: "h2,http/1.1" },
      );
    }
    if (sec === "reality") {
      fields.push(
        { key: "sni", label: "SNI" },
        { key: "dest", label: "Dest (steal target)", placeholder: "www.microsoft.com:443" },
        { key: "privateKey", label: "Private key (server)" },
        { key: "publicKey", label: "Public key (client)" },
        { key: "shortId", label: "Short ID" },
        { key: "fingerprint", label: "Fingerprint", type: "select", options: ["chrome", "firefox", "safari", "random"] },
      );
    }
    if (protocol === "vless") {
      fields.push({ key: "flow", label: "Flow", type: "select", options: ["", "xtls-rprx-vision"] });
    }
    if (protocol === "vmess") {
      fields.push(
        { key: "alterId", label: "Alter ID", type: "number", placeholder: "0" },
        { key: "cipher", label: "Cipher", type: "select", options: ["auto", "aes-128-gcm", "chacha20-poly1305", "none"] },
      );
    }
    fields.push(
      {
        key: "remark",
        label: "Remark (link name)",
        placeholder: "{USERNAME} • {DATA_LIMIT} • {DAYS_LEFT}d",
      },
      { key: "fragment", label: "Fragment (len,interval,packets)", placeholder: "100-200,10-20,tlshello" },
      { key: "noise", label: "Noise (packets,delay)", placeholder: "rand:10-20,10-20" },
      { key: "allowInsecure", label: "Allow insecure TLS", type: "bool" },
      { key: "mux", label: "Mux", type: "bool" },
      { key: "randomUserAgent", label: "Random User-Agent", type: "bool" },
    );
    return fields;
  }

  if (protocol === "shadowsocks") {
    return [
      HOST,
      PORT,
      { key: "method", label: "Method", type: "select", options: ["aes-256-gcm", "aes-128-gcm", "chacha20-ietf-poly1305"] },
      { key: "password", label: "Password", type: "password" },
    ];
  }

  if (protocol === "shadowsocks2022") {
    return [
      HOST,
      PORT,
      {
        key: "method",
        label: "Method",
        type: "select",
        options: [
          "2022-blake3-aes-256-gcm",
          "2022-blake3-aes-128-gcm",
          "2022-blake3-chacha20-poly1305",
        ],
      },
      // Server PSK. Each user gets their own key; clients send "server:user".
      { key: "serverPassword", label: "Server key (base64 PSK)", type: "password" },
    ];
  }

  if (protocol === "shadowtls") {
    return [
      HOST,
      PORT,
      { key: "sni", label: "SNI (camouflage host)", placeholder: "www.microsoft.com" },
      { key: "shadowtls_version", label: "ShadowTLS version", type: "select", options: ["3", "2"] },
      { key: "shadowtls_password", label: "ShadowTLS password", type: "password" },
      {
        key: "method",
        label: "Inner SS method",
        type: "select",
        options: ["2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305"],
      },
      { key: "password", label: "Inner SS password", type: "password" },
    ];
  }

  if (protocol === "hysteria2") {
    return [
      HOST,
      PORT,
      { key: "sni", label: "SNI" },
      { key: "obfs", label: "Obfs", type: "select", options: ["", "salamander"] },
      { key: "obfsPassword", label: "Obfs password", type: "password" },
      { key: "allowInsecure", label: "Allow insecure", type: "select", options: ["false", "true"] },
    ];
  }

  if (protocol === "tuic") {
    return [
      HOST,
      PORT,
      { key: "password", label: "Password", type: "password" },
      { key: "sni", label: "SNI" },
      { key: "alpn", label: "ALPN", placeholder: "h3" },
      { key: "congestionControl", label: "Congestion control", type: "select", options: ["bbr", "cubic", "new_reno"] },
      { key: "udpRelayMode", label: "UDP relay mode", type: "select", options: ["native", "quic"] },
      { key: "allowInsecure", label: "Allow insecure", type: "select", options: ["false", "true"] },
    ];
  }

  if (protocol === "anytls") {
    return [
      HOST,
      PORT,
      { key: "password", label: "Password", type: "password" },
      { key: "sni", label: "SNI" },
      { key: "fingerprint", label: "uTLS fingerprint", type: "select", options: ["", "chrome", "firefox", "safari", "ios", "edge", "random"] },
      { key: "allowInsecure", label: "Allow insecure", type: "select", options: ["false", "true"] },
    ];
  }

  if (protocol === "wireguard") {
    return [
      HOST,
      PORT,
      { key: "address", label: "Address", placeholder: "10.0.0.2/32" },
      { key: "privateKey", label: "Private key", type: "password" },
      { key: "publicKey", label: "Peer public key" },
      { key: "presharedKey", label: "Preshared key", type: "password" },
      { key: "allowedIPs", label: "Allowed IPs", placeholder: "0.0.0.0/0" },
      { key: "dns", label: "DNS", placeholder: "1.1.1.1" },
      { key: "mtu", label: "MTU", type: "number", placeholder: "1420" },
      { key: "persistentKeepalive", label: "Keepalive (s)", type: "number", placeholder: "25" },
    ];
  }

  return [HOST, PORT];
}
