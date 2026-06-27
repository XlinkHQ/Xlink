"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { setTheme, useTheme } from "@/lib/theme";
import { LogoutIcon, MoonIcon, NAV_GROUPS, SearchIcon, SunIcon } from "./nav";

export function Sidebar({
  active,
  onSelect,
  onLogout,
  onSearch,
  identity = "xlink.local",
  open = false,
}: {
  active: string;
  onSelect: (key: string) => void;
  onLogout?: () => void;
  onSearch?: () => void;
  identity?: string;
  open?: boolean;
}) {
  const theme = useTheme();
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const profileName = identity || "xlink.local";
  const initials = profileName
    .split(/[.\s@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "XL";
  return (
    <aside className={cn("warp-sb", open && "is-open")}>
      <div className="warp-sb-inner">
        <ul className="warp-sb-nav">
          <div className="warp-sb-head">
            <div className="warp-sb-head-id">
              <span className="warp-sb-head-avatar">{initials}</span>
              <span className="warp-sb-head-name">{profileName}</span>
            </div>
            <button
              type="button"
              className="warp-sb-head-search"
              onClick={onSearch}
              title="Search  ⌘K"
              aria-label="Search"
            >
              <SearchIcon size={16} aria-hidden />
            </button>
          </div>
          {NAV_GROUPS.map((group, groupIndex) => {
            const groupKey = group.title ?? `root-${groupIndex}`;
            const isCollapsed = Boolean(collapsedGroups[groupKey]);
            return (
              <li
                className={cn("warp-sb-group", isCollapsed && "is-collapsed")}
                key={groupKey}
              >
                {group.title ? (
                  <button
                    type="button"
                    className="warp-sb-group-title"
                    aria-expanded={!isCollapsed}
                    onClick={() =>
                      setCollapsedGroups((current) => ({
                        ...current,
                        [groupKey]: !current[groupKey],
                      }))
                    }
                  >
                    <span>{group.title}</span>
                    <svg
                      className="warp-sb-collapse-ico"
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      role="img"
                      focusable="false"
                      aria-hidden="true"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="currentColor"
                    >
                      <path d="M7.002 10.624A.5.5 0 0 1 6.25 10.192V5.808a.5.5 0 0 1 .752-.432l3.758 2.192a.5.5 0 0 1 0 .864l-3.758 2.192Z" />
                    </svg>
                  </button>
                ) : null}
                <div className="warp-sb-group-items">
                  {group.items.map((item) => {
                    const isActive = item.key === active;
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        title={item.label}
                        onClick={() => onSelect(item.key)}
                        className={cn("warp-sb-item", isActive && "warp-sb-active")}
                      >
                        <Icon className="warp-sb-ico" aria-hidden />
                        <span className="warp-sb-label">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ul>

        <div className="warp-sb-footer">
          <div className="warp-tab-dark-light">
            <button
              type="button"
              title="Switch Light Mode"
              className={theme !== "dark" ? "is-active" : ""}
              onClick={() => setTheme("light")}
            >
              <SunIcon size={14} aria-hidden />
            </button>
            <button
              type="button"
              title="Switch Dark Mode"
              className={theme === "dark" ? "is-active" : ""}
              onClick={() => setTheme("dark")}
            >
              <MoonIcon size={14} aria-hidden />
            </button>
          </div>
          {onLogout && (
            <button
              type="button"
              title="Logout"
              onClick={() => onLogout()}
              className="warp-sb-item"
            >
              <LogoutIcon className="warp-sb-ico" size={18} aria-hidden />
              <span className="warp-sb-label">Logout</span>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
