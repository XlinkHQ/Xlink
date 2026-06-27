# XLink Backend Audit Report

## 1. Critical / High Bugs

### WireGuard

**[CRITICAL] WireGuard private key defaults to UUID, not a valid key**
`app/subscription/formats/wireguard.py:39`
When `privateKey` credential is missing, code falls back to `config.client_id` (a 36-char UUID). WireGuard needs a 44-char base64 32-byte key, so every such config silently fails to connect with an opaque client error.
Fix: validate presence and raise early — `if not private_key: raise FormatRenderError('Missing private key', code='subscription_missing_fields', details={'missing':['privateKey']})`. Do not synthesize a fake key.

**[CRITICAL] Node-agent reload hardcodes `10.8.0.0/24` subnet**
`node-agent/xlink-agent.py:447-448`
The config builder derives the subnet dynamically from the address (`:349`) and bakes it into PostUp/PostDown, but the reload command's iptables rule is hardcoded to `10.8.0.0/24`. Any non-default address (e.g. `192.168.100.1/24`) leaves orphaned rules and breaks masquerade → no connectivity.
Fix: derive the subnet from the config (return it from `build_wireguard_config`, or substitute an `XLINK_WG_SUBNET` placeholder at runtime) and use it in the reload rule.

**[HIGH] Address allocation collision — no overflow / exhaustion check**
`app/services/client_assignment_service.py:353-355`
Loop condition is `while octet in used and octet < 255`, so it exits at 255 without testing whether 255 is already taken. With octets 2–254 exhausted, it hands out 255 even if assigned → duplicate addresses (credentials JSON has no unique constraint). No error on pool exhaustion either.
Fix: `while octet in used and octet < 256:` then `if octet >= 255: raise ConflictError('All WireGuard addresses exhausted for this node')`.

**[MEDIUM] Subnet extraction breaks on non-/24 and IPv6**
`node-agent/xlink-agent.py:349`
`addr.rsplit(".",1)[0] + ".0/24"` assumes IPv4 /24. `fd00::1/64` → `fd00::1/64.0/24` (garbage into iptables). Settings are unvalidated `dict[str, Any]`.
Fix: `ipaddress.ip_network(addr, strict=False)`; validate IPv4 and reject/handle other prefixes.

**[MEDIUM] Unvalidated `int()` on MTU / PersistentKeepalive**
`app/subscription/formats/wireguard.py:34,50`
`int()` on user-controlled settings crashes render with `ValueError` on non-numeric input; no range validation either.
Fix: wrap in try/except → `FormatRenderError`; enforce MTU 1280–65535 and keepalive 1–65.

### Other Protocols (Xray / sing-box / Hysteria)

**[HIGH] VLESS/Trojan REALITY fingerprint defaults to empty string**
`app/subscription/formats/vless.py:41`
`params["fp"] = str(setting(config,"fingerprint",""))` — empty `fp` fails REALITY client validation. `xray_json.py:64` and `stream.py:114` correctly default to `"chrome"`.
Fix: default to `"chrome"`.

**[HIGH] sing-box REALITY emits empty `public_key` / `short_id`**
`app/subscription/formats/singbox.py:22-26`
Missing `publicKey`/`shortId` → reality block with `""` values; sing-box rejects/fails to connect. Unlike WireGuard format, no required-field validation.
Fix: require both non-empty or raise `FormatRenderError`.

**[HIGH] Hysteria2 URI hardcodes `insecure=1`**
`app/subscription/formats/hysteria2.py:22`
Ignores `allowInsecure`; always disables TLS verification, overriding user security intent. `tuic.py:30` does it correctly.
Fix: `insecure = "1" if setting(config,"allowInsecure") else ""`.

**[HIGH] Blocking file I/O in async context stalls event loop**
`app/providers/base/store.py:57-67`
`JsonClientStore._save()` (open/flock/json.dump/fsync/replace) runs synchronously from async `create_client`/`update_client`/`delete_client`, starving the loop under concurrency.
Fix: `await asyncio.to_thread(self._save)` or async I/O / batched writes.

**[MEDIUM] sing-box VLESS `flow` always emitted as empty string**
`app/subscription/formats/singbox.py:88` — set `flow` only when truthy (clash.py:76-78 is the reference).

**[MEDIUM] sing-box gRPC `service_name` emitted empty** — `singbox.py:35`, same pattern.

**[MEDIUM] Hysteria `update_client` can't add obfs** — `app/providers/hysteria/provider.py:71-86`; obfs_password generation lives only in the create (`else`) branch, never runs on update.

**[MEDIUM] Circuit breaker never resets after timeout** — `app/providers/xray/gateway.py:114-123`; a failed half-open request restarts the full cooldown, prolonging the failure loop.

### Enforcement / Accounting

**[CRITICAL] Data-limit uses MAX instead of SUM across assignments**
`node-agent/xlink-agent.py:873`
`user_base[uid] = max(...)` instead of summing per-assignment `used_bytes`. A user with usage `[80,20]` is counted as 80, not 100 — multi-node users can blow past data limits.
Fix: `user_base[uid] = user_base.get(uid,0) + int(c.get("used_bytes",0) or 0)`.

