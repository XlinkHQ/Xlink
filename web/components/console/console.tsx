"use client";

import { Loader2, Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { DialogHost } from "@/components/ui/dialog";
import { Toaster } from "@/components/ui/toast";
import { clearTokens, currentUser, getToken, logout, setAuthLostHandler } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { CommandPalette } from "./command-palette";
import { NAV_ITEMS } from "./nav";
import { Sidebar } from "./sidebar";
import { DashboardScreen } from "./screens/dashboard";
import { LoginScreen } from "./screens/login";
import { AdminsScreen } from "./screens/admins";
import { GroupsScreen } from "./screens/groups";
import { NodesScreen } from "./screens/nodes";
import { ProfilesScreen } from "./screens/profiles";
import { SettingsScreen } from "./screens/settings";
import { UsersScreen } from "./screens/users";

const SCREEN_KEYS = NAV_ITEMS.map((i) => i.key);

function keyFromHash(): string {
  if (typeof window === "undefined") return "Overview";
  const slug = window.location.hash.replace(/^#\/?/, "").toLowerCase();
  return SCREEN_KEYS.find((k) => k.toLowerCase() === slug) ?? "Overview";
}

export function ConsoleV2() {
  const [active, setActiveState] = useState("Overview");

  useEffect(() => {
    setActiveState(keyFromHash());
    const onHash = () => setActiveState(keyFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const setActive = (key: string) => {
    setActiveState(key);
    if (typeof window !== "undefined" && keyFromHash() !== key) {
      window.location.hash = key.toLowerCase();
    }
  };
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [identity, setIdentity] = useState("xlink.local");
  const [navOpen, setNavOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const theme = useTheme();

  useEffect(() => {
    setAuthLostHandler(() => setAuthed(false));
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
        <Loader2 className="h-5 w-5 animate-spin" />
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
      className={`xlink-app-shell flex h-screen w-full overflow-hidden bg-canvas font-sans text-fg ${theme === "dark" ? "xlink-dark" : ""}`}
    >
      <Toaster />
      <DialogHost />
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} onSelect={setActive} />
      {navOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          className="warp-sb-scrim"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      <Sidebar
        active={active}
        open={navOpen}
        identity={identity}
        onSearch={() => setCommandOpen(true)}
        onSelect={(k) => {
          setActive(k);
          setNavOpen(false);
        }}
        onLogout={async () => {
          await logout();
          clearTokens();
          setAuthed(false);
        }}
      />
      <div className="xlink-main-shell relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="warp-mobilebar">
          <button
            type="button"
            aria-label="Menu"
            className="warp-mobilebar-btn"
            onClick={() => setNavOpen(true)}
          >
            <Menu size={20} />
          </button>
          <span className="warp-mobilebar-title">{active}</span>
        </header>
        <main className="min-h-0 flex-1 overflow-auto overscroll-none bg-canvas">
          <div className="mx-auto w-full max-w-[1600px] p-2 sm:p-3">
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
            ) : active === "Users" ? (
              <UsersScreen />
            ) : (
              <SettingsScreen />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
