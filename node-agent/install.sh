#!/usr/bin/env bash
#
# XLink node installer.
#
#   PANEL_URL=https://panel.example.com NODE_ID=<uuid> AGENT_TOKEN=<token> bash install.sh
#   bash install.sh <panel_url> <node_id> <agent_token>
#
# Core selection (default: all):
#   --cores=xray,singbox,hysteria,wireguard      pick exactly these
#   --no-singbox --no-hysteria --no-wireguard    drop individual cores
#   CORES=xray,wireguard bash install.sh         via env
#   --interactive                                pick from a menu
#
set -euo pipefail

PANEL_URL="${XLINK_PANEL_URL:-}"
NODE_ID="${XLINK_NODE_ID:-}"
AGENT_TOKEN="${XLINK_AGENT_TOKEN:-}"
INTERVAL="${XLINK_INTERVAL:-15}"
AGENT_URL="${XLINK_AGENT_URL:-}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

WANT_XRAY=1
WANT_SINGBOX="${XLINK_INSTALL_SINGBOX:-1}"
WANT_HYSTERIA="${XLINK_INSTALL_HYSTERIA:-1}"
WANT_WIREGUARD="${XLINK_INSTALL_WIREGUARD:-1}"
INTERACTIVE=0

C_DIM='\033[2m'; C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_RED='\033[31m'; C_YELLOW='\033[33m'; C_RST='\033[0m'
log()  { printf "${C_CYAN}▸${C_RST} %s\n" "$*"; }
ok()   { printf "  ${C_GREEN}✓${C_RST} %s\n" "$*"; }
skip() { printf "  ${C_DIM}•${C_RST} ${C_DIM}%s${C_RST}\n" "$*"; }
warn() { printf "  ${C_YELLOW}!${C_RST} %s\n" "$*"; }
die()  { printf "${C_RED}✗ %s${C_RST}\n" "$*" >&2; exit 1; }

apply_cores_list() {
  WANT_XRAY=0 WANT_SINGBOX=0 WANT_HYSTERIA=0 WANT_WIREGUARD=0
  local IFS=','
  for c in $1; do
    case "$(echo "$c" | tr 'A-Z' 'a-z' | tr -d ' ')" in
      xray) WANT_XRAY=1 ;;
      singbox|sing-box) WANT_SINGBOX=1 ;;
      hysteria|hysteria2|hy2) WANT_HYSTERIA=1 ;;
      wireguard|wg) WANT_WIREGUARD=1 ;;
      "") ;;
      *) die "unknown core '$c' (valid: xray, singbox, hysteria, wireguard)" ;;
    esac
  done
}

POS=()
for arg in "$@"; do
  case "$arg" in
    --cores=*)      apply_cores_list "${arg#*=}" ;;
    --no-singbox)   WANT_SINGBOX=0 ;;
    --no-hysteria)  WANT_HYSTERIA=0 ;;
    --no-wireguard) WANT_WIREGUARD=0 ;;
    --interactive|-i) INTERACTIVE=1 ;;
    -*) die "unknown flag '$arg'" ;;
    *) POS+=("$arg") ;;
  esac
done
[ -n "${CORES:-}" ] && apply_cores_list "$CORES"
PANEL_URL="${PANEL_URL:-${POS[0]:-}}"
NODE_ID="${NODE_ID:-${POS[1]:-}}"
AGENT_TOKEN="${AGENT_TOKEN:-${POS[2]:-}}"

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)."

ask_core() {
  local label="$1" cur="$2" ans
  read -rp "  install ${label}? [$([ "$cur" = 1 ] && echo 'Y/n' || echo 'y/N')] " ans
  case "${ans:-}" in
    y|Y) echo 1 ;; n|N) echo 0 ;; *) echo "$cur" ;;
  esac
}
if [ "$INTERACTIVE" = 1 ]; then
  log "select cores (xray is always installed)"
  WANT_SINGBOX="$(ask_core 'sing-box' "$WANT_SINGBOX")"
  WANT_HYSTERIA="$(ask_core 'hysteria' "$WANT_HYSTERIA")"
  WANT_WIREGUARD="$(ask_core 'wireguard' "$WANT_WIREGUARD")"
fi

