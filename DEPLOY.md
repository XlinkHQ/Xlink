# Deploying XLink

There are two machines: the **panel server** (runs the web console, API, Postgres,
Redis) and one or more **node servers** (run the VPN cores and the pull-based
agent). Nodes connect out to the panel's API — the panel never needs to reach
into a node.

## Panel server

The one-command installer does everything (Docker, clone, secret generation,
build/pull, migrations, start):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Theok09/Xlink/main/scripts/install.sh)
```

When it finishes it prints the panel URL and a one-time admin password. Re-run it
any time to update in place (your `.env` is preserved). Append `--build` to build
the images locally instead of pulling.

Prefer to drive it yourself? Clone the repo and use the manager script:

```bash
git clone https://github.com/Theok09/Xlink.git /opt/xlink
cd /opt/xlink
./xlink.sh install          # generate .env + secrets, pull, migrate, start
```

Open the firewall for the web port (default `3000`) and the API port
(default `8000` — nodes connect here). For a domain + automatic HTTPS, set the
domain in `.env` and the stack brings up the bundled Caddy edge proxy (the `tls`
compose profile); otherwise it serves plain ports for local/IP use.

## Node server

1. In the panel: **Nodes → add a node** (its public host + core port), then
   provision its **agent token**. Copy the node id and token.

2. On the node server, run the agent installer with the values from step 1:

   ```bash
   curl -fsSL https://<panel-host>:8000/agent/install.sh \
     | sudo -E bash -s https://<panel-host> <node-id> <agent-token>
   ```

   Restrict the cores it installs with `--cores=xray,wireguard` (default: all).

3. Verify the agent is talking to the panel:

   ```bash
   journalctl -u xlink-agent -f      # expect "pulled config" every cycle
   ```

   The node flips to **active** in the panel within ~30s.

## Notes

- The API port must be reachable from every node server.
- Secrets live in `.env` on the panel server — it is git-ignored; never commit it.
- Back up the database regularly: `xlink backup`.
- `./xlink.sh` is the single install/update entrypoint on the panel; the curl
  one-liner above is just a bootstrap that hands off to it.
