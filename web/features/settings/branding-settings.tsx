"use client";

import { Palette } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { getBranding, setBranding } from "@/lib/branding";
import { useT } from "@/lib/i18n";
import { SettingsRow, useRegisterSave } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

export function BrandingSettingsScreen() {
  const t = useT();
  const initial = getBranding();
  const [name, setName] = useState(initial.name);
  const [logo, setLogo] = useState(initial.logo);

  const save = () => {
    setBranding({ name: name.trim() || "XLink", logo: logo.trim() || "/xlink-logo.png" });
    toast("success", t("branding.saved"));
  };
  useRegisterSave(save);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Palette}
        title={t("branding.title")}
        description={t("branding.desc")}
      >
        <SettingsRow label={t("branding.panelName")} hint={t("branding.panelNameHint")}>
          <input className="warp-set-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="XLink" />
        </SettingsRow>
        <SettingsRow label={t("branding.logoUrl")} hint={t("branding.logoUrlHint")}>
          <input className="warp-set-input" value={logo} onChange={(e) => setLogo(e.target.value)} placeholder="https://…/logo.svg" />
        </SettingsRow>
        <SettingsRow label={t("branding.preview")} hint={t("branding.previewHint")}>
          {}
          <span
            className="inline-flex items-center gap-2"
            style={{
              padding: "8px 12px",
              borderRadius: "var(--radius-md)",
              background: "#ffffff",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <img src={logo || "/xlink-logo.png"} alt="" style={{ height: 22 }} />
            <span className="text-sm" style={{ color: "#303031" }}>
              {name || "XLink"}
            </span>
          </span>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
