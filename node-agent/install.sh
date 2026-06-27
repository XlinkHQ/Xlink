#!/usr/bin/env bash
#
# XLink node manager — install and manage an XLink node agent + cores.
#
# One-liner (panel serves this script):
#   curl -fsSL https://panel/api/v1/agent/install.sh | sudo -E bash -s <panel_url> <node_id> <token>
#
# After install, manage with:  xlink <command>
#   install [opts]     install/reinstall agent + cores
#   update             pull latest agent + restart
#   restart            restart the agent
#   stop | start       stop/start the agent
#   status             show agent + core status
#   logs               follow agent logs
#   core-update        reinstall/upgrade a core
#   uninstall          remove agent + service (keeps cores)
#
# Install options:
#   --cores=xray,singbox,hysteria,wireguard   pick exactly these (default: all)
#   --no-singbox --no-hysteria --no-wireguard drop individual cores
#   --interactive | -i                        pick cores from a menu
#   env: CORES=, XLINK_PANEL_URL=, XLINK_NODE_ID=, XLINK_AGENT_TOKEN=, XLINK_AGENT_URL=
#
set -euo pipefail

XLINK_DIR="/opt/xlink"
AGENT_PY="$XLINK_DIR/xlink-agent.py"
UNIT="/etc/systemd/system/xlink-agent.service"
BIN="/usr/local/bin/xlink"
INTERVAL="${XLINK_INTERVAL:-15}"

C_DIM='\033[2m'; C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_RED='\033[31m'; C_YELLOW='\033[33m'; C_B='\033[1m'; C_RST='\033[0m'
log()  { printf "${C_CYAN}▸${C_RST} %s\n" "$*"; }
ok()   { printf "  ${C_GREEN}✓${C_RST} %s\n" "$*"; }
skip() { printf "  ${C_DIM}•${C_RST} ${C_DIM}%s${C_RST}\n" "$*"; }
warn() { printf "  ${C_YELLOW}!${C_RST} %s\n" "$*"; }
die()  { printf "${C_RED}✗ %s${C_RST}\n" "$*" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run as root (sudo)."; }

ARCH="$(uname -m)"
case "$ARCH" in x86_64|amd64) GOARCH=amd64 ;; aarch64|arm64) GOARCH=arm64 ;; *) GOARCH=amd64 ;; esac

# ---------------------------------------------------------------- cores

install_xray() {
  log "xray core"
  if command -v xray >/dev/null 2>&1; then
    skip "xray present ($(xray version 2>/dev/null | head -1 | awk '{print $2}'))"; return
  fi
  bash <(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) install >/dev/null 2>&1 &&
    ok "xray installed" || die "xray install failed."
}

_sb_has_v2ray() { command -v sing-box >/dev/null 2>&1 && sing-box version 2>/dev/null | grep -q with_v2ray_api; }
install_singbox() {
  log "sing-box core (v2ray_api traffic stats)"
  if _sb_has_v2ray; then skip "sing-box (v2ray_api) present"; _singbox_unit; return; fi
  local gv="1.24.7"
  if [ ! -x /usr/local/go/bin/go ] || ! /usr/local/go/bin/go version 2>/dev/null | grep -q "go1.2[4-9]"; then
    if curl -fsSL "https://go.dev/dl/go${gv}.linux-${GOARCH}.tar.gz" -o /tmp/go.tgz; then
      rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tgz && ok "Go ${gv}"
    else warn "Go download failed — sing-box stats unavailable"; fi
  fi
  if [ -x /usr/local/go/bin/go ]; then
    GOBIN=/usr/local/bin GOTOOLCHAIN=auto /usr/local/go/bin/go install \
      -tags "with_quic,with_grpc,with_v2ray_api,with_clash_api,with_gvisor,with_utls" \
      github.com/sagernet/sing-box/cmd/sing-box@latest >/dev/null 2>&1 || warn "sing-box build failed"
    command -v grpcurl >/dev/null 2>&1 || GOBIN=/usr/local/bin GOTOOLCHAIN=auto /usr/local/go/bin/go install \
      github.com/fullstorydev/grpcurl/cmd/grpcurl@latest >/dev/null 2>&1 || true
  fi
  mkdir -p "$XLINK_DIR"
  cat > "$XLINK_DIR/v2ray_stats.proto" <<'PROTO'
syntax = "proto3";
package v2ray.core.app.stats.command;
message QueryStatsRequest { string pattern = 1; bool reset = 2; }
message Stat { string name = 1; int64 value = 2; }
message QueryStatsResponse { repeated Stat stat = 1; }
service StatsService { rpc QueryStats(QueryStatsRequest) returns (QueryStatsResponse); }
PROTO
  if _sb_has_v2ray; then ok "sing-box (v2ray_api) installed"
  elif ! command -v sing-box >/dev/null 2>&1; then
    curl -fsSL https://sing-box.app/install.sh | bash >/dev/null 2>&1 && ok "sing-box installed (no stats)" || warn "sing-box install failed"
  fi
  _singbox_unit
}
_singbox_unit() {
  command -v sing-box >/dev/null 2>&1 || return 0
  mkdir -p /etc/sing-box; [ -f /etc/sing-box/config.json ] || echo '{}' > /etc/sing-box/config.json
  cat > /etc/systemd/system/sing-box.service <<UNIT
[Unit]
Description=sing-box (xlink)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=$(command -v sing-box) run -c /etc/sing-box/config.json
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload; systemctl enable sing-box >/dev/null 2>&1 || true
}

