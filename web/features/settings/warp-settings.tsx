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
import { useT } from "@/lib/i18n";
import { SettingsRow, useRegisterSave } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

const EMPTY: WarpSettingsRead = {
  warp_enabled: false,
  warp_private_key: "",
  warp_public_key: "",
  warp_address: "",
  warp_endpoint: "engage.cloudflareclient.com:2408",
  warp_reserved: "",
};

export function WarpSettingsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["warp-settings"], queryFn: () => getWarpSettings() });
  const [form, setForm] = useState<WarpSettingsRead>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
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
      toast("success", t("warp.saved"));
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  }, busy);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Globe}
        title={t("warp.title")}
        description={t("warp.desc")}
      >
        <SettingsRow label={t("warp.enable")} hint={t("warp.enableHint")}>
          <label className="warp-switch">
            <input type="checkbox" checked={form.warp_enabled} onChange={(e) => set("warp_enabled", e.target.checked)} />
            <span className="warp-switch-track" />
          </label>
        </SettingsRow>
        <SettingsRow label={t("warp.privateKey")} hint={t("warp.privateKeyHint")}>
          <input className="warp-set-input warp-set-input-wide" value={form.warp_private_key} onChange={(e) => set("warp_private_key", e.target.value)} placeholder={t("warp.base64Placeholder")} />
        </SettingsRow>
        <SettingsRow label={t("warp.peerPublicKey")} hint={t("warp.peerPublicKeyHint")}>
          <input className="warp-set-input warp-set-input-wide" value={form.warp_public_key} onChange={(e) => set("warp_public_key", e.target.value)} placeholder={t("warp.base64Placeholder")} />
        </SettingsRow>
        <SettingsRow label={t("warp.addresses")} hint={t("warp.addressesHint")}>
          <input className="warp-set-input warp-set-input-wide" value={form.warp_address} onChange={(e) => set("warp_address", e.target.value)} placeholder="172.16.0.2/32" />
        </SettingsRow>
        <SettingsRow label={t("warp.endpoint")} hint={t("warp.endpointHint")}>
          <input className="warp-set-input warp-set-input-wide" value={form.warp_endpoint} onChange={(e) => set("warp_endpoint", e.target.value)} />
        </SettingsRow>
        <SettingsRow label={t("warp.reserved")} hint={t("warp.reservedHint")}>
          <input className="warp-set-input" value={form.warp_reserved} onChange={(e) => set("warp_reserved", e.target.value)} placeholder={t("warp.optionalPlaceholder")} />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
