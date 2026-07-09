#!/usr/bin/env bash
set -euo pipefail

APP_DIR_DEFAULT="/opt/xlink"
BIN_PATH="/usr/local/bin/xlink"
REPO_RAW="${XLINK_REPO_RAW:-}"

export DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1

C_DIM='\033[2m'; C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_RED='\033[31m'
C_YELLOW='\033[33m'; C_B='\033[1m'; C_RST='\033[0m'
log()  { printf "${C_CYAN}▸${C_RST} %s\n" "$*"; }
ok()   { printf "  ${C_GREEN}✓${C_RST} %s\n" "$*"; }
skip() { printf "  ${C_DIM}•${C_RST} ${C_DIM}%s${C_RST}\n" "$*"; }
warn() { printf "  ${C_YELLOW}!${C_RST} %s\n" "$*"; }
die()  { printf "${C_RED}✗ %s${C_RST}\n" "$*" >&2; exit 1; }

need_root() { [ "$(id -u)" -eq 0 ] || die "run as root (sudo xlink $CMD)"; }

APP_DIR="${XLINK_DIR:-$APP_DIR_DEFAULT}"
[ -f "$(pwd)/docker-compose.yml" ] && APP_DIR="$(pwd)"

COMPOSE_BASE="-f docker-compose.yml"
COMPOSE_PROD="-f docker-compose.yml -f docker-compose.prod.yml"
MIN_FREE_GB="${MIN_FREE_GB:-3}"
BUILD_MIN_FREE_GB="${BUILD_MIN_FREE_GB:-8}"

pin_version() {
  local tag="$1"
  [ -n "$tag" ] || return 0
  [ "${tag#v}" = "$tag" ] && tag="v$tag"
  local env="$APP_DIR/.env"
  if grep -q '^XLINK_IMAGE_TAG=' "$env" 2>/dev/null; then
    grep -v '^XLINK_IMAGE_TAG=' "$env" > "$env.tmp" && mv "$env.tmp" "$env"
  fi
  echo "XLINK_IMAGE_TAG=$tag" >> "$env"
  ok "pinned image tag: $tag"
}

free_gb() { df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0; }

# Trim build cache to ~3GB, keeping warm layers. --keep-storage was renamed to
# --reserved-space in Docker Engine 28+, so try the new flag first and fall back
# to the old one; daemon.json GC backstops either way.
prune_cache() {
  docker builder prune -f --reserved-space 3g >/dev/null 2>&1 \
    || docker builder prune -f --keep-storage 3g >/dev/null 2>&1 || true
}

LOCAL_BUILD=0

compose() {
  local dom; dom="$(grep -E '^XLINK_DOMAIN=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
  local base
  if [ "$LOCAL_BUILD" = "1" ] || [ ! -f "$APP_DIR/docker-compose.prod.yml" ]; then
    base="$COMPOSE_BASE"
  else
    base="$COMPOSE_PROD"
  fi
  [ -n "$dom" ] && base="$base --profile tls"
  ( cd "$APP_DIR" && docker compose $base "$@" )
}

install_self() {
  local src="${BASH_SOURCE[0]}"
  if [ "$(readlink -f "$src" 2>/dev/null || echo "$src")" != "$BIN_PATH" ]; then
    cp "$src" "$BIN_PATH" && chmod +x "$BIN_PATH"
    ok "installed 'xlink' command to $BIN_PATH"
  fi
}

install_daemon_config() {
  local src="$APP_DIR/docker/daemon.json"
  [ -f "$src" ] || return 0
  if ! cmp -s "$src" /etc/docker/daemon.json 2>/dev/null; then
    log "installing Docker daemon config (cache GC + log rotation)"
    mkdir -p /etc/docker && cp "$src" /etc/docker/daemon.json
    systemctl restart docker 2>/dev/null || service docker restart 2>/dev/null || true
    for _ in $(seq 1 30); do docker ps >/dev/null 2>&1 && break; sleep 1; done
    ok "daemon config installed"
  fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "installing Docker"
    curl -fsSL https://get.docker.com | sh >/dev/null 2>&1 || die "Docker install failed"
    ok "Docker installed"
  fi
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"
  docker ps >/dev/null 2>&1 || die "Docker daemon is not running"
}