install_hysteria() {
  log "hysteria core"
  if ! command -v hysteria >/dev/null 2>&1; then
    bash <(curl -fsSL https://get.hy2.sh/) >/dev/null 2>&1 && ok "hysteria installed" || warn "hysteria install failed"
  else skip "hysteria present"; fi
  command -v hysteria >/dev/null 2>&1 || return 0
  mkdir -p /etc/hysteria; [ -f /etc/hysteria/config.json ] || echo '{}' > /etc/hysteria/config.json
  systemctl disable --now hysteria-server.service >/dev/null 2>&1 || true
  cat > /etc/systemd/system/hysteria-server.service <<UNIT
[Unit]
Description=hysteria server (xlink)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=$(command -v hysteria) server -c /etc/hysteria/config.json
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload; systemctl enable hysteria-server >/dev/null 2>&1 || true
}

install_wireguard() {
  log "wireguard core"
  if command -v wg >/dev/null 2>&1; then skip "wireguard present"; return; fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard-tools iproute2 iptables >/dev/null 2>&1 && ok "wireguard installed" && return
  fi
  if command -v dnf >/dev/null 2>&1; then dnf install -y wireguard-tools iproute iptables >/dev/null 2>&1 && ok "wireguard installed" && return; fi
  if command -v yum >/dev/null 2>&1; then yum install -y wireguard-tools iproute iptables >/dev/null 2>&1 && ok "wireguard installed" && return; fi
  command -v wg >/dev/null 2>&1 && { ok "wireguard installed"; return; }
  warn "wireguard install failed (need wireguard-tools)"
}

# ---------------------------------------------------------------- agent

fetch_agent() {
  mkdir -p "$XLINK_DIR"
  local src_dir; src_dir="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
  if [ -n "$src_dir" ] && [ -f "$src_dir/xlink-agent.py" ]; then
    cp "$src_dir/xlink-agent.py" "$AGENT_PY"
  elif [ -n "${XLINK_AGENT_URL:-}" ]; then
    curl -fsSL "$XLINK_AGENT_URL" -o "$AGENT_PY" || die "could not download agent from XLINK_AGENT_URL"
  elif [ -n "${XLINK_PANEL_URL:-}" ]; then
    curl -fsSL "${XLINK_PANEL_URL%/}/api/v1/agent/xlink-agent.py" -o "$AGENT_PY" || die "could not download agent from panel"
  else
    die "agent source not found (need file next to script, XLINK_AGENT_URL, or XLINK_PANEL_URL)"
  fi
  [ -s "$AGENT_PY" ] || die "downloaded agent is empty"
}

write_unit() {
  cat > "$UNIT" <<EOF
[Unit]
Description=XLink Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=XLINK_PANEL_URL=${XLINK_PANEL_URL}
Environment=XLINK_NODE_ID=${XLINK_NODE_ID}
Environment=XLINK_AGENT_TOKEN=${XLINK_AGENT_TOKEN}
Environment=XLINK_INTERVAL=${INTERVAL}
ExecStart=/usr/bin/python3 ${AGENT_PY}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
}

install_self() { cp "$0" "$BIN" 2>/dev/null && chmod +x "$BIN" 2>/dev/null || true; }

# ---------------------------------------------------------------- commands

cmd_install() {
  need_root
  local want_xray=1 want_sb="${XLINK_INSTALL_SINGBOX:-1}" want_hy="${XLINK_INSTALL_HYSTERIA:-1}" want_wg="${XLINK_INSTALL_WIREGUARD:-1}" interactive=0
  local pos=()
  apply_cores() {
    want_xray=0 want_sb=0 want_hy=0 want_wg=0; local IFS=','
    for c in $1; do case "$(echo "$c"|tr 'A-Z' 'a-z'|tr -d ' ')" in
      xray) want_xray=1 ;; singbox|sing-box) want_sb=1 ;; hysteria|hysteria2|hy2) want_hy=1 ;;
      wireguard|wg) want_wg=1 ;; "") ;; *) die "unknown core '$c'" ;; esac; done
  }
  [ -n "${CORES:-}" ] && apply_cores "$CORES"
  for a in "$@"; do case "$a" in
    --cores=*) apply_cores "${a#*=}" ;;
    --no-singbox) want_sb=0 ;; --no-hysteria) want_hy=0 ;; --no-wireguard) want_wg=0 ;;
    --interactive|-i) interactive=1 ;;
    -*) die "unknown flag '$a'" ;; *) pos+=("$a") ;;
  esac; done

  XLINK_PANEL_URL="${XLINK_PANEL_URL:-${pos[0]:-}}"
  XLINK_NODE_ID="${XLINK_NODE_ID:-${pos[1]:-}}"
  XLINK_AGENT_TOKEN="${XLINK_AGENT_TOKEN:-${pos[2]:-}}"

  if [ "$interactive" = 1 ]; then
    log "select cores (xray always installed)"
    _ask() { local a; read -rp "  install $1? [$([ "$2" = 1 ] && echo Y/n || echo y/N)] " a; case "$a" in y|Y) echo 1;; n|N) echo 0;; *) echo "$2";; esac; }
    want_sb=$(_ask sing-box "$want_sb"); want_hy=$(_ask hysteria "$want_hy"); want_wg=$(_ask wireguard "$want_wg")
  fi
  [ -z "$XLINK_PANEL_URL" ] && read -rp "Panel URL: " XLINK_PANEL_URL
  [ -z "$XLINK_NODE_ID" ] && read -rp "Node ID: " XLINK_NODE_ID
  [ -z "$XLINK_AGENT_TOKEN" ] && read -rp "Agent token: " XLINK_AGENT_TOKEN
  [ -n "$XLINK_PANEL_URL" ] && [ -n "$XLINK_NODE_ID" ] && [ -n "$XLINK_AGENT_TOKEN" ] || die "panel URL, node ID and token are required."
  export XLINK_PANEL_URL XLINK_NODE_ID XLINK_AGENT_TOKEN

  local sel=""; [ "$want_xray" = 1 ] && sel+=" xray"; [ "$want_sb" = 1 ] && sel+=" sing-box"
  [ "$want_hy" = 1 ] && sel+=" hysteria"; [ "$want_wg" = 1 ] && sel+=" wireguard"
  log "cores:${sel}"

  log "base dependencies"
  command -v python3 >/dev/null 2>&1 && skip "python3 present" || {
    (apt-get update -y >/dev/null 2>&1 && apt-get install -y python3 >/dev/null 2>&1) || yum install -y python3 >/dev/null 2>&1 || die "install python3 manually."; ok "python3 installed"; }
  command -v curl >/dev/null 2>&1 || { apt-get install -y curl >/dev/null 2>&1 || yum install -y curl >/dev/null 2>&1 || true; }

  [ "$want_xray" = 1 ] && install_xray
  [ "$want_sb" = 1 ] && install_singbox
  [ "$want_hy" = 1 ] && install_hysteria
  [ "$want_wg" = 1 ] && install_wireguard

  log "xlink agent"
  fetch_agent; write_unit; install_self
  systemctl enable --now xlink-agent >/dev/null 2>&1
  ok "agent running"

  _row() { printf "  %-12s ${2}%s${C_RST}\n" "$1" "$3"; }
  _t() { case "$1" in installed|present|running) echo "$C_GREEN";; failed|missing) echo "$C_RED";; *) echo "$C_DIM";; esac; }
  echo; printf "${C_B}${C_CYAN}── XLink node ready ──${C_RST}\n"
  _row xray "$(_t "$(command -v xray >/dev/null 2>&1 && echo present || echo missing)")" "$(command -v xray >/dev/null 2>&1 && echo present || echo 'not installed')"
  _row sing-box "$(_t "$(command -v sing-box >/dev/null 2>&1 && echo present || echo skipped)")" "$([ "$want_sb" = 1 ] && (command -v sing-box >/dev/null 2>&1 && echo present || echo failed) || echo skipped)"
  _row hysteria "$(_t "$([ "$want_hy" = 1 ] && (command -v hysteria >/dev/null 2>&1 && echo present || echo failed) || echo skipped)")" "$([ "$want_hy" = 1 ] && (command -v hysteria >/dev/null 2>&1 && echo present || echo failed) || echo skipped)"
  _row wireguard "$(_t "$([ "$want_wg" = 1 ] && (command -v wg >/dev/null 2>&1 && echo present || echo failed) || echo skipped)")" "$([ "$want_wg" = 1 ] && (command -v wg >/dev/null 2>&1 && echo present || echo failed) || echo skipped)"
  echo
  log "node appears active in the panel within ~${INTERVAL}s"
  log "manage:  xlink status | xlink logs | xlink update"
}

