# XLink Node Agent

Connects a VPN node to the XLink panel using the **agent-pull** model: the node
makes only outbound HTTPS calls to the panel — no inbound port is exposed.

## 1. Create the node + token (in the panel)
Nodes → **Add node** → open it → **Generate agent token**. Copy the **Node ID**
and **Agent token** (the token is shown once).

## 2. One-line install (recommended)
On the node, as root:
```bash
PANEL_URL=https://panel.example.com NODE_ID=<uuid> AGENT_TOKEN=<token> \
  bash install.sh
```
This installs **Xray**, drops the agent in `/opt/xlink`, and registers a
`systemd` service that starts on boot. The node turns **active** in the panel
within a few seconds. Logs: `journalctl -u xlink-agent -f`.

### Manual install
```bash
scp xlink-agent.py root@YOUR_SERVER:/opt/xlink/xlink-agent.py
export XLINK_PANEL_URL=https://panel.example.com XLINK_NODE_ID=<id> XLINK_AGENT_TOKEN=<token>
python3 /opt/xlink/xlink-agent.py    # or use xlink-agent.service for systemd
```
Only the Python 3 standard library is required.

## Safe config apply
Every config change is applied **safely**: the agent writes a candidate file,
**validates** it with the core's own checker (`xray -test`, `sing-box check`),
backs up the live config, swaps the new one in atomically, and **rolls back** to
the previous config if the reload fails. A bad config never takes the node down.

## Notes
- `XLINK_PANEL_URL` must be a URL the **node** can reach (a public panel URL or a
  tunnel). `localhost` only works if the panel runs on the same box.
- The node shows **active** only while the agent is reporting. If it stops, the
  panel marks it **offline** after ~2 minutes (health check).
- `apply_config()` in `xlink-agent.py` is the integration point for writing the
  xray/sing-box config and reloading the core.
