"use client";

import { Menu } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DialogHost } from "@/components/ui/dialog";
import { Toaster } from "@/components/ui/toast";
import { clearTokens, currentUser, getToken, logout, setAuthLostHandler } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { CommandPalette } from "./command-palette";
import { NAV_ITEMS } from "./nav";
import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";
import { DashboardScreen } from "@/features/dashboard";
import { LoginScreen } from "@/features/login";
import { AdminsScreen } from "@/features/admins";
import { AuditLogScreen } from "@/features/auditlog";
import { GroupsScreen } from "@/features/groups";
import { NodesScreen } from "@/features/nodes";
import { ProfilesScreen } from "@/features/profiles";
import { RoutingScreen } from "@/features/routing";
import { OutboundsScreen } from "@/features/outbounds";
import { SettingsScreen } from "@/features/settings";
import { UsersScreen } from "@/features/users";
import { ApiKeysScreen } from "@/features/apikeys";

const SCREEN_KEYS = NAV_ITEMS.map((i) => i.key);

function keyFromPath(): string {
  if (typeof window === "undefined") return "Overview";
  const slug = window.location.pathname.replace(/^\/+|\/+$/g, "").toLowerCase();
  if (!slug) return "Overview";
  return SCREEN_KEYS.find((k) => k.toLowerCase() === slug) ?? "Overview";
}

function pathForKey(key: string): string {
  return key === "Overview" ? "/" : `/${key.toLowerCase()}`;
}

export function ConsoleV2() {
  const [active, setActiveState] = useState("Overview");

  useEffect(() => {
    setActiveState(keyFromPath());
    const onPop = () => setActiveState(keyFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const setActive = (key: string) => {
    setActiveState(key);
    if (typeof window !== "undefined") {
      const path = pathForKey(key);
      if (window.location.pathname !== path) {
        window.history.pushState(null, "", path);
      }
    }
  };
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [identity, setIdentity] = useState("xlink.local");
  const [navOpen, setNavOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const theme = useTheme();
  const qc = useQueryClient();
  const t = useT();

  useEffect(() => {
    setAuthLostHandler(() => {
      qc.clear();
      setAuthed(false);
    });
    if (!getToken()) {
      setAuthed(false);
      return;
    }
    let active = true;
    currentUser()
      .then((u) => {
        if (!active) return;
        setAuthed(true);
        if (u.username) setIdentity(u.username);
      })
      .catch(() => {
        if (!active) return;
        clearTokens();
        setAuthed(false);
      });
    return () => {
      active = false;
      setAuthLostHandler(null);
    };
  }, []);

  if (authed === null) {
    return (
      <div className="grid h-screen place-items-center bg-canvas font-sans text-fg-muted">
        <Spinner size={22} />
      </div>
    );
  }

  if (!authed) {
    return (
      <div className={theme === "dark" ? "xlink-dark" : ""}>
        <Toaster />
        <DialogHost />
        <LoginScreen
          onSuccess={(name) => {
            setIdentity(name);
            setAuthed(true);
          }}
        />
      </div>
    );
  }

  return (
    <div
      className={`flex h-screen w-full overflow-hidden bg-canvas font-sans text-fg ${theme === "dark" ? "xlink-dark" : ""}`}
    >
      <Toaster />
      <DialogHost />
      <CommandPalette onSelect={setActive} />
      {navOpen ? (
        <button
          type="button"
          aria-label={t("console.closeMenu")}
          className="warp-sb-scrim"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      {navCollapsed ? null : (
        <Sidebar
          active={active}
          open={navOpen}
          onClose={() => setNavCollapsed(true)}
          onSelect={(k) => {
            setActive(k);
            setNavOpen(false);
          }}
        />
      )}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="warp-mobilebar">
          <button
            type="button"
            aria-label={t("console.menu")}
            className="warp-mobilebar-btn"
            onClick={() => setNavOpen(true)}
          >
            <Menu size={20} />
          </button>
          <span className="warp-mobilebar-title">{active}</span>
        </header>
        <main className="min-h-0 flex-1 overflow-auto overscroll-none bg-canvas">
          <TopBar
            active={active}
            identity={identity}
            navCollapsed={navCollapsed}
            onReopenNav={() => setNavCollapsed(false)}
            onLogout={async () => {
              await logout();
              clearTokens();
              qc.clear();
              setAuthed(false);
            }}
          />
          <div className="mx-auto w-full max-w-[1600px] p-4 sm:p-6">
          {active === "Overview" ? (
            <DashboardScreen />
          ) : active === "Admins" ? (
            <AdminsScreen />
          ) : active === "Nodes" ? (
            <NodesScreen />
          ) : active === "Profiles" ? (
            <ProfilesScreen />
          ) : active === "Groups" ? (
            <GroupsScreen />
          ) : active === "Routing" ? (
            <RoutingScreen />
          ) : active === "Outbounds" ? (
            <OutboundsScreen />
          ) : active === "Users" ? (
            <UsersScreen />
          ) : active === "Activity" ? (
            <AuditLogScreen />
          ) : active === "ApiKeys" ? (
            <ApiKeysScreen />
          ) : active === "Settings" ? (
            <SettingsScreen />
          ) : (
            <DashboardScreen />
          )}
          </div>
        </main>
      </div>
    </div>
  );
}
