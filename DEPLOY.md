# XLink deploy

## Panel server (94.183.218.221)

1. Copy this folder to the server, then:

   ```bash
   cd xlink
   cp deploy.env.production .env
   docker compose build
   docker compose up -d
   ```

2. Wait for health, then open the panel:

   `http://94.183.218.221:3000`

   Login: `admin` / (the password in `deploy.env.production`).

3. Open the firewall: 3000 (web), 8000 (api — nodes connect here).

## Node server (185.130.47.51)

1. In the panel: Nodes → add a node (host `185.130.47.51`, port 443),
   then provision its **agent token**. Copy the node id + token.

2. Copy the `node-agent/` folder to the node server, then:

   ```bash
   cd node-agent
   sudo XLINK_PANEL_URL=http://94.183.218.221:8000 \
        XLINK_NODE_ID=<node-uuid> \
        XLINK_AGENT_TOKEN=<token> \
        bash install-remote.sh
   ```

3. Verify: `journalctl -u xlink-agent -f` — should show `pulled config`.
   The node goes `active` in the panel within ~30s.

## Notes

- API port 8000 must be reachable from the node server.
- For TLS / a domain, put a reverse proxy (caddy/nginx) in front of web:3000 and api:8000.
- Secrets live in `.env` — keep it off git.
