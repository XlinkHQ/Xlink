"use client";

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * DefGuard-style "marked section" primitives for XLink settings.
 * Structure copied from DefGuard MarkedSection + MarkedSectionHeader + SectionMarker
 * (icon tile 32px accent-muted radius-full, icon 20px accent; title 16/600 fg-default,
 * description 14/400 fg-muted). Sizing/spacing resolved to px from DefGuard tokens.
 * lucide strokeWidth 1.8.
 */


export function SettingsSection({
  icon: Icon,
  title,
  description,
  divider = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  /** render a divider above this section (between groups) */
  divider?: boolean;
  children: ReactNode;
}) {
  return (
    <>
      {divider ? <div className="warp-ss-divider" /> : null}
      <section className="warp-ss-section">
        <span className="warp-ss-marker">
          <Icon size={20} strokeWidth={1.8} aria-hidden />
        </span>
        <div className="warp-ss-body">
          <div className="warp-ss-head">
            <h4 className="warp-ss-title">{title}</h4>
            {description ? <p className="warp-ss-desc">{description}</p> : null}
          </div>
          <div className="warp-ss-fields">{children}</div>
        </div>
      </section>
    </>
  );
}