[ -z "$PANEL_URL" ]   && read -rp "Panel URL: " PANEL_URL
[ -z "$NODE_ID" ]     && read -rp "Node ID: " NODE_ID
[ -z "$AGENT_TOKEN" ] && read -rp "Agent token: " AGENT_TOKEN
[ -n "$PANEL_URL" ] && [ -n "$NODE_ID" ] && [ -n "$AGENT_TOKEN" ] || die "PANEL_URL, NODE_ID and AGENT_TOKEN are required."

selected=""
[ "$WANT_XRAY" = 1 ]      && selected="$selected xray"
[ "$WANT_SINGBOX" = 1 ]   && selected="$selected sing-box"
[ "$WANT_HYSTERIA" = 1 ]  && selected="$selected hysteria"
[ "$WANT_WIREGUARD" = 1 ] && selected="$selected wireguard"
log "cores:${selected}"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) GOARCH="amd64" ;;
  aarch64|arm64) GOARCH="arm64" ;;
  *) GOARCH="amd64" ;;
esac

R_XRAY="skipped" R_SINGBOX="skipped" R_HYSTERIA="skipped" R_WIREGUARD="skipped"

log "base dependencies"
if ! command -v python3 >/dev/null 2>&1; then
  (apt-get update -y >/dev/null 2>&1 && apt-get install -y python3 >/dev/null 2>&1) ||
    yum install -y python3 >/dev/null 2>&1 || die "install python3 manually."
  ok "python3 installed"
else
  skip "python3 present"
fi

# ---------- xray ----------
if [ "$WANT_XRAY" = 1 ]; then
  log "xray core"
  if command -v xray >/dev/null 2>&1; then
    skip "xray present ($(xray version 2>/dev/null | head -1 | awk '{print $2}'))"
    R_XRAY="present"
  else
    bash <(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) install >/dev/null 2>&1 &&
      { ok "xray installed"; R_XRAY="installed"; } || die "xray install failed."
  fi
fi

# ---------- sing-box (built with v2ray_api for per-user traffic) ----------
sb_has_v2ray() { command -v sing-box >/dev/null 2>&1 && sing-box version 2>/dev/null | grep -q with_v2ray_api; }
if [ "$WANT_SINGBOX" = 1 ]; then
  log "sing-box core (v2ray_api traffic stats)"
  if sb_has_v2ray; then
    skip "sing-box (v2ray_api) present"
    R_SINGBOX="present"
  else
    GO_VER="1.24.7"
    if [ ! -x /usr/local/go/bin/go ] || ! /usr/local/go/bin/go version 2>/dev/null | grep -q "go1.2[4-9]"; then
      curl -fsSL "https://go.dev/dl/go${GO_VER}.linux-${GOARCH}.tar.gz" -o /tmp/go.tgz &&
        rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tgz && ok "Go ${GO_VER}" || warn "Go install failed"
    fi
    if [ -x /usr/local/go/bin/go ]; then
      GOBIN=/usr/local/bin GOTOOLCHAIN=auto /usr/local/go/bin/go install \
        -tags "with_quic,with_grpc,with_v2ray_api,with_clash_api,with_gvisor,with_utls" \
        github.com/sagernet/sing-box/cmd/sing-box@latest >/dev/null 2>&1 || warn "sing-box build failed"
      command -v grpcurl >/dev/null 2>&1 || GOBIN=/usr/local/bin GOTOOLCHAIN=auto /usr/local/go/bin/go install \
        github.com/fullstorydev/grpcurl/cmd/grpcurl@latest >/dev/null 2>&1 || warn "grpcurl install failed"
    fi
    mkdir -p /opt/xlink
    cat > /opt/xlink/v2ray_stats.proto <<'PROTO'
syntax = "proto3";
package v2ray.core.app.stats.command;
message QueryStatsRequest { string pattern = 1; bool reset = 2; }
message Stat { string name = 1; int64 value = 2; }
message QueryStatsResponse { repeated Stat stat = 1; }
service StatsService { rpc QueryStats(QueryStatsRequest) returns (QueryStatsResponse); }
PROTO
    if sb_has_v2ray; then
      ok "sing-box (v2ray_api) installed"; R_SINGBOX="installed"
    elif command -v sing-box >/dev/null 2>&1; then
      R_SINGBOX="installed (no stats)"
    else
      curl -fsSL https://sing-box.app/install.sh -o /tmp/sb.sh && bash /tmp/sb.sh >/dev/null 2>&1 &&
        { ok "sing-box installed (no traffic stats)"; R_SINGBOX="installed (no stats)"; } ||
        { warn "sing-box install failed"; R_SINGBOX="failed"; }
    fi
  fi