cmd_update() {
  need_root; [ -f "$UNIT" ] || die "not installed. run: xlink install"
  log "updating agent"
  # reuse env from existing unit
  eval "$(grep -E '^Environment=XLINK_' "$UNIT" | sed 's/^Environment=//')"
  export XLINK_PANEL_URL XLINK_NODE_ID XLINK_AGENT_TOKEN
  fetch_agent; install_self
  systemctl restart xlink-agent && ok "agent updated + restarted"
}

cmd_core_update() {
  need_root; local core="${1:-}"
  case "$core" in
    xray) command -v xray >/dev/null 2>&1 && bash <(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) install >/dev/null 2>&1 && ok "xray updated" || install_xray ;;
    singbox|sing-box) install_singbox ;;
    hysteria) install_hysteria ;;
    wireguard|wg) install_wireguard ;;
    *) die "usage: xlink core-update <xray|singbox|hysteria|wireguard>" ;;
  esac
  systemctl restart xlink-agent >/dev/null 2>&1 || true
}

cmd_status() {
  local act; act="$(systemctl is-active xlink-agent 2>/dev/null || echo inactive)"
  printf "${C_B}XLink node${C_RST}\n"
  printf "  agent      %s\n" "$([ "$act" = active ] && printf "${C_GREEN}running${C_RST}" || printf "${C_RED}%s${C_RST}" "$act")"
  for c in xray sing-box hysteria wg; do
    local n="$c"; [ "$c" = wg ] && n=wireguard
    command -v "$c" >/dev/null 2>&1 && printf "  %-10s ${C_GREEN}installed${C_RST}\n" "$n" || printf "  %-10s ${C_DIM}absent${C_RST}\n" "$n"
  done
  ip link show wg0 >/dev/null 2>&1 && printf "  wg0        ${C_GREEN}up${C_RST}\n" || true
}