fix_env_owner() {
  # Hand ownership of .env + install dir to the real user when invoked via sudo,
  # so `docker compose`/`xlink` can read the secret file without root. Runs on
  # every install/update, not just first gen — a pre-existing root-owned .env
  # (from an earlier sudo install) otherwise stays unreadable ("open .env:
  # permission denied", which silently breaks compose → migrate → user create).
  [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] || return 0
  [ -f "$APP_DIR/.env" ] && chown "$SUDO_USER" "$APP_DIR/.env" 2>/dev/null || true
  chown -R "$SUDO_USER" "$APP_DIR" 2>/dev/null || true
}

gen_env() {
  local env="$APP_DIR/.env"
  [ -f "$env" ] && { skip "using existing .env"; fix_env_owner; return 0; }
  command -v openssl >/dev/null 2>&1 || die "openssl is required"
  log "generating .env with fresh secrets"
  local db_pw jwt admin_pw dom acme cors th
  db_pw="$(docker inspect xlink-postgres-1 2>/dev/null | grep -o 'POSTGRES_PASSWORD=[^"]*' | head -1 | cut -d= -f2- || true)"
  [ -n "$db_pw" ] && ok "reusing db password from running postgres" || { db_pw="$(openssl rand -hex 16)"; ok "generated db password"; }
  jwt="$(openssl rand -hex 32)"
  admin_pw="${XLINK_ADMIN_PASSWORD:-$(openssl rand -base64 18 | tr -d '/+=' | head -c 16)XY29ab!}"
  dom="${XLINK_DOMAIN:-}"
  if [ -z "$dom" ] && [ -t 0 ]; then printf "  Panel domain for HTTPS (blank = plain HTTP): "; read -r dom || dom=""; fi
  acme="${XLINK_ACME_EMAIL:-}"
  [ -n "$dom" ] && [ -z "$acme" ] && acme="admin@${dom}"
  cors="*"; th="*"
  [ -n "$dom" ] && cors="https://$dom" && th="$dom"

  # Web port: ask (default 3000), so it needn't collide with something already
  # on 3000. Non-interactive installs keep the default or an env override.
  local web_port
  web_port="${XLINK_WEB_PORT:-}"
  if [ -z "$web_port" ] && [ -t 0 ]; then
    printf "  Web UI port [3000]: "; read -r web_port || web_port=""
  fi
  web_port="${web_port:-3000}"
  case "$web_port" in ''|*[!0-9]*) web_port=3000 ;; esac

  # Secret admin path: serve the panel under an unguessable prefix instead of
  # bare "/", so a random scan of the IP finds nothing. Blank = a fresh random
  # path is generated; type "/" to keep the panel at root; or set your own.
  local web_path
  web_path="${XLINK_WEB_PATH:-}"
  if [ -z "$web_path" ] && [ -t 0 ]; then
    printf "  Secret panel path (blank = random, '/' = root): "; read -r web_path || web_path=""
  fi
  if [ -z "$web_path" ]; then
    web_path="/$(openssl rand -hex 8)"
  fi
  # Normalise: root stays empty (no prefix); otherwise ensure a single leading
  # slash and no trailing slash.
  if [ "$web_path" = "/" ]; then
    web_path=""
  else
    web_path="/$(printf '%s' "$web_path" | sed 's#^/*##; s#/*$##')"
  fi
  # Detect the server's real public IP HERE (on the host — inside the container
  # detection only sees the docker bridge). Prefer an external lookup, fall back
  # to the default-route source address.
  local pub_ip
  pub_ip="${XLINK_PUBLIC_IP:-}"
  if [ -z "$pub_ip" ]; then
    pub_ip="$(curl -fsS --max-time 4 https://api.ipify.org 2>/dev/null || true)"
  fi
  if [ -z "$pub_ip" ]; then
    pub_ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++)if($i=="src"){print $(i+1);exit}}' || true)"
  fi
  cat > "$env" <<EOF
XLINK_ADMIN_USERNAME=admin
XLINK_ADMIN_PASSWORD=$admin_pw
XLINK_ENV=production
XLINK_DEBUG=false
XLINK_HOST=0.0.0.0
XLINK_PORT=8000
XLINK_WEB_PORT=$web_port
XLINK_WEB_PATH=$web_path
XLINK_PUBLIC_IP=$pub_ip
XLINK_DOMAIN=$dom
XLINK_ACME_EMAIL=$acme
XLINK_CORS_ORIGINS=$cors
XLINK_TRUSTED_HOSTS=$th
XLINK_LOG_LEVEL=INFO
XLINK_LOG_JSON=true
XLINK_POSTGRES_HOST=postgres
XLINK_POSTGRES_PORT=5432
XLINK_POSTGRES_USER=xlink
XLINK_POSTGRES_PASSWORD=$db_pw
XLINK_POSTGRES_DB=xlink
XLINK_REDIS_HOST=redis
XLINK_REDIS_PORT=6379
XLINK_JWT_SECRET_KEY=$jwt
XLINK_RATE_LIMIT_ENABLED=true
XLINK_DB_POOL_SIZE=10
XLINK_DB_MAX_OVERFLOW=10
EOF
  chmod 600 "$env"
  fix_env_owner
  ADMIN_PW="$admin_pw"
  ok "wrote .env (mode 600)"
}

