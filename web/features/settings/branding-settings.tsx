"use client";

import { Palette } from "lucide-react";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { getBranding, setBranding } from "@/lib/branding";
import { SettingsRow, useRegisterSave } from "./settings";
import { SettingsSection } from "@/components/console/screens/settings-kit";

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
          {/* Logos are often dark-on-transparent wordmarks that vanish on the
              dark theme, so preview them on a fixed light chip that keeps them
              legible in both themes. */}
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