fi
if command -v sing-box >/dev/null 2>&1 && [ "$WANT_SINGBOX" = 1 ]; then
  SB_BIN="$(command -v sing-box)"; mkdir -p /etc/sing-box
  [ -f /etc/sing-box/config.json ] || echo '{}' > /etc/sing-box/config.json
  cat > /etc/systemd/system/sing-box.service <<UNIT
[Unit]
Description=sing-box (xlink)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=${SB_BIN} run -c /etc/sing-box/config.json
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload; systemctl enable sing-box >/dev/null 2>&1 || true
fi

# ---------- hysteria2 ----------
if [ "$WANT_HYSTERIA" = 1 ]; then
  log "hysteria core"
  if command -v hysteria >/dev/null 2>&1; then
    skip "hysteria present"; R_HYSTERIA="present"
  elif bash <(curl -fsSL https://get.hy2.sh/) >/dev/null 2>&1; then
    ok "hysteria installed"; R_HYSTERIA="installed"
  else
    warn "hysteria install failed"; R_HYSTERIA="failed"
  fi
fi
if command -v hysteria >/dev/null 2>&1 && [ "$WANT_HYSTERIA" = 1 ]; then
  mkdir -p /etc/hysteria
  [ -f /etc/hysteria/config.json ] || echo '{}' > /etc/hysteria/config.json
  HBIN="$(command -v hysteria)"
  systemctl disable --now hysteria-server.service >/dev/null 2>&1 || true
  cat > /etc/systemd/system/hysteria-server.service <<UNIT
[Unit]
Description=hysteria server (xlink)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=${HBIN} server -c /etc/hysteria/config.json
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload; systemctl enable hysteria-server >/dev/null 2>&1 || true
fi

# ---------- wireguard ----------
if [ "$WANT_WIREGUARD" = 1 ]; then
  log "wireguard core"
  if command -v wg >/dev/null 2>&1; then
    skip "wireguard present"; R_WIREGUARD="present"
  elif (apt-get update -y >/dev/null 2>&1 && apt-get install -y wireguard wireguard-tools >/dev/null 2>&1) ||
       yum install -y wireguard-tools >/dev/null 2>&1; then
    ok "wireguard installed"; R_WIREGUARD="installed"
  else
    warn "wireguard install failed"; R_WIREGUARD="failed"
  fi
fi

# ---------- agent ----------
log "xlink agent"
mkdir -p /opt/xlink
if [ -f "$SRC_DIR/xlink-agent.py" ]; then
  cp "$SRC_DIR/xlink-agent.py" /opt/xlink/xlink-agent.py
elif [ -n "$AGENT_URL" ]; then
  curl -fsSL "$AGENT_URL" -o /opt/xlink/xlink-agent.py
else
  die "xlink-agent.py not found next to install.sh and XLINK_AGENT_URL not set."
fi
cat > /etc/systemd/system/xlink-agent.service <<EOF
[Unit]
Description=XLink Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=XLINK_PANEL_URL=${PANEL_URL}
Environment=XLINK_NODE_ID=${NODE_ID}
Environment=XLINK_AGENT_TOKEN=${AGENT_TOKEN}
Environment=XLINK_INTERVAL=${INTERVAL}
ExecStart=/usr/bin/python3 /opt/xlink/xlink-agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now xlink-agent >/dev/null 2>&1
ok "agent running"

# ---------- summary ----------
row() { printf "  %-12s ${2}%s${C_RST}\n" "$1" "$3"; }
tone() { case "$1" in installed|present) echo "$C_GREEN" ;; failed) echo "$C_RED" ;; skipped) echo "$C_DIM" ;; *) echo "$C_YELLOW" ;; esac; }
echo
printf "${C_CYAN}── XLink node ready ──${C_RST}\n"
row "xray"      "$(tone "$R_XRAY")"      "$R_XRAY"
row "sing-box"  "$(tone "$R_SINGBOX")"   "$R_SINGBOX"
row "hysteria"  "$(tone "$R_HYSTERIA")"  "$R_HYSTERIA"
row "wireguard" "$(tone "$R_WIREGUARD")" "$R_WIREGUARD"
echo
log "node appears active in the panel within ~${INTERVAL}s"
log "logs:  journalctl -u xlink-agent -f"