cmd_uninstall() {
  need_root
  read -rp "Remove XLink agent + service? cores stay. [y/N] " a; [ "$a" = y ] || [ "$a" = Y ] || exit 0
  systemctl disable --now xlink-agent >/dev/null 2>&1 || true
  rm -f "$UNIT"; systemctl daemon-reload
  rm -rf "$XLINK_DIR"; rm -f "$BIN"
  ok "uninstalled (cores left intact)"
}

usage() {
  cat <<USAGE
${C_B}xlink${C_RST} — XLink node manager
  install [<panel> <id> <token>] [--cores=..|--no-..|-i]   install agent + cores
  update                            pull latest agent + restart
  restart | start | stop            control the agent
  status                            show agent + cores
  logs                              follow agent logs
  core-update <core>                reinstall/upgrade a core
  uninstall                         remove agent (keeps cores)
USAGE
}

case "${1:-install}" in
  install) shift 2>/dev/null || true; cmd_install "$@" ;;
  update) cmd_update ;;
  core-update) shift; cmd_core_update "$@" ;;
  restart) need_root; systemctl restart xlink-agent && ok "restarted" ;;
  start) need_root; systemctl start xlink-agent && ok "started" ;;
  stop) need_root; systemctl stop xlink-agent && ok "stopped" ;;
  status) cmd_status ;;
  logs) journalctl -u xlink-agent -f ;;
  uninstall) cmd_uninstall ;;
  -h|--help|help) usage ;;
  # backward-compat: positional args = install
  http*|https*) cmd_install "$@" ;;
  *) cmd_install "$@" ;;
esac
