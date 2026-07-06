#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${1:-10}"
SERVICE="xlink-agent"
OVERRIDE_DIR="/etc/systemd/system/${SERVICE}.service.d"

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash set-interval.sh [seconds]"
  exit 1
fi

echo "[set-interval] setting XLINK_INTERVAL=${INTERVAL}s for ${SERVICE}"

mkdir -p "$OVERRIDE_DIR"
cat > "${OVERRIDE_DIR}/override.conf" <<EOF
[Service]
Environment=XLINK_INTERVAL=${INTERVAL}
EOF

systemctl daemon-reload
systemctl restart "$SERVICE"

echo "[set-interval] applied. current status:"
systemctl show "$SERVICE" -p Environment | tr ' ' '\n' | grep -i interval || true
echo "[set-interval] tail logs:"
journalctl -u "$SERVICE" -n 5 --no-pager
