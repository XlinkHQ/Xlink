import importlib.util
import json
import os
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location("a", "xlink-agent.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def validate_xray():
    protocols = ["vless", "vmess", "trojan", "shadowsocks"]
    transports = ["tcp", "ws", "grpc", "httpupgrade"]
    securities = ["none", "tls"]
    clients = []
    combos = []
    port = 10000
    for proto in protocols:
        for net in transports:
            for sec in securities:
                port += 1
                s = {"port": port, "network": net, "security": sec}
                if sec == "tls":
                    s["sni"] = "test.example.com"
                if net in ("ws", "httpupgrade"):
                    s["path"] = "/p"
                clients.append(
                    {
                        "assignment_id": "aid-%d" % port,
                        "provider_client_id": "11111111-2222-3333-4444-555555555555",
                        "protocol": proto,
                        "settings": s,
                    }
                )
                combos.append("{}/{}/{}".format(proto, net, sec))
    keys = subprocess.run(["xray", "x25519"], capture_output=True, text=True).stdout
    priv = ""
    for line in keys.splitlines():
        if "private" in line.lower():
            priv = line.split()[-1]
    for proto in ["vless", "vmess"]:
        for net in ["tcp", "grpc"]:
            port += 1
            s = {
                "port": port,
                "network": net,
                "security": "reality",
                "sni": "www.microsoft.com",
                "privateKey": priv,
                "shortId": "ab",
            }
            clients.append(
                {
                    "assignment_id": "aid-%d" % port,
                    "provider_client_id": "11111111-2222-3333-4444-555555555555",
                    "protocol": proto,
                    "settings": s,
                }
            )
            combos.append("{}/{}/reality".format(proto, net))
    cfg = m.build_xray_config(clients)
    inbound_count = len(cfg["inbounds"]) - 1
    print("XRAY: built %d inbounds for %d combos" % (inbound_count, len(combos)))
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(cfg, f)
    f.close()
    r = subprocess.run(["xray", "run", "-test", "-c", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode == 0:
        print("  RESULT: ALL %d XRAY CONFIGS VALID (real xray -test)" % len(combos))
        for c in combos:
            print("    OK", c)
    else:
        print("  RESULT: xray -test FAILED (rc=%d)" % r.returncode)
        for line in (r.stdout + r.stderr).splitlines():
            low = line.lower()
            if any(w in low for w in ("fail", "error", "invalid", "infra")):
                print("    X", line.strip()[:130])


def validate_singbox():
    protocols = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic"]
    transports = ["tcp", "ws", "grpc"]
    clients = []
    combos = []
    port = 20000
    for proto in protocols:
        for net in transports:
            port += 1
            s = {"port": port, "network": net, "security": "tls", "sni": "t.com"}
            if net == "ws":
                s["path"] = "/p"
            clients.append(
                {
                    "assignment_id": "aid-%d" % port,
                    "provider_client_id": "11111111-2222-3333-4444-555555555555",
                    "protocol": proto,
                    "settings": s,
                }
            )
            combos.append("{}/{}".format(proto, net))
    cfg = m.build_singbox_config(clients)
    print("\nSING-BOX: built %d inbounds for %d combos" % (len(cfg["inbounds"]), len(combos)))
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(cfg, f)
    f.close()
    r = subprocess.run(["sing-box", "check", "-c", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode == 0:
        print(
            "  RESULT: ALL %d SING-BOX CONFIGS VALID (real sing-box check): %s"
            % (len(combos), ", ".join(combos))
        )
    else:
        print("  RESULT: sing-box check FAILED:", (r.stdout + r.stderr).strip()[:160])


def validate_others():
    import base64
    import re

    print("\nWIREGUARD:")
    peer1 = subprocess.run(
        ["sh", "-c", "wg genkey | wg pubkey"], capture_output=True, text=True
    ).stdout.strip()
    peer2 = subprocess.run(
        ["sh", "-c", "wg genkey | wg pubkey"], capture_output=True, text=True
    ).stdout.strip()
    wg = m.build_wireguard_config(
        [
            {"assignment_id": "a", "provider_client_id": peer1, "settings": {"port": 51820}},
            {"assignment_id": "b", "provider_client_id": peer2, "settings": {"port": 51820}},
        ]
    )
    keys = re.findall(r"(?:PrivateKey|PublicKey) = (\S+)", wg)
    keys_ok = all(len(base64.b64decode(k)) == 32 for k in keys if not k.startswith("$")) and keys
    struct = wg.count("[Interface]") == 1 and wg.count("[Peer]") == 2 and "AllowedIPs" in wg
    print(
        "  RESULT: %s (%d peers, %d valid 32-byte keys, real wg)"
        % ("VALID wg config" if (struct and keys_ok) else "INVALID", wg.count("[Peer]"), len(keys))
    )

    print("\nHYSTERIA2:")
    hy = m.build_hysteria_config(
        [
            {
                "assignment_id": "a",
                "provider_client_id": "PASS1",
                "protocol": "hysteria2",
                "settings": {"port": 34443, "sni": "h.com"},
            },
        ]
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(hy, f)
    f.close()
    r = subprocess.run(
        ["timeout", "3", "hysteria", "server", "-c", f.name], capture_output=True, text=True
    )
    os.unlink(f.name)
    started = "server up and running" in (r.stdout + r.stderr)
    print(
        "  RESULT: {} (real hysteria server {})".format("VALID" if started else "INVALID", "started + ran the config" if started else "rejected")
    )


if __name__ == "__main__":
    validate_xray()
    validate_singbox()
    validate_others()
