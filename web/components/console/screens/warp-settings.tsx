"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import {
  ApiError,
  getWarpSettings,
  updateWarpSettings,
  type WarpSettingsRead,
} from "@/lib/api";
import { SettingsRow, useRegisterSave } from "./settings";
import { SettingsSection } from "./settings-kit";

const EMPTY: WarpSettingsRead = {
  warp_enabled: false,
  warp_private_key: "",
  warp_public_key: "",
  warp_address: "",
  warp_endpoint: "engage.cloudflareclient.com:2408",
  warp_reserved: "",
};

export function WarpSettingsScreen() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["warp-settings"], queryFn: () => getWarpSettings() });
  const [form, setForm] = useState<WarpSettingsRead>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // One-time latch so a background refetch can't clobber in-progress edits.
    if (q.data && !loaded) {
      setForm(q.data);
      setLoaded(true);
    }
  }, [q.data, loaded]);

  const set = <K extends keyof WarpSettingsRead>(k: K, v: WarpSettingsRead[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  useRegisterSave(async () => {
    setBusy(true);
    try {
      const saved = await updateWarpSettings(form);
      setForm(saved);
      qc.invalidateQueries({ queryKey: ["warp-settings"] });
      toast("success", "WARP settings saved — nodes apply on next sync.");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }, busy);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Globe}
        title="Cloudflare WARP"
        description="Route selected traffic through a WARP (WireGuard) outbound. Add a routing rule with outbound “warp” to send matching domains/IPs through it."
      >
        <SettingsRow label="Enable WARP outbound" hint="Injects a WARP wireguard outbound into the Xray config.">
          <label className="warp-switch">
            <input type="checkbox" checked={form.warp_enabled} onChange={(e) => set("warp_enabled", e.target.checked)} />
            <span className="warp-switch-track" />
          </label>
        </SettingsRow>
        <SettingsRow label="Private key" hint="WARP WireGuard secret key (from wgcf / warp-cli).">
          <input className="warp-set-input warp-set-input-wide" value={form.warp_private_key} onChange={(e) => set("warp_private_key", e.target.value)} placeholder="base64 key" />
        </SettingsRow>
        <SettingsRow label="Peer public key" hint="Cloudflare endpoint public key.">
          <input className="warp-set-input warp-set-input-wide" value={form.warp_public_key} onChange={(e) => set("warp_public_key", e.target.value)} placeholder="base64 key" />
        </SettingsRow>
        <SettingsRow label="Address(es)" hint="Comma-separated interface addresses (e.g. 172.16.0.2/32, 2606:…/128).">
          <input className="warp-set-input warp-set-input-wide" value={form.warp_address} onChange={(e) => set("warp_address", e.target.value)} placeholder="172.16.0.2/32" />
        </SettingsRow>
        <SettingsRow label="Endpoint" hint="WARP endpoint host:port.">
          <input className="warp-set-input warp-set-input-wide" value={form.warp_endpoint} onChange={(e) => set("warp_endpoint", e.target.value)} />
        </SettingsRow>
        <SettingsRow label="Reserved" hint="Optional comma-separated reserved bytes (e.g. 12,34,56).">
          <input className="warp-set-input" value={form.warp_reserved} onChange={(e) => set("warp_reserved", e.target.value)} placeholder="optional" />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