do_backup() {
  docker inspect xlink-postgres-1 >/dev/null 2>&1 || { skip "no running database"; return 0; }
  mkdir -p "$APP_DIR/backups"
  local u d bk
  u="$(grep -E '^XLINK_POSTGRES_USER=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || echo xlink)"
  d="$(grep -E '^XLINK_POSTGRES_DB=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || echo xlink)"
  bk="$APP_DIR/backups/backup_$(date +%F_%H%M).sql"
  if compose exec -T postgres pg_dump -U "$u" "$d" > "$bk" 2>/dev/null; then
    ok "backup saved $bk"
    ls -1t "$APP_DIR"/backups/backup_*.sql 2>/dev/null | tail -n +8 | xargs -r rm -f
    gzip -kf "$bk"
    telegram_upload "$bk.gz"
  else
    rm -f "$bk"; skip "backup skipped (database not ready)"
  fi
}

telegram_upload() {
  local file="$1"
  local tok chat
  tok="$(grep -E '^XLINK_BACKUP_TG_TOKEN=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
  chat="$(grep -E '^XLINK_BACKUP_TG_CHAT=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  if curl -sf -F "chat_id=$chat" -F "document=@$file" \
      "https://api.telegram.org/bot${tok}/sendDocument" >/dev/null 2>&1; then
    ok "backup uploaded to Telegram"
  else
    warn "Telegram upload failed"
  fi
}

cmd_backup_service() {
  need_root
  local hours="${1:-6}"
  local marker="# xlink-backup-service"
  local line="0 */$hours * * * $BIN_PATH backup >/dev/null 2>&1 $marker"
  ( crontab -l 2>/dev/null | grep -v "$marker"; echo "$line" ) | crontab -
  ok "scheduled backups every ${hours}h (cron)"
  local tok chat
  tok="$(grep -E '^XLINK_BACKUP_TG_TOKEN=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
  [ -n "$tok" ] || warn "set XLINK_BACKUP_TG_TOKEN + XLINK_BACKUP_TG_CHAT in .env for Telegram delivery"
}

build_images() {
  LOCAL_BUILD=1
  export DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1
  docker image prune -f >/dev/null 2>&1 || true
  local free; free="$(free_gb)"
  [ "${free:-0}" -ge "$BUILD_MIN_FREE_GB" ] || die "only ${free}G free — build needs ≥ ${BUILD_MIN_FREE_GB}G. Use 'xlink update' (pull) or free disk."
  log "building images (${free}G free)"
  compose build || die "build failed"
  prune_cache
  ok "images built"
}

migrate() {
  log "waiting for postgres"
  local u d; u="$(grep -E '^XLINK_POSTGRES_USER=' "$APP_DIR/.env" | cut -d= -f2-)"; d="$(grep -E '^XLINK_POSTGRES_DB=' "$APP_DIR/.env" | cut -d= -f2-)"
  compose up -d postgres redis
  for _ in $(seq 1 30); do compose exec -T postgres pg_isready -U "$u" -d "$d" >/dev/null 2>&1 && break; sleep 1; done
  log "applying migrations"
  compose run --rm migrate && ok "schema up to date"
}

summary() {
  local dom wp wpath ip; dom="$(grep -E '^XLINK_DOMAIN=' "$APP_DIR/.env" | cut -d= -f2-)"; wp="$(grep -E '^XLINK_WEB_PORT=' "$APP_DIR/.env" | cut -d= -f2- || echo 3000)"; wpath="$(grep -E '^XLINK_WEB_PATH=' "$APP_DIR/.env" | cut -d= -f2-)"
  echo; printf "${C_B}${C_CYAN}── XLink ready ──${C_RST}\n"
  if [ -n "$dom" ]; then printf "  %-8s https://%s%s\n" panel "$dom" "$wpath"; else ip="$(hostname -I 2>/dev/null | awk '{print $1}')"; printf "  %-8s http://%s:%s%s\n" panel "$ip" "$wp" "$wpath"; fi
  [ -n "${ADMIN_PW:-}" ] && { printf "  %-8s ${C_B}admin / %s${C_RST}\n" login "$ADMIN_PW"; warn "save this password — shown once"; }
  printf "  %-8s xlink up | down | logs | update | backup | cli | help\n" manage
}

