"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { setTheme, useTheme } from "@/lib/theme";
import { NAV_GROUPS, SearchIcon } from "./nav";

const SB_MIN = 200;
const SB_MAX = 360;
const SB_DEFAULT = 260;
const SB_COLLAPSE_AT = 168;

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
  const [width, setWidth] = useState(SB_DEFAULT);
  const [collapsed, setCollapsed] = useState(false);
  const [acctOpen, setAcctOpen] = useState(false);
  const dragging = useRef(false);

  useEffect(() => {
    const w = Number(localStorage.getItem("xlink-sb-width"));
    if (w >= SB_MIN && w <= SB_MAX) setWidth(w);
    setCollapsed(localStorage.getItem("xlink-sb-collapsed") === "1");
  }, []);

  const onDragStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragging.current = true;
    const move = (ev: PointerEvent) => {
      if (!dragging.current) return;
      const w = ev.clientX;
      if (w < SB_COLLAPSE_AT) {
        setCollapsed(true);
        localStorage.setItem("xlink-sb-collapsed", "1");
        dragging.current = false;
        cleanup();
        return;
      }
      const clamped = Math.max(SB_MIN, Math.min(SB_MAX, w));
      setWidth(clamped);
      localStorage.setItem("xlink-sb-width", String(clamped));
    };
    const up = () => { dragging.current = false; cleanup(); };
    const cleanup = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
  }, []);

  const reopen = () => {
    setCollapsed(false);
    localStorage.setItem("xlink-sb-collapsed", "0");
  };

  const profileName = identity || "xlink.local";
  const initials = profileName
    .split(/[.\s@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "XL";

  if (collapsed) {
    return (
      <button
        type="button"
        className="warp-sb-reopen"
        onClick={reopen}
        title="Open sidebar"
        aria-label="Open sidebar"
      >
        <SearchIcon size={16} aria-hidden />
      </button>
    );
  }

  return (
    <aside className={cn("warp-sb", open && "is-open")} style={{ width }}>
      <div
        className="warp-sb-resize"
        onPointerDown={onDragStart}
        role="separator"
        aria-orientation="vertical"
        title="Drag to resize · drag left to hide"
      />
      <div className="warp-sb-inner">
        <ul className="warp-sb-nav">
          <div className="warp-sb-head">
            <button
              type="button"
              className="warp-sb-head-id"
              onClick={() => setAcctOpen((o) => !o)}
              aria-haspopup="menu"
              aria-expanded={acctOpen}
              title={profileName}
            >
              <span className="warp-sb-head-avatar">{initials}</span>
              <span className="warp-sb-head-name">{profileName}</span>
            </button>
            <button
              type="button"
              className="warp-sb-head-search"
              onClick={onSearch}
              title="Search  ⌘K"
              aria-label="Search"
            >
              <SearchIcon size={16} aria-hidden />
            </button>
            {acctOpen ? (
              <>
                <button
                  type="button"
                  className="warp-sb-acct-scrim"
                  aria-hidden
                  tabIndex={-1}
                  onClick={() => setAcctOpen(false)}
                />
                <div className="warp-sb-acct-menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    className="warp-menu-item"
                    onClick={() => { setAcctOpen(false); onSelect("Settings"); }}
                  >
                    <span>Settings</span>
                    <span className="warp-sb-acct-kbd"><kbd>G</kbd><span>then</span><kbd>S</kbd></span>
                  </button>
                  <div className="warp-sb-acct-sep" role="separator" />
                  <button
                    type="button"
                    role="menuitem"
                    className="warp-menu-item"
                    onClick={() => { setTheme(theme === "dark" ? "light" : "dark"); }}
                  >
                    <span>{theme === "dark" ? "Light theme" : "Dark theme"}</span>
                  </button>
                  {onLogout ? (
                    <>
                      <div className="warp-sb-acct-sep" role="separator" />
                      <button
                        type="button"
                        role="menuitem"
                        className="warp-menu-item is-danger"
                        onClick={() => { setAcctOpen(false); onLogout(); }}
                      >
                        <span>Log out</span>
                        <span className="warp-sb-acct-kbd"><kbd>⌥</kbd><kbd>⇧</kbd><kbd>Q</kbd></span>
                      </button>
                    </>
                  ) : null}
                </div>
              </>
            ) : null}
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
      </div>
    </aside>
  );
}
