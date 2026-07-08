#!/usr/bin/env bash
#
# XLink bootstrap installer — one command, fully automated:
#   bash <(curl -fsSL https://raw.githubusercontent.com/XlinkHQ/Xlink/main/scripts/install.sh)
#
# It: installs Docker if missing, clones the repo, generates fresh secrets,
# builds/pulls the images, runs migrations, starts the panel, and prints the
# login URL + one-time admin password. Re-running it updates in place.
#
# Options (env or flags):
#   XLINK_DIR=/opt/xlink        where to install (default /opt/xlink)
#   XLINK_REF=main              git ref/tag to check out (default main)
#   XLINK_REPO=<url>            git remote (default the public GitHub repo)
#   --build                     force a local image build (default: pull, build on fail)
set -euo pipefail

REPO="${XLINK_REPO:-https://github.com/XlinkHQ/Xlink.git}"
REF="${XLINK_REF:-main}"
DIR="${XLINK_DIR:-/opt/xlink}"
MODE="pull"
[ "${1:-}" = "--build" ] && MODE="build"

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_RED='\033[31m'; C_B='\033[1m'; C_RST='\033[0m'
log()  { printf "${C_CYAN}▸${C_RST} %s\n" "$*"; }
ok()   { printf "  ${C_GREEN}✓${C_RST} %s\n" "$*"; }
die()  { printf "${C_RED}✗ %s${C_RST}\n" "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root:  sudo bash <(curl -fsSL .../install.sh)"

# --- Docker ---
if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker"
  curl -fsSL https://get.docker.com | sh >/dev/null 2>&1 || die "Docker install failed"
  systemctl enable --now docker >/dev/null 2>&1 || true
  ok "Docker installed"
else
  ok "Docker present"
fi
command -v git >/dev/null 2>&1 || {
  log "installing git"
  (apt-get update -y && apt-get install -y git) >/dev/null 2>&1 \
    || yum install -y git >/dev/null 2>&1 || die "install git manually"
}

# --- Repo (clone or update in place, preserving .env) ---
if [ -d "$DIR/.git" ]; then
  log "updating $DIR"
  git -C "$DIR" fetch --depth 1 origin "$REF" >/dev/null 2>&1
  git -C "$DIR" reset --hard "origin/$REF" >/dev/null 2>&1 || git -C "$DIR" reset --hard "$REF" >/dev/null 2>&1
  ok "repo updated ($REF)"
else
  log "cloning $REPO"
  git clone --depth 1 --branch "$REF" "$REPO" "$DIR" >/dev/null 2>&1 \
    || git clone "$REPO" "$DIR" >/dev/null 2>&1 \
    || die "clone failed (private repo? set XLINK_REPO=https://<token>@github.com/XlinkHQ/Xlink.git)"
  ok "cloned to $DIR"
fi

# --- Hand off to the panel manager (does env-gen, build/pull, migrate, up) ---
cd "$DIR"
chmod +x xlink.sh
log "installing panel ($MODE)"
if [ "$MODE" = "build" ]; then
  ./xlink.sh install build
else
  ./xlink.sh install
fi