cmd_install() {
  need_root; ensure_docker; install_self; install_daemon_config; gen_env
  pin_version "${VERSION:-}"
  local free; free="$(free_gb)"; log "free disk: ${free}G"
  [ "${free:-0}" -ge "$MIN_FREE_GB" ] || { docker builder prune -af >/dev/null 2>&1 || true; docker image prune -af >/dev/null 2>&1 || true; }
  do_backup
  # A secret admin path (XLINK_WEB_PATH) is baked into the web image at build
  # time, so a registry-pulled image can't carry it — force a local build when
  # one is configured.
  local mode="${1:-pull}"
  if [ "$mode" != "build" ] && grep -qE '^XLINK_WEB_PATH=.+' "$APP_DIR/.env" 2>/dev/null; then
    log "secret web path set → building images locally so it's baked in"
    mode="build"
  fi
  if [ "$mode" = "build" ]; then build_images; else
    log "pulling images"; compose pull 2>/dev/null && ok "images pulled" || { warn "pull failed — building locally"; build_images; }
  fi
  migrate
  log "starting services"; compose up -d
  prune_cache; docker image prune -f >/dev/null 2>&1 || true
  summary
}

cmd_update() {
  need_root; install_self; pin_version "${VERSION:-}"; do_backup
  # Rebuild locally when a secret web path is set (baked into the image at build
  # time); otherwise pull the prebuilt images.
  if grep -qE '^XLINK_WEB_PATH=.+' "$APP_DIR/.env" 2>/dev/null; then
    log "secret web path set → rebuilding images locally"; build_images
  else
    log "pulling images"; compose pull 2>/dev/null || warn "pull failed"
  fi
  migrate
  compose up -d
  prune_cache; docker image prune -f >/dev/null 2>&1 || true
  ok "updated; free disk: $(free_gb)G"
}

cmd_uninstall() {
  need_root
  [ -t 0 ] && { printf "  Remove containers + the xlink command? Data volumes are kept. [y/N] "; read -r a; [ "$a" = "y" ] || exit 0; }
  compose down 2>/dev/null || true
  rm -f "$BIN_PATH"
  ok "uninstalled (data volumes preserved; 'docker volume rm' to purge)"
}

usage() {
  cat <<EOF
xlink — panel installer + manager

  xlink install [build] [--version vX]   install/reinstall
  xlink update [--version vX]             pull, backup, migrate, restart
  xlink up | down | restart | status | logs
  xlink backup                           snapshot the database now
  xlink backup-service [hours]           schedule cron backups (default 6h)
  xlink cli <args>                       run the panel CLI
  xlink edit                             edit .env
  xlink uninstall                        remove containers + command (keeps data)

Telegram backup delivery: set XLINK_BACKUP_TG_TOKEN + XLINK_BACKUP_TG_CHAT in .env
EOF
}

CMD="${1:-help}"; shift 2>/dev/null || true

VERSION=""; MODE_ARG=""
_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --version=*) VERSION="${1#*=}"; shift ;;
    build|pull) MODE_ARG="$1"; shift ;;
    *) _args+=("$1"); shift ;;
  esac
done
set -- "${_args[@]}"

case "$CMD" in
  install)   cmd_install "${MODE_ARG:-pull}" ;;
  update)    cmd_update ;;
  backup-service) cmd_backup_service "${1:-6}" ;;
  up)        need_root; compose up -d && ok "up" ;;
  down)      need_root; compose down && ok "down" ;;
  restart)   need_root; compose restart && ok "restarted" ;;
  status)    compose ps ;;
  logs)      compose logs -f "${1:-}" ;;
  backup)    need_root; do_backup ;;
  cli)       compose exec -T api python -m app.cli.main "$@" ;;
  edit)      need_root; "${EDITOR:-nano}" "$APP_DIR/.env" ;;
  uninstall) cmd_uninstall ;;
  -h|--help|help) usage ;;
  *) die "unknown command '$CMD' — try 'xlink help'" ;;
esac
