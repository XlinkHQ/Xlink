"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, Menu, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { listNodes, onlineUsers, usersTotal } from "@/lib/api";
import { setTheme, useTheme } from "@/lib/theme";
import { DgDarkTheme, DgGlobe, DgLightTheme, DgUsers } from "./dg-icons";
import { isNodeOnline } from "@/lib/status";

function StatChip({
  icon,
  online,
  total,
  totalLabel,
}: {
  icon: React.ReactNode;
  online: number | null;
  total: number | null;
  totalLabel?: string;
}) {
  const known = online != null && total != null;
  const pct = known && total > 0 ? Math.min(100, (online / total) * 100) : 0;
  const critical = known && total > 0 && online / total >= 0.9;
  return (
    <span className="warp-topbar-stat">
      {icon}
      <span>{known ? `${online}/${totalLabel ?? total}` : "—/—"}</span>
      <span className={`warp-topbar-bar${critical ? " critical" : ""}`}>
        <span className="bar" style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

function TopBarStats() {
  const onlineQuery = useQuery({
    queryKey: ["topbar-online-users"],
    queryFn: () => onlineUsers(),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const usersQuery = useQuery({
    queryKey: ["topbar-users-total"],
    queryFn: () => usersTotal("user"),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });
  const nodesQuery = useQuery({
    queryKey: ["nodes"],
    queryFn: () => listNodes(),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  });

  const totalUsers = usersQuery.data ? usersQuery.data.meta.total : null;
  const onlineUsersCount = onlineQuery.data ? onlineQuery.data.user_ids.length : null;

  const nodeItems = nodesQuery.data?.items ?? null;
  const totalNodes = nodeItems ? nodeItems.length : null;
  const onlineNodes = nodeItems
    ? nodeItems.filter((n) => isNodeOnline(n.status)).length
    : null;

  return (
    <div className="warp-topbar-license">
      <StatChip
        icon={<DgUsers size={16} />}
        online={onlineUsersCount}
        total={totalUsers}
      />
      <StatChip
        icon={<DgGlobe size={16} />}
        online={onlineNodes}
        total={totalNodes}
      />
    </div>
  );
}

const PAGE_TITLES: Record<string, string> = {
  Overview: "Overview",
  Nodes: "Nodes",
  Profiles: "Hosts",
  Groups: "Services",
  Users: "Users",
  Admins: "Admins",
  Activity: "Activity log",
  ApiKeys: "API Keys",
  Settings: "Settings",
};

export function TopBar({
  active,
  identity,
  navCollapsed,
  onReopenNav,
  onLogout,
}: {
  active: string;
  identity: string;
  navCollapsed?: boolean;
  onReopenNav?: () => void;
  onLogout?: () => void;
}) {
  const theme = useTheme();
  const dark = theme === "dark";
  const [menuOpen, setMenuOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  return (
    <div className="warp-topbar">
      {navCollapsed && onReopenNav ? (
        <button
          type="button"
          className="warp-topbar-hamburger"
          aria-label="Open sidebar"
          title="Open sidebar"
          onClick={onReopenNav}
        >
          <Menu size={20} strokeWidth={2} aria-hidden />
        </button>
      ) : null}
      <p className="warp-topbar-title">{PAGE_TITLES[active] ?? active}</p>

      <div className="warp-topbar-right">
        <TopBarStats />
        <span className="warp-topbar-divider" />
        <div className="warp-topbar-profile" ref={wrap}>
          <button
            type="button"
            className="warp-topbar-profile-btn"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span className="warp-topbar-avatar"><User size={18} strokeWidth={1.8} aria-hidden /></span>
            <span className="warp-topbar-email">{identity}</span>
            <ChevronDown size={20} strokeWidth={2} aria-hidden />
          </button>
          {menuOpen ? (
            <div className="warp-topbar-menu" role="menu">
              {onLogout ? (
                <button
                  type="button"
                  role="menuitem"
                  className="warp-topbar-menu-item"
                  onClick={() => {
                    setMenuOpen(false);
                    onLogout();
                  }}
                >
                  <LogOut size={16} strokeWidth={1.8} aria-hidden /> Logout
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <span className="warp-topbar-divider" />

        <button
          type="button"
          className="warp-topbar-theme"
          title={dark ? "Light mode" : "Dark mode"}
          aria-label="Toggle theme"
          onClick={() => setTheme(dark ? "light" : "dark")}
        >
          {dark ? <DgDarkTheme size={20} /> : <DgLightTheme size={20} />}
        </button>
      </div>
    </div>
  );
}
