#!/usr/bin/env bash
# XLink node installer — run ON the node server (e.g. 185.130.47.51).
# Installs xray-core + the xlink agent as a systemd service pointed at the panel.
#
# Usage:
#   sudo XLINK_PANEL_URL=http://94.183.218.221:8000 \
#        XLINK_NODE_ID=<node-uuid-from-panel> \
#        XLINK_AGENT_TOKEN=<token-from-panel> \
#        bash install-remote.sh
set -euo pipefail

PANEL_URL="${XLINK_PANEL_URL:?set XLINK_PANEL_URL (e.g. http://94.183.218.221:8000)}"
NODE_ID="${XLINK_NODE_ID:?set XLINK_NODE_ID (create the node in the panel first)}"
AGENT_TOKEN="${XLINK_AGENT_TOKEN:?set XLINK_AGENT_TOKEN (provision it in the panel)}"
XRAY_VERSION="${XRAY_VERSION:-v25.3.6}"
INTERVAL="${XLINK_INTERVAL:-30}"

echo "[xlink] installing dependencies..."
if command -v apt-get >/dev/null; then
  apt-get update -y
  apt-get install -y --no-install-recommends curl unzip ca-certificates python3 procps
fi

echo "[xlink] installing xray ${XRAY_VERSION}..."
mkdir -p /usr/local/bin /usr/local/etc/xray /var/log/xray
curl -fsSL -o /tmp/xray.zip \
  "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-64.zip"
unzip -o /tmp/xray.zip -d /usr/local/bin xray
chmod +x /usr/local/bin/xray
rm -f /tmp/xray.zip

echo "[xlink] installing agent..."
install -m 0755 "$(dirname "$0")/xlink-agent.py" /opt/xlink-agent.py

# Minimal bootstrap xray config so the stats API is up before first sync.
if [ ! -s /usr/local/etc/xray/config.json ]; then
  cat > /usr/local/etc/xray/config.json <<'JSON'
{
  "log": { "loglevel": "warning", "error": "/var/log/xray/error.log" },
  "stats": {},
  "api": { "tag": "api", "services": ["StatsService"] },
  "policy": { "levels": { "0": { "statsUserUplink": true, "statsUserDownlink": true } },
              "system": { "statsInboundUplink": true, "statsInboundDownlink": true } },
  "inbounds": [ { "tag": "api", "listen": "127.0.0.1", "port": 10085,
    "protocol": "dokodemo-door", "settings": { "address": "127.0.0.1" } } ],
  "outbounds": [ { "protocol": "freedom" } ]
}
JSON
fi

echo "[xlink] writing systemd units..."
cat > /etc/systemd/system/xray.service <<'UNIT'
[Unit]
Description=Xray Service
After=network.target

[Service]
ExecStart=/usr/local/bin/xray run -c /usr/local/etc/xray/config.json
Restart=always
RestartSec=2
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/xlink-agent.service <<UNIT
[Unit]
Description=XLink Node Agent
After=network.target xray.service

[Service]
Environment=XLINK_PANEL_URL=${PANEL_URL}
Environment=XLINK_NODE_ID=${NODE_ID}
Environment=XLINK_AGENT_TOKEN=${AGENT_TOKEN}
Environment=XLINK_INTERVAL=${INTERVAL}
Environment=XLINK_XRAY_BIN=/usr/local/bin/xray
Environment=XLINK_XRAY_CONFIG=/usr/local/etc/xray/config.json
Environment="XLINK_XRAY_RELOAD=systemctl restart xray"
Environment=XLINK_XRAY_API=127.0.0.1:10085
Environment=XLINK_XRAY_SERVICE=xray
ExecStart=/usr/bin/python3 /opt/xlink-agent.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now xray.service
systemctl enable --now xlink-agent.service

echo "[xlink] done. check: journalctl -u xlink-agent -f"
