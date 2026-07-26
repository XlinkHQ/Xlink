"use client";

import { ChevronDown, ChevronRight, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { type Branding, getBranding, onBrandingChange } from "@/lib/branding";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { NAV_GROUPS, type NavGroup } from "./nav";

export function Sidebar({
  active,
  onSelect,
  onClose,
  open = false,
}: {
  active: string;
  onSelect: (key: string) => void;
  onClose?: () => void;
  open?: boolean;
}) {
  const t = useT();
  const [brand, setBrand] = useState<Branding>(getBranding);
  useEffect(() => onBrandingChange(() => setBrand(getBranding())), []);

  return (
    <aside className={cn("warp-sb", open && "is-open")}>
      <div className="warp-sb-inner">
        <div className="warp-sb-top">
          <img src={brand.logo} alt={brand.name} className="warp-sb-logo" draggable={false} />
          {onClose ? (
            <button
              type="button"
              className="warp-sb-collapse"
              aria-label={t("sidebar.collapse")}
              title={t("sidebar.collapse")}
              onClick={onClose}
            >
              <Menu size={20} strokeWidth={2} aria-hidden />
            </button>
          ) : null}
        </div>

        <nav className="warp-sb-groups">
          {NAV_GROUPS.map((group, i) => (
            <SidebarGroup
              key={group.title ?? `g${i}`}
              group={group}
              active={active}
              onSelect={onSelect}
            />
          ))}
        </nav>
      </div>
    </aside>
  );
}

function SidebarGroup({
  group,
  active,
  onSelect,
}: {
  group: NavGroup;
  active: string;
  onSelect: (key: string) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="warp-nav-group">
      {group.title ? (
        <button
          type="button"
          className="warp-nav-track"
          aria-expanded={open}
          onClick={() => setOpen((s) => !s)}
        >
          {open ? (
            <ChevronDown size={20} strokeWidth={2} aria-hidden />
          ) : (
            <ChevronRight size={20} strokeWidth={2} aria-hidden />
          )}
          <span>{group.title}</span>
        </button>
      ) : null}
      {open ? (
        <div className="warp-nav-items">
          {group.items.map((item) => {
            const Icon = item.icon;
            const isActive = item.key === active;
            return (
              <button
                key={item.key}
                type="button"
                title={item.label}
                data-status={isActive ? "active" : undefined}
                onClick={() => onSelect(item.key)}
                className="warp-nav-item"
              >
                <span className="warp-nav-ico" aria-hidden>
                  <Icon size={20} />
                </span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
