"use client";

import { Palette } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { getBranding, setBranding } from "@/lib/branding";
import { SettingsRow, useRegisterSave } from "./settings";
import { SettingsSection } from "./settings-kit";

export function BrandingSettingsScreen() {
  const initial = getBranding();
  const [name, setName] = useState(initial.name);
  const [logo, setLogo] = useState(initial.logo);

  const save = () => {
    setBranding({ name: name.trim() || "XLink", logo: logo.trim() || "/xlink-logo.png" });
    toast("success", "Branding saved.");
  };
  useRegisterSave(save);

  return (
    <div className="w-full">
      <SettingsSection
        icon={Palette}
        title="Branding"
        description="Customize the panel name, logo and colors."
      >
        <SettingsRow label="Panel name" hint="Shown on the sidebar and login screen.">
          <input className="warp-set-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="XLink" />
        </SettingsRow>
        <SettingsRow label="Logo URL" hint="An image URL (svg/png). Leave blank for the default.">
          <input className="warp-set-input" value={logo} onChange={(e) => setLogo(e.target.value)} placeholder="https://…/logo.svg" />
        </SettingsRow>
        <SettingsRow label="Preview" hint="Current logo + name.">
          <span className="flex items-center gap-2">
            <img src={logo || "/xlink-logo.png"} alt="" style={{ height: 22 }} />
            <span className="text-sm text-fg">{name || "XLink"}</span>
          </span>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