**[HIGH] IP device-limit disables ALL assignments, not just excess**
`app/agent/ip_limit.py:79-88`
Exceeding `device_limit` disables every active assignment instead of trimming to the limit. limit=2 + 3 devices → all 3 dropped.
Fix: sort assignments (oldest first), disable only enough to reach `device_limit`.

**[HIGH] Zero traffic-limit treated as unlimited (4 sites)**
`app/subscription/generator.py:92, 161, 162` (+ `_human` at :54)
`if limit` treats `0` as falsy, so a 0-byte quota shows `∞` (DATA_LEFT/DATA_LIMIT) and users over a 0 quota are marked Active instead of Limited.
Fix: use `if limit is not None` in each spot; have `_human(0)` return `"0 B"`.

## 2. Dead Code & Redundant Files

- **Triplicated SHA256 token hashing** — `app/api/v1/routers/api_keys.py:19-20`, `app/services/token_service.py:22-23`, `app/agent/heartbeat.py:17-18`. Same `sha256(token).hexdigest()` three times. Centralize one helper in `app/core/security.py`, import everywhere.
- **`__pycache__` in working tree** (252 dirs, not git-tracked) — clean: `find . -type d -name __pycache__ -exec rm -r {} +; find . -name '*.pyc' -delete`. Confirm `.gitignore` covers it.
- **Stale `.VSCodeCounter/` reports** — already deleted in git status; finalize the removal.
- Empty `__init__.py` (20 files) — harmless; leave as-is or add `__all__` to `app/services`. Low priority.

## 3. Marzban Feature Gaps

- **[HIGH] No UserTemplate / bulk provisioning** — `app/schemas/user.py:16`. Add `UserTemplate` model + `/users/from-template` that materializes a User from preset defaults via existing `UserService.create_user`. Biggest reseller workflow gap.
- **[MEDIUM] No bulk user actions** — `app/api/v1/routers/users.py`. Add `POST /users/bulk` (enable/disable/delete/reset_usage/extend_expiry/add_data) with filter or id-list, implemented as set-based UPDATE/DELETE.
- **[MEDIUM] Telegram is outbound-only** — `app/webhooks/dispatcher.py`. Optional opt-in bot worker (getUpdates) gated by admin-ID allowlist, mapped onto existing services.
- **[LOW] No per-node core version** — agent reports `agent_version` but not the data-plane engine (Xray/Hysteria) version. Add `core_kind`/`core_version` to Node + `NodeRead`, wire to `xray_releases`.
- **[LOW] No per-admin (reseller) quota enforcement** — `users_data_usage` is tracked but not enforced. Add admin-level `data_limit`/`expire` + scheduler check calling existing `disable_admin_users`.

## 4. Optimizations

- **[HIGH] N+1: profile.disable() fetches node per assignment** — `app/services/profile_service.py:113-117`. Batch via `get_many(node_ids)`.
- **[HIGH] N+1: sync_group() fetches profile per id** — `app/services/client_assignment_service.py:195-196`. Batch via `get_many(target_profile_ids)`.
- **[HIGH] O(n²): overrides_for_profiles double-scans rows** — `app/repositories/inbound_host.py:61-67`. Pre-build `by_profile` index + `universal` list once.
- **[MEDIUM] Sync I/O in async metrics endpoint** — `app/api/v1/routers/monitoring.py:244-245`. `anyio.to_thread.run_sync` + short TTL cache.
- **[MEDIUM] Sequential provider health checks** — `app/monitoring/metrics.py:26-38`. `asyncio.gather` them.
- **[MEDIUM] Cache invalidation collects all keys in memory** — `app/subscription/service.py:186-190`. Batch-delete via `scan_iter` in chunks of 1000.
- **[MEDIUM] generate_feed re-sums bytes every call** — `app/subscription/generator.py:134`. Precompute at fetch.
- **[LOW] Misleading async-without-await** — `generator.py:123,126`. Drop `async` or document.
- **[LOW] Silent ValidationError suppression** — `generator.py:140`. Log skipped sources.
- **[LOW] Type mismatch tuple→list** — `service.py:142`. Wrap in `tuple(...)`.
- **[LOW] Missing eager loading in user_service** — `user_service.py:58-69`. `selectinload(User.assignments)`.

## Action List (fix in this order)

1. **`node-agent/xlink-agent.py:873`** — MAX→SUM data-limit enforcement (revenue leak; users exceed quotas).
2. **`node-agent/xlink-agent.py:447-448`** — reload subnet hardcode (breaks all non-default WG nodes).
3. **`app/subscription/formats/wireguard.py:39`** — UUID-as-privateKey; fail loudly on missing key.
4. **`app/services/client_assignment_service.py:353-355`** — WG address collision/exhaustion guard.
5. **`app/agent/ip_limit.py:79-88`** — disable only excess devices, not all.
6. **`app/subscription/generator.py:92,161,162`** — zero-limit `is not None` fixes.
7. **`app/subscription/formats/hysteria2.py:22`** — honor `allowInsecure`.
8. **`vless.py:41` + `singbox.py:22-26,35,88`** — REALITY/empty-field defaults.
9. **`app/providers/base/store.py:57-67`** — offload blocking I/O to a thread.
10. **`wireguard.py:34,50` + `xlink-agent.py:349`** — MTU/keepalive validation + safe subnet parsing.
11. Optimizations (N+1s, O(n²)) then dead-code dedup, then Marzban gaps (UserTemplate first).