"use client";

import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  clearTokens,
  createAssignment,
  createNode,
  createProfile,
  currentUser,
  deleteAssignment,
  disableAssignment,
  disableNode,
  disableProfile,
  executeFailover,
  exportBackup,
  getToken,
  gitopsCommit,
  gitopsDiff,
  issueAgentCommand,
  listAssignments,
  listNodes,
  listProfiles,
  listUsers,
  login as apiLogin,
  logout as apiLogout,
  monitoringSummary,
  planFailover,
  restoreBackup,
  runScheduler,
  schedulerPolicies,
  setAuthLostHandler,
  subscriptionFeed,
  trafficSummary,
  assignmentTraffic,
} from "@/lib/api";
import type { NodeRead, ProfileRead, UserRead } from "@/lib/api";
import { appSwitch, menu, sections } from "@/lib/dashboard-data";
import { LIVE_SECTIONS, type LiveSection } from "@/lib/live-sections";

type AppMode = (typeof appSwitch)[number]["label"];

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const GLOBAL_CONTROLS = ["Copy", "Comment", "Detail"] as const;

const UNAVAILABLE_SECTIONS = new Set<string>();

const CREATE_SECTIONS = new Set(["Nodes", "Profiles", "Assignments"]);
const DISABLE_SECTIONS = new Set(["Nodes", "Profiles", "Assignments"]);
const REMOVE_SECTIONS = new Set(["Assignments"]);

function isImplementedAction(section: string, action: string, hasSelection: boolean): boolean {
  const normalized = action.toLowerCase();
  if (section === "Agents") return false;
  if (section === "Overview") {
    if (normalized === "refresh summary" || normalized === "open monitoring" || normalized === "export report" || normalized === "refresh") return true;
    if (normalized === "dashboard layout" || normalized === "alert rules") return true;
    return false;
  }
  if (normalized.includes("refresh")) return LIVE_SECTIONS[section] !== undefined;
  if (
    normalized.includes("new") ||
    normalized.includes("add") ||
    normalized.includes("create")
  ) {
    return CREATE_SECTIONS.has(section);
  }
  if (normalized.includes("disable")) return DISABLE_SECTIONS.has(section) && hasSelection;
  if (normalized.includes("remove")) return REMOVE_SECTIONS.has(section) && hasSelection;
  if (normalized === "copy" || normalized === "detail") {
    return LIVE_SECTIONS[section] !== undefined && hasSelection;
  }
  return false;
}

function getControlIcon(control: string) {
  if (control.includes("Enable") || control.includes("Execute")) {
    return "xlink-enable.svg";
  }

  if (control.includes("Disable") || control.includes("Invalidate")) {
    return "xlink-disable.svg";
  }

  if (control.includes("Remove")) {
    return "xlink-remove.svg";
  }

  if (control.includes("Reset") || control.includes("Rollback") || control.includes("Restore")) {
    return "xlink-reset.svg";
  }

  if (control.includes("Validate") || control.includes("Acknowledge") || control.includes("Preview")) {
    return "xlink-check.svg";
  }

  if (control.includes("Rotate") || control.includes("Sync")) {
    return "xlink-sync.svg";
  }

  return null;
}

function getRowState(activeTab: string, rowIndex: number) {
  if (activeTab === "Disabled" || rowIndex === 1) return "disabled";
  if (activeTab === "Expired" || rowIndex === 2) return "expired";
  return "active";
}

function getRowFlags(state: string) {
  if (state === "disabled") return "X";
  if (state === "expired") return "E";
  if (state === "running") return "R";
  return "";
}

function getTableIcon(section: string) {
  if (section === "Nodes") return "icon-10.svg";
  if (section === "Profiles") return "icon-12.svg";
  if (section === "Assignments") return "icon-14.svg";
  if (section === "Users") return "icon-15.svg";
  return "icon-9.svg";
}

function getColumnWidth(header: string, index: number) {
  const widths: Record<string, string> = {
    Active: "68px",
    Assignment: "127px",
    Comment: "117px",
    Created: "110px",
    Email: "180px",
    Expires: "90px",
    Host: "132px",
    Limit: "90px",
    Max: "55px",
    Name: "127px",
    Node: "127px",
    Port: "55px",
    Profile: "127px",
    Protocol: "90px",
    Provider: "92px",
    Role: "90px",
    Status: "90px",
    Updated: "110px",
    User: "127px",
    Username: "127px",
    Users: "55px",
    Verified: "77px",
    Version: "77px",
  };

  return widths[header] ?? (index === 0 ? "127px" : "132px");
}

export function XLinkConsole() {
  const [authenticated, setAuthenticated] = useState(false);
  const [booting, setBooting] = useState(true);
  const [appMode, setAppMode] = useState<AppMode>("Advanced");
  const [activeSectionLabel, setActiveSectionLabel] = useState("Assignments");
  const [openParentLabel, setOpenParentLabel] = useState<string | null>("Assignments");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [safeMode, setSafeMode] = useState(false);
  const [filterEnabled, setFilterEnabled] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [createPanelOpen, setCreatePanelOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFormOpen, setSearchFormOpen] = useState(false);
  const [notice, setNotice] = useState("XLink console ready.");
  const [liveRows, setLiveRows] = useState<Record<string, unknown>[]>([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(() => new Set());
  const [dashboardLayoutOpen, setDashboardLayoutOpen] = useState(false);
  const [alertRulesOpen, setAlertRulesOpen] = useState(false);
  const [overviewLayout, setOverviewLayout] = useState<{ metric: string; visible: boolean }[]>(() => {
    try {
      const stored = localStorage.getItem("xlink.overview.layout");
      if (stored) return JSON.parse(stored) as { metric: string; visible: boolean }[];
    } catch {}
    return [];
  });
  const [alertRules, setAlertRules] = useState<{ id: string; metric: string; operator: "gt" | "lt"; threshold: number }[]>(() => {
    try {
      const stored = localStorage.getItem("xlink.overview.alerts");
      if (stored) return JSON.parse(stored) as { id: string; metric: string; operator: "gt" | "lt"; threshold: number }[];
    } catch {}
    return [];
  });
  const menuRef = useRef<HTMLElement | null>(null);
  const activeSection =
    sections.find((section) => section.label === activeSectionLabel) ?? sections[0];
  const [activeTab, setActiveTab] = useState(activeSection.tabs[0]);
  const visibleTab = activeSection.tabs.includes(activeTab) ? activeTab : activeSection.tabs[0];
  const liveSection: LiveSection | undefined = LIVE_SECTIONS[activeSection.label];

  const STATUS_TAB_MAP: Record<string, string> = {
    Active: "active",
    Offline: "offline",
    Disabled: "disabled",
    Expired: "expired",
  };

  const displayRows: Record<string, unknown>[] = (() => {
    if (activeSection.label === "Overview") {
      if (overviewLayout.length === 0) return liveRows;
      const layoutMetrics = overviewLayout.map((e) => e.metric);
      const ordered: Record<string, unknown>[] = [];
      for (const entry of overviewLayout) {
        if (!entry.visible) continue;
        const row = liveRows.find((r) => String(r.metric ?? "") === entry.metric);
        if (row) ordered.push(row);
      }
      for (const row of liveRows) {
        const m = String(row.metric ?? "");
        if (!layoutMetrics.includes(m)) ordered.push(row);
      }
      return ordered;
    }

    if (!liveSection) return liveRows;

    let rows = liveRows;

    const tabStatus = STATUS_TAB_MAP[visibleTab];
    if (tabStatus !== undefined) {
      rows = rows.filter((row) => liveSection.statusOf(row) === tabStatus);
    }

    if (filterEnabled && searchText.trim()) {
      const needle = searchText.trim().toLowerCase();
      rows = rows.filter((row) =>
        liveSection.columns.some((col) =>
          col.accessor(row).toLowerCase().includes(needle),
        ),
      );
    }

    return rows;
  })();

  const activeCount = liveSection ? displayRows.length : 0;

  const breachedMetrics = new Set<string>(
    activeSection.label === "Overview"
      ? alertRules
          .filter((rule) => {
            const row = liveRows.find((r) => String(r.metric ?? "") === rule.metric);
            if (!row) return false;
            const raw = typeof row.raw === "number" ? row.raw : Number(row.value);
            if (Number.isNaN(raw)) return false;
            return rule.operator === "gt" ? raw > rule.threshold : raw < rule.threshold;
          })
          .map((rule) => rule.metric)
      : [],
  );

  const icon = (name: string, className = "icon") => (
    <img alt="" className={className} draggable={false} src={`/routeros-icons/${name}`} />
  );

  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearNoticeTimer = () => {
    if (!noticeTimer.current) return;
    clearTimeout(noticeTimer.current);
    noticeTimer.current = null;
  };
  const showNotice = (message: string, ttl = 3500) => {
    const clean = message.replace(/\.+$/, "");
    setNotice(clean);
    clearNoticeTimer();
    noticeTimer.current = setTimeout(() => {
      setNotice("");
      noticeTimer.current = null;
    }, ttl);
  };

  const runSectionAction = async (action: string) => {
    const normalized = action.toLowerCase();

    if (activeSection.label === "Overview") {
      if (normalized === "refresh summary" || normalized === "refresh") {
        setRefreshKey((k) => k + 1);
        showNotice("Overview refreshed.");
        return;
      }
      if (normalized === "open monitoring") {
        setActiveSectionLabel("Monitoring");
        const monSection = sections.find((s) => s.label === "Monitoring");
        if (monSection) setActiveTab(monSection.tabs[0]);
        showNotice("Monitoring opened.");
        return;
      }
      if (normalized === "export report") {
        showNotice("Exporting report…");
        try {
          const [nodes, profiles, assignments, users, traffic, monitoring] = await Promise.all([
            listNodes(),
            listProfiles(),
            listAssignments(),
            listUsers(),
            trafficSummary(),
            monitoringSummary(),
          ]);
          const report = {
            generated_at: new Date().toISOString(),
            nodes: { size: nodes.size, items: nodes.items },
            profiles: { size: profiles.size, items: profiles.items },
            assignments: { size: assignments.size, items: assignments.items },
            users: { size: users.size, items: users.items },
            traffic,
            monitoring,
          };
          const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `xlink-overview-report-${new Date().toISOString().slice(0, 10)}.json`;
          a.click();
          URL.revokeObjectURL(url);
          showNotice("Report exported.");
        } catch (caught) {
          showNotice(caught instanceof ApiError ? caught.message : "Export failed.");
        }
        return;
      }
      if (normalized === "dashboard layout") {
        setDashboardLayoutOpen(true);
        setAlertRulesOpen(false);
        showNotice("Dashboard Layout opened.");
        return;
      }
      if (normalized === "alert rules") {
        setAlertRulesOpen(true);
        setDashboardLayoutOpen(false);
        showNotice("Alert Rules opened.");
        return;
      }
      showNotice(`${action} is not implemented`);
      return;
    }

    if (liveSection && normalized.includes("refresh")) {
      setRefreshKey((key) => key + 1);
      showNotice(`Refreshing ${activeSection.label}…`);
      return;
    }

    if (
      normalized.includes("new") ||
      normalized.includes("add") ||
      normalized.includes("register") ||
      normalized.includes("create")
    ) {
      if (!CREATE_SECTIONS.has(activeSection.label)) {
        setCreatePanelOpen(false);
        showNotice(`${activeSection.label} has no create form.`);
        return;
      }
      setCreatePanelOpen(true);
      showNotice(`${action} form opened for ${activeSection.label}.`);
      return;
    }

    if (normalized === "copy" || normalized === "detail") {
      if (!liveSection) {
        showNotice(`${action} is not available here.`);
        return;
      }
      if (!selectedRowId) {
        showNotice("Select a row first.");
        return;
      }
      const row = liveRows.find((candidate, index) => {
        const id =
          typeof candidate.id === "string"
            ? candidate.id
            : typeof candidate.name === "string"
              ? `${activeSection.label}:${candidate.name}:${index}`
              : `${activeSection.label}:row:${index}`;
        return id === selectedRowId;
      });
      if (!row) {
        showNotice("Select a row first.");
        return;
      }
      if (normalized === "copy") {
        const text = typeof row.id === "string" ? row.id : JSON.stringify(row);
        navigator.clipboard
          .writeText(text)
          .then(() => showNotice("Copied to clipboard"))
          .catch(() => showNotice("Copy failed"));
        return;
      }
      showNotice(JSON.stringify(row));
      return;
    }

    if (normalized === "comment") {
      showNotice("Comment is not implemented");
      return;
    }

    if (normalized.includes("disable")) {
      if (!DISABLE_SECTIONS.has(activeSection.label)) {
        showNotice(`${action} is not available yet.`);
        return;
      }
      if (!selectedRowId) {
        showNotice("Select a row first.");
        return;
      }
      try {
        if (activeSection.label === "Nodes") {
          await disableNode(selectedRowId);
        } else if (activeSection.label === "Profiles") {
          await disableProfile(selectedRowId);
        } else if (activeSection.label === "Assignments") {
          await disableAssignment(selectedRowId);
        }
        setRefreshKey((k) => k + 1);
        showNotice("Disabled.");
      } catch (caught) {
        showNotice(caught instanceof ApiError ? caught.message : "Action failed.");
      }
      return;
    }

    if (normalized.includes("remove")) {
      if (!selectedRowId) {
        showNotice("Select a row first.");
        return;
      }
      try {
        if (activeSection.label === "Assignments") {
          await deleteAssignment(selectedRowId);
          setRefreshKey((k) => k + 1);
          showNotice("Deleted.");
        } else {
          showNotice("Remove not supported for this section.");
        }
      } catch (caught) {
        showNotice(caught instanceof ApiError ? caught.message : "Action failed.");
      }
      return;
    }

    showNotice(`${action} is not implemented`);
  };

  useEffect(() => {
    setAuthLostHandler(() => {
      setAuthenticated(false);
      setLiveRows([]);
      showNotice("Session expired. Please sign in again.");
    });

    let active = true;
    if (!getToken()) {
      setBooting(false);
    } else {
      currentUser()
        .then(() => {
          if (active) setAuthenticated(true);
        })
        .catch(() => {
          if (active) clearTokens();
        })
        .finally(() => {
          if (active) setBooting(false);
        });
    }

    return () => {
      active = false;
      clearNoticeTimer();
      setAuthLostHandler(null);
    };
  }, []);

  useEffect(() => {
    if (!CREATE_SECTIONS.has(activeSection.label)) {
      setCreatePanelOpen(false);
    }
    if (activeSection.label !== "Overview") {
      setDashboardLayoutOpen(false);
      setAlertRulesOpen(false);
    }
    setSelectedRowId(null);
    setSelectedRowIds(new Set());
    setSearchText("");
    setFilterEnabled(false);
  }, [activeSection.label]);

  useEffect(() => {
    if (!openParentLabel) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      setOpenParentLabel(null);
    };

    document.addEventListener("mousedown", closeOnOutsideClick);

    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [openParentLabel]);

  useEffect(() => {
    if (!authenticated || !liveSection) {
      setLiveRows([]);
      setLiveError(null);
      setLiveLoading(false);
      return;
    }

    let active = true;
    setLiveRows([]);
    setLiveLoading(true);
    setLiveError(null);

    liveSection
      .fetch()
      .then((page) => {
        if (!active) return;
        setLiveRows(page.items);
        showNotice(`${activeSection.label} loaded ${page.items.length} record(s).`);
      })
      .catch((caught) => {
        if (!active) return;
        setLiveRows([]);
        setLiveError(caught instanceof ApiError ? caught.message : "Cannot reach the control plane.");
        showNotice(`${activeSection.label} failed to load.`);
      })
      .finally(() => {
        if (active) setLiveLoading(false);
      });

    return () => {
      active = false;
    };
  }, [authenticated, liveSection, activeSection.label, refreshKey]);

  const handleLogout = async () => {
    setMoreOpen(false);
    await apiLogout();
    setAuthenticated(false);
    setLiveRows([]);
    showNotice("Signed out.");
  };

  if (booting) {
    return (
      <div className="login">
        <section>
          <div className="credits">
            <span>Connecting…</span>
          </div>
        </section>
      </div>
    );
  }

  if (!authenticated) {
    return <LoginScreen onLogin={() => setAuthenticated(true)} />;
  }

  const sectionToolbar = (
    <aside className="toolbar">
      <section>
        <div className="toolbar-heading">
          {icon("icon-8.svg")}
          <h2>Actions</h2>
        </div>
        <ul>
          {activeSection.actions.map((action) => {
            const enabled = isImplementedAction(activeSection.label, action, selectedRowId !== null);

            return (
              <li key={action}>
                <button
                  className="side-action"
                  disabled={!enabled}
                  onClick={() => runSectionAction(action)}
                  title={enabled ? undefined : "Not implemented"}
                  type="button"
                >
                  {action}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
      <section>
        <div className="toolbar-heading">
          {icon("icon-12.svg")}
          <h2>Configuration</h2>
        </div>
        <ul>
          {activeSection.configuration.map((item) => {
            const configEnabled = isImplementedAction(activeSection.label, item, selectedRowId !== null);
            return (
              <li key={item}>
                <button
                  className="side-action"
                  disabled={!configEnabled}
                  onClick={configEnabled ? () => runSectionAction(item) : undefined}
                  title={configEnabled ? undefined : "Not implemented"}
                  type="button"
                >
                  {item}
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );

  return (
    <div
      id="page"
      className={cx(
        "grid-shell",
        appMode !== "Advanced" && "no-sidebar",
        sidebarCollapsed && appMode === "Advanced" && "sidebar-collapsed",
      )}
    >
      <header className="topbar">
        <button
          aria-pressed={sidebarCollapsed}
          className="btn btn-icon btn-outline btn-menu-switch"
          onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          title={sidebarCollapsed ? "Expand side menu" : "Minimize side menu"}
          type="button"
        >
          {icon("xlink-chevron-small.svg", "icon icon-sm")}
        </button>
        <div className="identity">xlink.local</div>
        <div className="traffic">
          <span>Tx: 760 bps</span>
          <span>Rx: 92.9 kbps</span>
        </div>
        <div className="topbar-center">
          <ul className="undo-redo" role="toolbar" aria-label="Reverting">
            <li>
              <button
                className="btn btn-outline btn-icon"
                disabled
                title="Not implemented"
                type="button"
              >
                {icon("xlink-undo.svg", "icon icon-sm")}
              </button>
            </li>
            <li>
              <button
                className="btn btn-outline btn-icon"
                disabled
                title="Not implemented"
                type="button"
              >
                {icon("xlink-redo.svg", "icon icon-sm")}
              </button>
            </li>
          </ul>
          <label className="check">
            <input
              checked={safeMode}
              className="switch"
              onChange={(event) => {
                setSafeMode(event.target.checked);
                showNotice(event.target.checked ? "Safe Mode enabled." : "Safe Mode disabled.");
              }}
              type="checkbox"
            />
            <b>Safe Mode</b>
          </label>
          <nav className="btn-switch-group" aria-label="Applications">
            {appSwitch.map((item) => (
              <button
                key={item.label}
                aria-pressed={item.label === appMode}
                className={cx("btn btn-white btn-icon-txt", item.label === appMode && "active")}
                onClick={() => {
                  setAppMode(item.label);
                  setMoreOpen(false);
                  showNotice(`${item.label} opened.`);
                }}
                type="button"
              >
                {icon(item.icon)}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>
        <div className={cx("topbar-more btn-select-wrap btn-select-clean", moreOpen && "show")}>
          <button
            aria-controls="genMenu"
            aria-expanded={moreOpen}
            aria-haspopup="true"
            className="btn btn-outline btn-icon btn-select"
            id="genMenuButton"
            onClick={() => setMoreOpen((open) => !open)}
            title="General menu"
            type="button"
          >
            {icon("xlink-dots.svg", "icon icon-sm")}
          </button>
          {moreOpen ? (
            <div className="btn-select-drop" role="menu" aria-labelledby="genMenuButton">
              <ul id="genMenu" role="presentation">
                <li className="mobile-only">
                  <button
                    className="btn btn-icon-txt"
                    onClick={() => showNotice("Nothing to undo.")}
                    role="menuitem"
                    type="button"
                  >
                    {icon("xlink-undo.svg")}
                    Undo
                  </button>
                </li>
                <li className="mobile-only">
                  <button
                    className="btn btn-icon-txt"
                    onClick={() => showNotice("Nothing to redo.")}
                    role="menuitem"
                    type="button"
                  >
                    {icon("xlink-redo.svg")}
                    Redo
                  </button>
                </li>
                <li className="sep mobile-only" />
                <li className="mobile-only">
                  <label>
                    <span className="btn btn-icon-txt">
                      {icon("xlink-safe.svg")}
                      <span>Safe Mode</span>
                      <input
                        checked={safeMode}
                        className="switch"
                        onChange={(event) => {
                          setSafeMode(event.target.checked);
                          showNotice(
                            event.target.checked ? "Safe Mode enabled." : "Safe Mode disabled.",
                          );
                        }}
                        type="checkbox"
                      />
                    </span>
                  </label>
                </li>
                <li className="sep" />
                {[
                  ["Help Center", "xlink-help.svg"],
                  ["Get Apps", "xlink-docs.svg"],
                ].map(([item, itemIcon]) => (
                  <li key={item}>
                    <button
                      className="btn btn-icon-txt"
                      disabled
                      role="menuitem"
                      title="Not implemented"
                      type="button"
                    >
                      {icon(itemIcon)}
                      {item}
                    </button>
                  </li>
                ))}
                <li className="sep" />
                {[
                  ["About", "xlink-about.svg"],
                  ["Reboot", "xlink-reboot.svg"],
                ].map(([item, itemIcon]) => (
                  <li key={item}>
                    <button
                      className="btn btn-icon-txt"
                      disabled
                      role="menuitem"
                      title="Not implemented"
                      type="button"
                    >
                      {icon(itemIcon)}
                      {item}
                    </button>
                  </li>
                ))}
                <li className="sep" />
                <li>
                  <button
                    className="btn btn-icon-txt"
                    onClick={handleLogout}
                    role="menuitem"
                    type="button"
                  >
                    {icon("xlink-exit.svg")}
                    Logout
                  </button>
                </li>
              </ul>
            </div>
          ) : null}
        </div>
      </header>

      {appMode === "Advanced" ? (
        <nav className="sidenav">
          <div className="menu-wrap">
            <nav className="menu" aria-label="Features" ref={menuRef}>
              <ul className="level-1">
                {menu.map((item) => (
                  <li
                    key={item.label}
                    className={cx(
                      "parent" in item && item.parent && "parent",
                      openParentLabel === item.label && "active",
                    )}
                  >
                    <span className="group">
                      <button
                        aria-expanded={
                          "parent" in item && item.parent
                            ? openParentLabel === item.label
                            : undefined
                        }
                        aria-haspopup={"parent" in item && item.parent ? "true" : undefined}
                        aria-current={item.label === activeSection.label ? "page" : undefined}
                        className={cx(item.label === activeSection.label && "current")}
                        onClick={() => {
                          if (!("tabs" in item)) {
                            setSearchOpen(true);
                            setSearchQuery("");
                            showNotice("Search opened.");
                            return;
                          }

                          if (item.parent) {
                            setOpenParentLabel((currentLabel) =>
                              currentLabel === item.label ? null : item.label,
                            );
                            setActiveSectionLabel(item.label);
                            setActiveTab(item.tabs[0]);
                            showNotice(`${item.label} opened.`);
                            return;
                          }

                          setOpenParentLabel(null);
                          setActiveSectionLabel(item.label);
                          setActiveTab(item.tabs[0]);
                          showNotice(`${item.label} opened.`);
                        }}
                        type="button"
                      >
                        {icon(item.icon)}
                        <span className="text">{item.label}</span>
                        {"parent" in item && item.parent
                          ? icon("xlink-chevron-small.svg", "icon icon-sm menu-chevron")
                          : null}
                      </button>
                      {"children" in item && item.children && openParentLabel === item.label ? (
                        <ul className="level-2" aria-label={`${item.label} submenu`}>
                          {item.children.map((child) => (
                            <li key={child}>
                              <button
                                onClick={() => {
                                  setActiveSectionLabel(item.label);
                                  setActiveTab(item.tabs.includes(child) ? child : item.tabs[0]);
                                  setOpenParentLabel(null);
                                  showNotice(`${child} opened.`);
                                }}
                                type="button"
                              >
                                {child}
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </nav>
      ) : null}

      <main className={cx("main", appMode === "Terminal" && "main-terminal")}>
        {appMode === "Terminal" ? (
          <TerminalView />
        ) : appMode === "Setup" ? (
          <SetupView
            icon={icon}
            pinned={pinned}
            setPinned={setPinned}
            showNotice={showNotice}
          />
        ) : searchFormOpen ? (
          <ChangeNowView
            pinned={pinned}
            setPinned={setPinned}
            onCancel={() => {
              setSearchFormOpen(false);
              showNotice("Change Now closed.");
            }}
            onSubmit={() => {
              setSearchFormOpen(false);
              showNotice("Password change submitted.");
            }}
          />
        ) : (
          <div className="wndw">
          <div className="wndw-titlebar bg-medium">
            <div className="titlebar-left">
              {icon(activeSection.icon, "wndw-titlebar-icon icon")}
              <h1 className="wndw-titlebar-title">{activeSection.label}</h1>
              <nav className="tabs-nav">
                <ul className="tabs" role="tablist">
                  {activeSection.tabs.map((tab) => (
                    <li key={tab}>
                      <button
                        className={cx("btn btn-white", tab === visibleTab && "tabs-active")}
                        onClick={() => {
                          setActiveTab(tab);
                          showNotice(`${tab} tab opened.`);
                        }}
                        type="button"
                      >
                        {tab}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            </div>
            <button
              aria-pressed={pinned}
              className={cx("btn btn-icon btn-extra", pinned && "active")}
              onClick={() => {
                setPinned((isPinned) => !isPinned);
                showNotice(pinned ? "View unpinned." : "View pinned.");
              }}
              title="Pin view"
              type="button"
            >
              {icon("xlink-pin.svg", "icon icon-sm")}
            </button>
          </div>

          <div className="wndw-tools">
            <ul className="controls" role="toolbar" aria-label={`${activeSection.label} tools`}>
              {GLOBAL_CONTROLS.map((control) => {
                const controlIcon = getControlIcon(control);
                const enabled = isImplementedAction(activeSection.label, control, selectedRowId !== null);

                return (
                  <li key={`global-${control}`}>
                    <button
                      className="btn btn-icon-txt"
                      disabled={!enabled}
                      onClick={() => runSectionAction(control)}
                      title={enabled ? undefined : "Not implemented"}
                      type="button"
                    >
                      {controlIcon ? icon(controlIcon) : null}
                      {control}
                    </button>
                  </li>
                );
              })}
              <li className="controls-sep" aria-hidden="true" />
              {activeSection.controls.map((control, index) => {
                const controlIcon = getControlIcon(control);
                const enabled = isImplementedAction(activeSection.label, control, selectedRowId !== null);

                return (
                  <li key={control}>
                    <button
                      className="btn btn-icon-txt"
                      disabled={!enabled}
                      onClick={() => runSectionAction(control)}
                      title={enabled ? undefined : "Not implemented"}
                      type="button"
                    >
                      {index === 0 ? (
                        icon("icon-31.svg")
                      ) : controlIcon ? (
                        icon(controlIcon)
                      ) : null}
                      {control}
                    </button>
                  </li>
                );
              })}
            </ul>
            <label className="check">
              <input
                checked={filterEnabled}
                className="switch"
                onChange={(event) => {
                  setFilterEnabled(event.target.checked);
                  if (!event.target.checked) setSearchText("");
                  showNotice(
                    event.target.checked
                      ? `${activeSection.label} filter enabled.`
                      : `${activeSection.label} filter disabled.`,
                  );
                }}
                type="checkbox"
              />
              <b>Filter</b>
            </label>
            {filterEnabled && liveSection ? (
              <input
                aria-label="Search rows"
                className="filter-search-input"
                placeholder="Search…"
                type="search"
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
              />
            ) : null}
            <div className="tools-right">
              <div className="statusbar">{activeCount} items</div>
            </div>
          </div>

          <div className={cx("content", createPanelOpen && "content-form")}>
            {createPanelOpen ? (
              <CreatePanel
                sectionLabel={activeSection.label}
                onCancel={() => {
                  setCreatePanelOpen(false);
                  showNotice(`${activeSection.label} create form closed.`);
                }}
                onSuccess={() => {
                  setCreatePanelOpen(false);
                  setRefreshKey((k) => k + 1);
                  showNotice(`${activeSection.label} entry created.`);
                }}
              />
            ) : activeSection.label === "Agents" ? (
              <>
                <AgentsPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Subscriptions" ? (
              <>
                <SubscriptionsPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Traffic" ? (
              <>
                <TrafficPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Failover" ? (
              <>
                <FailoverPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Scheduler" ? (
              <>
                <SchedulerPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Backup" ? (
              <>
                <BackupPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "GitOps" ? (
              <>
                <GitOpsPanel showNotice={showNotice} />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Overview" && dashboardLayoutOpen ? (
              <>
                <DashboardLayoutPanel
                  liveRows={liveRows}
                  layout={overviewLayout}
                  onClose={() => setDashboardLayoutOpen(false)}
                  onSave={(newLayout) => {
                    setOverviewLayout(newLayout);
                    try { localStorage.setItem("xlink.overview.layout", JSON.stringify(newLayout)); } catch {}
                    setDashboardLayoutOpen(false);
                    showNotice("Dashboard layout saved.");
                  }}
                />
                {sectionToolbar}
              </>
            ) : activeSection.label === "Overview" && alertRulesOpen ? (
              <>
                <AlertRulesPanel
                  liveRows={liveRows}
                  rules={alertRules}
                  onClose={() => setAlertRulesOpen(false)}
                  onSave={(newRules) => {
                    setAlertRules(newRules);
                    try { localStorage.setItem("xlink.overview.alerts", JSON.stringify(newRules)); } catch {}
                    setAlertRulesOpen(false);
                    showNotice("Alert rules saved.");
                  }}
                />
                {sectionToolbar}
              </>
            ) : (
              <>
            <div className={cx("panel", activeCount === 0 && "no-data")}>
              <table className="table focus-flash comment-std" id="main-table" role="treegrid">
                <thead tabIndex={0}>
                  <tr>
                    <th className="select-col" title="Select" style={{ width: "33px" }}>
                      <input
                        checked={
                          displayRows.length > 0 &&
                          displayRows.every((row) =>
                            typeof row.id === "string" ? selectedRowIds.has(row.id) : false,
                          )
                        }
                        onChange={(event) => {
                          const rowIds = displayRows
                            .map((row) => (typeof row.id === "string" ? row.id : null))
                            .filter((rowId): rowId is string => Boolean(rowId));

                          if (event.target.checked) {
                            setSelectedRowIds(new Set(rowIds));
                            setSelectedRowId(rowIds[0] ?? null);
                          } else {
                            setSelectedRowIds(new Set());
                            setSelectedRowId(null);
                          }

                          showNotice(
                            event.target.checked
                              ? `${activeSection.label} rows selected.`
                              : `${activeSection.label} rows cleared.`,
                          );
                        }}
                        title="Select all"
                        type="checkbox"
                      />
                    </th>
                    <th className="status-col" title="Status" style={{ width: "33px" }}>
                      <div>
                        <i className="rsl" draggable />
                        <i className="rsr" draggable />
                      </div>
                    </th>
                    <th
                      className="sort comment"
                      data-name="comment"
                      title="Comment"
                      style={{ width: "117px" }}
                    >
                      <div>
                        <i className="rsl" draggable />
                        <button aria-hidden="true" className="switch" disabled tabIndex={-1} type="button" />
                        <button className="cell-btn" tabIndex={-1} type="button">
                          Comment
                        </button>
                        <i className="rsr" draggable />
                      </div>
                    </th>
                    {(liveSection
                      ? liveSection.columns.map((column) => column.header)
                      : activeSection.columns
                    ).map((head, index) => (
                      <th
                        key={head}
                        aria-sort={index === 0 ? "ascending" : undefined}
                        className={cx("sort", index === 0 && "sort-ascend")}
                        title={head}
                        style={{ width: getColumnWidth(head, index) }}
                      >
                        <div>
                          <i className="rsl" draggable />
                          <button
                            className="cell-btn"
                            onClick={() => showNotice(`${activeSection.label} sorted by ${head}.`)}
                            tabIndex={-1}
                            type="button"
                          >
                            {head}
                          </button>
                          <i className="rsr" draggable />
                        </div>
                      </th>
                    ))}
                    <th className="fill-col" style={{ width: "100%" }}>
                      &nbsp;
                      <div>
                        <i className="rsl" draggable />
                      </div>
                    </th>
                  </tr>
                </thead>
                {liveSection
                  ? displayRows.map((row, rowIndex) => {
	                      const rowState = liveSection.statusOf(row);
	                      const rowFlags =
	                        rowState === "disabled" ? "X" : rowState === "expired" ? "E" : "";
	                      const rowId =
                        typeof row.id === "string"
                          ? row.id
                          : typeof row.name === "string"
                            ? `${activeSection.label}:${row.name}:${rowIndex}`
                            : `${activeSection.label}:row:${rowIndex}`;
	                      const rowSelected = rowId ? selectedRowIds.has(rowId) : false;
                        const rowMetric = String(row.metric ?? "");
                        const rowAlerting = activeSection.label === "Overview" && breachedMetrics.has(rowMetric);

	                      return (
                        <tbody
                          key={`${activeSection.label}-${rowIndex}`}
                          aria-level={1}
                          aria-setsize={displayRows.length}
	                          className={cx(rowState !== "active" && rowState, rowSelected && "selected", rowAlerting && "row-alert")}
	                          data-id={rowIndex + 1}
	                          onClick={() => {
	                            if (!rowId) return;
	                            setSelectedRowIds(new Set([rowId]));
	                            setSelectedRowId(rowId);
	                          }}
	                        >
                          <tr>
                            <td className="select-col">
	                              <input
	                                checked={rowSelected}
	                                onClick={(event) => event.stopPropagation()}
	                                onChange={(event) => {
	                                  if (!rowId) return;
	                                  setSelectedRowIds((current) => {
	                                    const next = new Set(current);
	                                    if (event.target.checked) {
	                                      next.add(rowId);
	                                      setSelectedRowId(rowId);
	                                    } else {
	                                      next.delete(rowId);
	                                      setSelectedRowId(next.values().next().value ?? null);
	                                    }
	                                    return next;
	                                  });
	                                }}
	                                title={`Select row ${rowIndex + 1}`}
	                                type="checkbox"
	                              />
                            </td>
                            <td
                              className="status-col"
                              title={rowAlerting ? "ALERT" : rowFlags ? `${rowFlags} - ${rowState}` : ""}
                            >
                              <span className="flags">
                                {rowAlerting ? <span className="alert-flag">!</span> : rowFlags ? <span className={rowState}>{rowFlags}</span> : null}
                              </span>
                            </td>
                            <td className="comment" title="" />
                            {liveSection.columns.map((column, columnIndex) => (
                              <td
                                key={column.header}
                                style={columnIndex === 0 ? { paddingLeft: "0px" } : undefined}
                              >
                                {columnIndex === 0 ? (
                                  <>
                                    <button
                                      className="btn row-tree-btn"
                                      disabled
                                      style={{ visibility: "hidden" }}
                                      tabIndex={-1}
                                      type="button"
                                    >
                                      <span className="icon icon-tbl icon-Minus_12x12" />
                                    </button>
                                    <img
                                      alt=""
                                      className="icon icon-tbl"
                                      draggable={false}
                                      src={`/routeros-icons/${getTableIcon(activeSection.label)}`}
                                    />
                                  </>
                                ) : null}
                                {column.accessor(row)}
                              </td>
                            ))}
                            <td className="fill-col">&nbsp;</td>
                          </tr>
                        </tbody>
                      );
                    })
                  : null}
              </table>
              <div className="splash">
                <div className="splash-content">
                  {icon("xlink-empty.svg", "splash-icon")}
                  {UNAVAILABLE_SECTIONS.has(activeSection.label) ? (
                    <>
                      <h2>{activeSection.label} is unavailable</h2>
                      <p>This section has no backend service and is not available yet.</p>
                    </>
                  ) : liveSection && liveLoading ? (
                    <>
                      <h2>Loading {activeSection.label}…</h2>
                      <p>Fetching live records from the control plane.</p>
                    </>
                  ) : liveSection && liveError ? (
                    <>
                      <h2>Could not load {activeSection.label}</h2>
                      <p>{liveError}</p>
                      <button
                        className="btn btn-dark-green"
                        onClick={() => setRefreshKey((k) => k + 1)}
                        type="button"
                      >
                        Retry
                      </button>
                    </>
                  ) : (
                    <>
                      <h2>{activeSection.emptyTitle}</h2>
                      <p>{activeSection.emptyText}</p>
                    </>
                  )}
                </div>
              </div>
            </div>

            {sectionToolbar}
              </>
            )}
          </div>
          </div>
        )}
      </main>
      <SearchDialog
        onClose={() => setSearchOpen(false)}
        onOpenChangeNow={() => {
          setSearchOpen(false);
          setSearchFormOpen(true);
          setCreatePanelOpen(false);
          setAppMode("Advanced");
          setOpenParentLabel(null);
          showNotice("Change Now opened.");
        }}
        open={searchOpen}
        query={searchQuery}
        setQuery={setSearchQuery}
      />
      <div className="notice" role="status">
        {notice}
      </div>
    </div>
  );
}

function CreatePanel({
  onCancel,
  onSuccess,
  sectionLabel,
}: {
  onCancel: () => void;
  onSuccess: () => void;
  sectionLabel: string;
}) {
  if (sectionLabel === "Nodes") {
    return <CreateNodePanel onCancel={onCancel} onSuccess={onSuccess} />;
  }
  if (sectionLabel === "Profiles") {
    return <CreateProfilePanel onCancel={onCancel} onSuccess={onSuccess} />;
  }
  if (sectionLabel === "Assignments") {
    return <CreateAssignmentPanel onCancel={onCancel} onSuccess={onSuccess} />;
  }
  return null;
}

function SearchDialog({
  onClose,
  onOpenChangeNow,
  open,
  query,
  setQuery,
}: {
  onClose: () => void;
  onOpenChangeNow: () => void;
  open: boolean;
  query: string;
  setQuery: Dispatch<SetStateAction<string>>;
}) {
  if (!open) return null;

  const hasQuery = query.trim().length > 0;
  const results = [
    { group: "System", label: "Change Now", description: "Change expired administrator password" },
    { group: "Assignments", label: "New Assignment", description: "Create user assignment" },
    { group: "Profiles", label: "Profiles", description: "Protocol and renderer settings" },
  ].filter((item) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return false;
    return `${item.group} ${item.label} ${item.description}`.toLowerCase().includes(needle);
  });

  return (
    <div className="modal-layer" role="presentation">
      <dialog
        className="modal modal-search"
        id="search-dialog"
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          }
        }}
        open
      >
        <header className="bg-bright">
          <form
            autoComplete="off"
            className="search-input grow-1"
            onSubmit={(event) => event.preventDefault()}
            role="search"
          >
            <img
              alt=""
              className="icon"
              draggable={false}
              src="/routeros-icons/icon-18.svg"
            />
            <input
              autoFocus
              id="menu-search-input"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search configuration"
              type="search"
              value={query}
            />
          </form>
          <div className="flex-none">
            <button className="btn btn-icon btn-white" onClick={onClose} title="Esc" type="button">
              <img
                alt=""
                className="icon icon-xs"
                draggable={false}
                src="/routeros-icons/xlink-remove.svg"
              />
            </button>
          </div>
        </header>
        <nav className={cx("hide-empty", (!hasQuery || results.length === 0) && "is-empty")}>
          <h2>Search results</h2>
          <ul id="menu-search-results">
            {results.map((result) => (
              <li key={`${result.group}-${result.label}`}>
                <button
                  className="btn btn-extra"
                  onClick={result.label === "Change Now" ? onOpenChangeNow : undefined}
                  type="button"
                >
                  <span>
                    <mark>{result.label}</mark>
                    <small>{result.group}</small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <nav className={cx("hide-empty", hasQuery && "is-empty")}>
          <h2>Pinned</h2>
          <ul id="menu-pinned-list">
            <li>
              <button className="btn btn-extra" onClick={onOpenChangeNow} type="button">
                <span>
                  <mark>Change Now</mark>
                  <small>System</small>
                </span>
              </button>
            </li>
          </ul>
        </nav>
      </dialog>
    </div>
  );
}

function ChangeNowView({
  onCancel,
  onSubmit,
  pinned,
  setPinned,
}: {
  onCancel: () => void;
  onSubmit: () => void;
  pinned: boolean;
  setPinned: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <div className="form--item-width search-result-form">
      <div className="form--titlebar">
        <div id="title-icon" className="wndw-titlebar-icon icon icon-System" />
        <ul className="breadcrumbs">
          <li>
            <h1 id="title">
              <span>Change Now</span>
            </h1>
          </li>
          <li id="itemname" />
        </ul>
        <div id="adv-placeholder" />
        <button
          aria-pressed={pinned}
          className={cx("btn btn-icon btn-extra flex-none", pinned && "active")}
          onClick={() => setPinned((isPinned) => !isPinned)}
          title="Pin to search results"
          type="button"
        >
          <span className="icon icon-sm icon-Pin_12x12 unpinned" />
        </button>
        <button className="btn btn-icon btn-FormSwitch" title="Expand form" type="button">
          <span className="icon" />
        </button>
      </div>
      <div className="wndw--tools d-lg-none mobile-form-tools hide-empty">
        <div className="select-wrap hide-empty">
          <select id="m-action" tabIndex={-1} aria-labelledby="m-action-button" />
          <button className="btn btn-icon-txt" id="m-action-button" type="button">
            <span className="icon icon-Action" />
            Actions
          </button>
        </div>
        <div className="select-wrap hide-empty">
          <select id="m-config" tabIndex={-1} aria-labelledby="m-config-button" />
          <button className="btn btn-icon-txt" id="m-config-button" type="button">
            <span className="icon icon-Configuration" />
            Configuration
          </button>
        </div>
      </div>
      <div className="alert" id="alert" />
      <div className="content">
        <form
          autoCapitalize="off"
          autoCorrect="off"
          className="panel"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <div className="form--panel-scroll custom-scrollbar" id="content">
            <div className="d-flex gap-inner-base align-items-center">
              <div className="form--statusbar" id="statusbar" />
            </div>
            <div className="form--items">
              <div className="acc-list" id="itemList">
                <section className="acc">
                  <div className="acc-cont" aria-labelledby="title">
                    <fieldset className="min-w-0" role="none">
                      <ChangeReadonly label=" " value="Your password has expired," />
                    </fieldset>
                    <fieldset className="min-w-0" role="none">
                      <ChangeReadonly label=" " value="please change it!" />
                    </fieldset>
                    <fieldset className="min-w-0" role="none">
                      <FPasswordField id="formfield-s1b" label="Old Password" />
                    </fieldset>
                    <fieldset className="min-w-0" role="none">
                      <FPasswordField id="formfield-s3" label="New Password" />
                    </fieldset>
                    <fieldset className="min-w-0" role="none">
                      <FPasswordField id="formfield-s16" label="Confirm Password" />
                    </fieldset>
                  </div>
                </section>
              </div>
            </div>
            <div id="query-output" />
          </div>
          <div className="form--confirm shadow-panel-top">
            <div>
              <button className="btn btn-red btn-md" onClick={onCancel} type="button">
                Cancel
              </button>
            </div>
            <div>
              <button className="btn btn-dark-green btn-wide" type="submit">
                Change Now
              </button>
            </div>
            <div className="errorMessage" id="errorField" />
          </div>
        </form>
        <div className="toolbar d-none d-lg-block hide-empty">
          <section className="hide-empty">
            <div className="d-flex gap-inner-xs align-items-center">
              <span className="icon icon-Action" />
              <h2 id="action-heading">Actions</h2>
            </div>
            <div className="focus-flash">
              <ul id="action" role="toolbar" aria-labelledby="action-heading" />
            </div>
          </section>
          <section className="hide-empty">
            <div className="d-flex gap-inner-xs align-items-center">
              <span className="icon icon-Configuration" />
              <h2 id="config-heading">Configuration</h2>
            </div>
            <div className="focus-flash">
              <ul id="config" role="toolbar" aria-labelledby="config-heading" />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function CreateNodePanel({ onCancel, onSuccess }: { onCancel: () => void; onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("443");
  const [maxUsers, setMaxUsers] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = { name, slug, host, port: Number(port) };
      if (maxUsers.trim()) body.max_users = Number(maxUsers);
      await createNode(body);
      onSuccess();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="panel form--item-width create-panel" onSubmit={submit}>
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <CreateSection title="General">
            <div className="create-grid">
              <fieldset className="min-w-0" role="none">
                <FField label="Name" value={name} onChange={setName} required />
                <FField label="Slug" value={slug} onChange={setSlug} required />
                <FField label="Host" value={host} onChange={setHost} required />
                <FField label="Port" value={port} onChange={setPort} required />
                <FField label="Max Users" value={maxUsers} onChange={setMaxUsers} />
              </fieldset>
            </div>
          </CreateSection>
        </div>
      </div>
      <div className="form--confirm create-actions shadow-panel-top">
        <div>
          <button className="btn btn-red btn-md" onClick={onCancel} type="button">
            Cancel
          </button>
        </div>
        <div>
          <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
            {loading ? "…" : "OK"}
          </button>
        </div>
        {error ? <div className="errorMessage" aria-live="polite">{error}</div> : <div className="errorMessage is-empty" aria-live="polite" />}
      </div>
    </form>
  );
}

function CreateProfilePanel({ onCancel, onSuccess }: { onCancel: () => void; onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [providerKind, setProviderKind] = useState("xray");
  const [nodeId, setNodeId] = useState("");
  const [protocol, setProtocol] = useState("");
  const [nodes, setNodes] = useState<NodeRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listNodes().then((page) => {
      setNodes(page.items);
      if (page.items.length > 0) setNodeId(page.items[0].id);
    }).catch(() => {});
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await createProfile({ name, slug, provider_kind: providerKind, node_id: nodeId, protocol });
      onSuccess();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="panel form--item-width create-panel" onSubmit={submit}>
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <CreateSection title="General">
            <div className="create-grid">
              <fieldset className="min-w-0" role="none">
                <FField label="Name" value={name} onChange={setName} required />
                <FField label="Slug" value={slug} onChange={setSlug} required />
                <FField label="Provider Kind" value={providerKind} onChange={setProviderKind} required />
                <FField label="Protocol" value={protocol} onChange={setProtocol} required />
                <div className="f-item">
                  <label>Node</label>
                  <div className="extra" />
                  <div className="f-row">
                    <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                      {nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </fieldset>
            </div>
          </CreateSection>
        </div>
      </div>
      <div className="form--confirm create-actions shadow-panel-top">
        <div>
          <button className="btn btn-red btn-md" onClick={onCancel} type="button">
            Cancel
          </button>
        </div>
        <div>
          <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
            {loading ? "…" : "OK"}
          </button>
        </div>
        {error ? <div className="errorMessage" aria-live="polite">{error}</div> : <div className="errorMessage is-empty" aria-live="polite" />}
      </div>
    </form>
  );
}

function CreateAssignmentPanel({ onCancel, onSuccess }: { onCancel: () => void; onSuccess: () => void }) {
  const [userId, setUserId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [providerKind, setProviderKind] = useState("xray");
  const [expiresAt, setExpiresAt] = useState("");
  const [trafficLimit, setTrafficLimit] = useState("");
  const [nodes, setNodes] = useState<NodeRead[]>([]);
  const [profiles, setProfiles] = useState<ProfileRead[]>([]);
  const [users, setUsers] = useState<UserRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listNodes(), listProfiles(), listUsers()]).then(([n, p, u]) => {
      setNodes(n.items);
      setProfiles(p.items);
      setUsers(u.items);
      if (n.items.length > 0) setNodeId(n.items[0].id);
      if (p.items.length > 0) setProfileId(p.items[0].id);
      if (u.items.length > 0) setUserId(u.items[0].id);
    }).catch(() => {});
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = { user_id: userId, profile_id: profileId, node_id: nodeId, provider_kind: providerKind };
      if (expiresAt.trim()) body.expires_at = expiresAt;
      if (trafficLimit.trim()) body.traffic_limit_bytes = Number(trafficLimit);
      await createAssignment(body);
      onSuccess();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="panel form--item-width create-panel" onSubmit={submit}>
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <CreateSection title="General">
            <div className="create-grid">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label>User</label>
                  <div className="extra" />
                  <div className="f-row">
                    <select value={userId} onChange={(e) => setUserId(e.target.value)}>
                      {users.map((u) => (
                        <option key={u.id} value={u.id}>{u.username}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="f-item">
                  <label>Profile</label>
                  <div className="extra" />
                  <div className="f-row">
                    <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="f-item">
                  <label>Node</label>
                  <div className="extra" />
                  <div className="f-row">
                    <select value={nodeId} onChange={(e) => setNodeId(e.target.value)}>
                      {nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <FField label="Provider Kind" value={providerKind} onChange={setProviderKind} required />
                <FField label="Expires At" value={expiresAt} onChange={setExpiresAt} />
                <FField label="Traffic Limit (bytes)" value={trafficLimit} onChange={setTrafficLimit} />
              </fieldset>
            </div>
          </CreateSection>
        </div>
      </div>
      <div className="form--confirm create-actions shadow-panel-top">
        <div>
          <button className="btn btn-red btn-md" onClick={onCancel} type="button">
            Cancel
          </button>
        </div>
        <div>
          <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
            {loading ? "…" : "OK"}
          </button>
        </div>
        {error ? <div className="errorMessage" aria-live="polite">{error}</div> : <div className="errorMessage is-empty" aria-live="polite" />}
      </div>
    </form>
  );
}

function FField({
  label,
  onChange,
  required,
  value,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <div className="f-item">
      <label>
        <span>{label}</span>
      </label>
      <div className="extra" />
      <div className="f-row">
        <input
          required={required}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}

function ChangeReadonly({ label, value }: { label: string; value: string }) {
  return (
    <div className="f-item">
      <label>
        <span>{label}</span>
      </label>
      <div className="extra" />
      <div className="f-row">
        <span className="rovalue">{value}</span>
      </div>
    </div>
  );
}

function FPasswordField({ id, label }: { id: string; label: string }) {
  return (
    <div className="f-item">
      <label htmlFor={id}>
        <span>{label}</span>
      </label>
      <div className="extra" />
      <div className="f-row">
        <input id={id} type="password" />
      </div>
    </div>
  );
}

function SubscriptionsPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [scope, setScope] = useState<"assignments" | "profiles" | "users">("assignments");
  const [id, setId] = useState("");
  const [format, setFormat] = useState("text");
  const [content, setContent] = useState("");
  const [etag, setEtag] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formats = ["text", "base64", "singbox_json", "clash_yaml", "mihomo_yaml", "wireguard_conf"];

  const generate = async () => {
    if (!id.trim()) { setError("ID is required."); return; }
    setError(null);
    setContent("");
    setLoading(true);
    try {
      const result = await subscriptionFeed(scope, id.trim(), format);
      setContent(result.content);
      setEtag(result.etag);
      showNotice("Feed generated.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    navigator.clipboard.writeText(content).then(() => showNotice("Copied to clipboard.")).catch(() => showNotice("Copy failed."));
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void generate();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label>
                    <span>Scope</span>
                  </label>
                  <div className="f-row">
                    <select
                      value={scope}
                      onChange={(event) =>
                        setScope(event.target.value as "assignments" | "profiles" | "users")
                      }
                    >
                      <option value="assignments">assignments</option>
                      <option value="profiles">profiles</option>
                      <option value="users">users</option>
                    </select>
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label>
                    <span>ID</span>
                  </label>
                  <div className="f-row">
                    <input value={id} onChange={(event) => setId(event.target.value)} placeholder="UUID" />
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label>
                    <span>Format</span>
                  </label>
                  <div className="f-row">
                    <select value={format} onChange={(event) => setFormat(event.target.value)}>
                      {formats.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </fieldset>
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {etag ? <div className="rovalue muted-value">ETag: {etag}</div> : null}
              {content ? (
                <textarea className="output-textarea" readOnly rows={12} value={content} />
              ) : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
                  {loading ? "…" : "Generate Feed"}
                </button>
                {content ? (
                  <button className="btn btn-light-green btn-wide" onClick={copy} type="button">
                    Copy
                  </button>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function TrafficPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [assignmentId, setAssignmentId] = useState("");
  const [detail, setDetail] = useState<{ upload_bytes: number; download_bytes: number; total_bytes: number; sample_count: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lookup = async () => {
    if (!assignmentId.trim()) { setError("Assignment ID is required."); return; }
    setError(null);
    setDetail(null);
    setLoading(true);
    try {
      const result = await assignmentTraffic(assignmentId.trim());
      setDetail(result);
      showNotice("Traffic loaded.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  function bytes(value: number): string {
    if (value < 1024) return `${value} B`;
    const units = ["KiB", "MiB", "GiB", "TiB"];
    let size = value / 1024;
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
    return `${size.toFixed(1)} ${units[unit]}`;
  }

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void lookup();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label>
                    <span>Assignment ID</span>
                  </label>
                  <div className="extra" />
                  <div className="f-row">
                    <input
                      value={assignmentId}
                      onChange={(event) => setAssignmentId(event.target.value)}
                      placeholder="UUID"
                    />
                  </div>
                </div>
              </fieldset>
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {detail ? (
                <table className="table metric-table">
                  <tbody>
                    <tr><td>Upload</td><td>{bytes(detail.upload_bytes)}</td></tr>
                    <tr><td>Download</td><td>{bytes(detail.download_bytes)}</td></tr>
                    <tr><td>Total</td><td>{bytes(detail.total_bytes)}</td></tr>
                    <tr><td>Samples</td><td>{detail.sample_count}</td></tr>
                  </tbody>
                </table>
              ) : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
                  {loading ? "…" : "Lookup Traffic"}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function FailoverPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [sourceNodeId, setSourceNodeId] = useState("");
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createPlan = async () => {
    if (!sourceNodeId.trim()) { setError("Source Node ID is required."); return; }
    setError(null);
    setPlan(null);
    setResult(null);
    setLoading(true);
    try {
      const p = await planFailover({ source_node_id: sourceNodeId.trim() });
      setPlan(p);
      showNotice("Failover plan created.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  const execute = async () => {
    if (!plan) return;
    setError(null);
    setExecuting(true);
    try {
      const r = await executeFailover(plan);
      setResult(r);
      showNotice("Failover executed.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void createPlan();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="failover-source-node">
                    <span>Source Node ID</span>
                  </label>
                  <div className="extra" />
                  <div className="f-row">
                    <input
                      id="failover-source-node"
                      value={sourceNodeId}
                      onChange={(e) => setSourceNodeId(e.target.value)}
                      placeholder="UUID"
                    />
                  </div>
                </div>
              </fieldset>
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {plan && !result ? (
                <pre className="output-pre">{JSON.stringify(plan, null, 2)}</pre>
              ) : null}
              {result ? <pre className="output-pre">{JSON.stringify(result, null, 2)}</pre> : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
                  {loading ? "…" : "Create Plan"}
                </button>
                {plan ? (
                  <button className="btn btn-light-green btn-wide" onClick={execute} disabled={executing} type="button">
                    {executing ? "…" : "Execute Failover"}
                  </button>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function SchedulerPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [policies, setPolicies] = useState<string[]>([]);
  const [policy, setPolicy] = useState("");
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<ProfileRead[]>([]);
  const [decision, setDecision] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([schedulerPolicies(), listProfiles()]).then(([p, pr]) => {
      setPolicies(p);
      if (p.length > 0) setPolicy(p[0]);
      setProfiles(pr.items);
      if (pr.items.length > 0) setProfileId(pr.items[0].id);
    }).catch(() => {});
  }, []);

  const run = async () => {
    if (!policy) { setError("Select a policy."); return; }
    if (!profileId.trim()) { setError("Profile ID is required."); return; }
    setError(null);
    setDecision(null);
    setLoading(true);
    try {
      const result = await runScheduler({ policy, profile_id: profileId.trim() });
      setDecision(result);
      showNotice("Scheduler ran.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void run();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="scheduler-policy">
                    <span>Policy</span>
                  </label>
                  <div className="f-row">
                    <select id="scheduler-policy" value={policy} onChange={(e) => setPolicy(e.target.value)}>
                      {policies.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="scheduler-profile">
                    <span>Profile</span>
                  </label>
                  <div className="f-row">
                    {profiles.length > 0 ? (
                      <select id="scheduler-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                        {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    ) : (
                      <input
                        id="scheduler-profile"
                        value={profileId}
                        onChange={(e) => setProfileId(e.target.value)}
                        placeholder="Profile UUID"
                        required
                      />
                    )}
                  </div>
                </div>
              </fieldset>
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {decision ? <pre className="output-pre">{JSON.stringify(decision, null, 2)}</pre> : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
                  {loading ? "…" : "Run Scheduler"}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function BackupPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [restoreResult, setRestoreResult] = useState<Record<string, unknown> | null>(null);
  const [exporting, setExporting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doExport = async () => {
    setError(null);
    setExporting(true);
    try {
      const data = await exportBackup({});
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `xlink-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showNotice("Backup exported.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setExporting(false);
    }
  };

  const doRestore = async () => {
    if (!restoreFile) { setError("Select a backup file."); return; }
    setError(null);
    setRestoreResult(null);
    setRestoring(true);
    try {
      const text = await restoreFile.text();
      const backupData = JSON.parse(text) as Record<string, unknown>;
      const result = await restoreBackup({ document: backupData, dry_run: dryRun });
      setRestoreResult(result);
      showNotice(dryRun ? "Dry run complete." : "Restore complete.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void doRestore();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <details open className="acc-inner">
              <summary>Export</summary>
              <div className="acc-cont" aria-labelledby="title">
                <div className="operation-row">
                  <button className="btn btn-dark-green btn-md" onClick={doExport} disabled={exporting} type="button">
                    {exporting ? "…" : "Export Backup"}
                  </button>
                </div>
              </div>
            </details>
          </section>
          <section className="acc">
            <details open className="acc-inner">
              <summary>Restore</summary>
              <div className="acc-cont" aria-labelledby="title">
                <fieldset className="min-w-0" role="none">
                  <div className="f-item">
                    <label htmlFor="backup-file">
                      <span>Backup File</span>
                    </label>
                    <div className="extra" />
                    <div className="f-row">
                      <input
                        id="backup-file"
                        type="file"
                        accept=".json"
                        onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
                      />
                    </div>
                  </div>
                </fieldset>
                <label className="check">
                  <input
                    checked={dryRun}
                    className="switch"
                    onChange={(e) => setDryRun(e.target.checked)}
                    type="checkbox"
                  />
                  <b>Dry Run</b>
                </label>
                {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
                {restoreResult ? <pre className="output-pre">{JSON.stringify(restoreResult, null, 2)}</pre> : null}
                <div className="operation-row">
                  <button className="btn btn-dark-green btn-md" disabled={restoring} type="submit">
                    {restoring ? "…" : "Restore Backup"}
                  </button>
                </div>
              </div>
            </details>
          </section>
        </div>
      </div>
    </form>
  );
}

function GitOpsPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [entityType, setEntityType] = useState("node");
  const [entityId, setEntityId] = useState("");
  const [beforePayload, setBeforePayload] = useState("{}");
  const [afterPayload, setAfterPayload] = useState("{}");
  const [actor, setActor] = useState("");
  const [message, setMessage] = useState("");
  const [diff, setDiff] = useState<Record<string, unknown> | null>(null);
  const [parsedBefore, setParsedBefore] = useState<Record<string, unknown> | null>(null);
  const [parsedAfter, setParsedAfter] = useState<Record<string, unknown> | null>(null);
  const [commitResult, setCommitResult] = useState<Record<string, unknown> | null>(null);
  const [diffing, setDiffing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDiff = async () => {
    if (!entityId.trim()) { setError("Entity ID is required."); return; }
    setError(null);
    setDiff(null);
    setCommitResult(null);
    setDiffing(true);
    try {
      let bp: Record<string, unknown>;
      let ap: Record<string, unknown>;
      try {
        bp = JSON.parse(beforePayload) as Record<string, unknown>;
        ap = JSON.parse(afterPayload) as Record<string, unknown>;
      } catch {
        setError("Invalid JSON in before/after payload.");
        setDiffing(false);
        return;
      }
      const beforeObj = { entity_type: entityType, entity_id: entityId.trim(), payload: bp };
      const afterObj = { entity_type: entityType, entity_id: entityId.trim(), payload: ap };
      const result = await gitopsDiff({ before: beforeObj, after: afterObj });
      setDiff(result);
      setParsedBefore(beforeObj);
      setParsedAfter(afterObj);
      showNotice("Diff computed.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setDiffing(false);
    }
  };

  const runCommit = async () => {
    if (!parsedBefore || !parsedAfter) return;
    setError(null);
    setCommitting(true);
    try {
      const body: Record<string, unknown> = { before: parsedBefore, after: parsedAfter };
      if (actor.trim()) body.actor = actor.trim();
      if (message.trim()) body.message = message.trim();
      const result = await gitopsCommit(body);
      setCommitResult(result);
      showNotice("Committed.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setCommitting(false);
    }
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void runDiff();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="gitops-entity-type">
                    <span>Entity Type</span>
                  </label>
                  <div className="f-row">
                    <select id="gitops-entity-type" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
                      <option value="node">node</option>
                      <option value="profile">profile</option>
                      <option value="assignment">assignment</option>
                      <option value="user">user</option>
                    </select>
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="gitops-entity-id">
                    <span>Entity ID</span>
                  </label>
                  <div className="f-row">
                    <input
                      id="gitops-entity-id"
                      value={entityId}
                      onChange={(e) => setEntityId(e.target.value)}
                      placeholder="UUID"
                      required
                    />
                  </div>
                </div>
              </fieldset>
              <div className="form-row-pair operational-pair">
                <div className="f-item f-item-stack">
                  <label htmlFor="gitops-before">
                    <span>Before Payload (JSON)</span>
                  </label>
                  <div className="f-row">
                    <textarea
                      id="gitops-before"
                      className="output-textarea"
                      rows={5}
                      value={beforePayload}
                      onChange={(e) => setBeforePayload(e.target.value)}
                    />
                  </div>
                </div>
                <div className="f-item f-item-stack">
                  <label htmlFor="gitops-after">
                    <span>After Payload (JSON)</span>
                  </label>
                  <div className="f-row">
                    <textarea
                      id="gitops-after"
                      className="output-textarea"
                      rows={5}
                      value={afterPayload}
                      onChange={(e) => setAfterPayload(e.target.value)}
                    />
                  </div>
                </div>
              </div>
              {diff ? (
                <fieldset className="min-w-0" role="none">
                  <div className="f-item">
                    <label htmlFor="gitops-actor">
                      <span>Actor</span>
                    </label>
                    <div className="f-row">
                      <input id="gitops-actor" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="username" />
                    </div>
                  </div>
                  <div className="f-item">
                    <label htmlFor="gitops-message">
                      <span>Commit Message</span>
                    </label>
                    <div className="f-row">
                      <input id="gitops-message" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Description of change" />
                    </div>
                  </div>
                </fieldset>
              ) : null}
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {diff ? <pre className="output-pre">{JSON.stringify(diff, null, 2)}</pre> : null}
              {commitResult ? <pre className="output-pre">{JSON.stringify(commitResult, null, 2)}</pre> : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={diffing} type="submit">
                  {diffing ? "…" : "Compute Diff"}
                </button>
                {diff && !commitResult ? (
                  <button className="btn btn-light-green btn-wide" onClick={runCommit} disabled={committing} type="button">
                    {committing ? "…" : "Commit"}
                  </button>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

const AGENT_COMMAND_KINDS = [
  "apply_config",
  "reload",
  "restart",
  "upgrade",
  "rollback",
  "collect_diagnostics",
  "provider_healthcheck",
] as const;

function AgentsPanel({ showNotice }: { showNotice: (m: string) => void }) {
  const [nodes, setNodes] = useState<NodeRead[]>([]);
  const [nodeId, setNodeId] = useState("");
  const [kind, setKind] = useState<string>(AGENT_COMMAND_KINDS[0]);
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listNodes().then((page) => {
      setNodes(page.items);
      if (page.items.length > 0) setNodeId(page.items[0].id);
    }).catch(() => {});
  }, []);

  const issue = async () => {
    if (!nodeId) { setError("Select a node."); return; }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(payload) as Record<string, unknown>;
    } catch {
      setError("Payload must be valid JSON.");
      return;
    }
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await issueAgentCommand(nodeId, { kind, payload: parsed });
      setResult(res);
      showNotice("Command issued.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        void issue();
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont" aria-labelledby="title">
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="agents-node">
                    <span>Node</span>
                  </label>
                  <div className="f-row">
                    <select
                      id="agents-node"
                      value={nodeId}
                      onChange={(e) => setNodeId(e.target.value)}
                    >
                      {nodes.map((n) => (
                        <option key={n.id} value={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item">
                  <label htmlFor="agents-kind">
                    <span>Command Kind</span>
                  </label>
                  <div className="f-row">
                    <select
                      id="agents-kind"
                      value={kind}
                      onChange={(e) => setKind(e.target.value)}
                    >
                      {AGENT_COMMAND_KINDS.map((k) => (
                        <option key={k} value={k}>{k}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </fieldset>
              <fieldset className="min-w-0" role="none">
                <div className="f-item f-item-stack">
                  <label htmlFor="agents-payload">
                    <span>Payload (JSON)</span>
                  </label>
                  <div className="f-row">
                    <textarea
                      id="agents-payload"
                      className="output-textarea"
                      rows={4}
                      value={payload}
                      onChange={(e) => setPayload(e.target.value)}
                    />
                  </div>
                </div>
              </fieldset>
              {error ? <div className="errorMessage" aria-live="polite">{error}</div> : null}
              {result ? <pre className="output-pre">{JSON.stringify(result, null, 2)}</pre> : null}
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" disabled={loading} type="submit">
                  {loading ? "…" : "Issue Command"}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

const OVERVIEW_DEFAULT_METRICS = [
  "Total Nodes",
  "Total Profiles",
  "Total Assignments",
  "Total Users",
  "Total Traffic",
  "Upload",
  "Download",
  "Metrics Collected",
];

function DashboardLayoutPanel({
  liveRows,
  layout,
  onClose,
  onSave,
}: {
  liveRows: Record<string, unknown>[];
  layout: { metric: string; visible: boolean }[];
  onClose: () => void;
  onSave: (layout: { metric: string; visible: boolean }[]) => void;
}) {
  const allMetrics = liveRows.length > 0
    ? liveRows.map((r) => String(r.metric ?? "")).filter(Boolean)
    : OVERVIEW_DEFAULT_METRICS;

  const initEntries = (): { metric: string; visible: boolean }[] => {
    const saved = layout.length > 0 ? layout : [];
    const savedMetrics = saved.map((e) => e.metric);
    const merged = saved.filter((e) => allMetrics.includes(e.metric));
    for (const m of allMetrics) {
      if (!savedMetrics.includes(m)) merged.push({ metric: m, visible: true });
    }
    return merged;
  };

  const [entries, setEntries] = useState<{ metric: string; visible: boolean }[]>(initEntries);

  const toggle = (metric: string) => {
    setEntries((prev) => prev.map((e) => e.metric === metric ? { ...e, visible: !e.visible } : e));
  };

  const move = (index: number, dir: -1 | 1) => {
    const next = index + dir;
    if (next < 0 || next >= entries.length) return;
    setEntries((prev) => {
      const arr = [...prev];
      const tmp = arr[index];
      arr[index] = arr[next];
      arr[next] = tmp;
      return arr;
    });
  };

  const reset = () => setEntries(OVERVIEW_DEFAULT_METRICS.map((m) => ({ metric: m, visible: true })));

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(entries);
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont">
              <div className="layout-panel-header">
                <span>Choose which metrics are visible and their order.</span>
              </div>
              <ul className="layout-metric-list">
                {entries.map((entry, idx) => (
                  <li key={entry.metric} className="layout-metric-row">
                    <label className="layout-metric-check">
                      <input
                        checked={entry.visible}
                        onChange={() => toggle(entry.metric)}
                        type="checkbox"
                      />
                      <span>{entry.metric}</span>
                    </label>
                    <span className="layout-metric-controls">
                      <button
                        className="btn btn-icon btn-outline"
                        disabled={idx === 0}
                        onClick={() => move(idx, -1)}
                        title="Move up"
                        type="button"
                      >
                        ▲
                      </button>
                      <button
                        className="btn btn-icon btn-outline"
                        disabled={idx === entries.length - 1}
                        onClick={() => move(idx, 1)}
                        title="Move down"
                        type="button"
                      >
                        ▼
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" type="submit">
                  Save Layout
                </button>
                <button className="btn btn-light-green btn-md" onClick={reset} type="button">
                  Reset
                </button>
                <button className="btn btn-red btn-md" onClick={onClose} type="button">
                  Cancel
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function AlertRulesPanel({
  liveRows,
  rules,
  onClose,
  onSave,
}: {
  liveRows: Record<string, unknown>[];
  rules: { id: string; metric: string; operator: "gt" | "lt"; threshold: number }[];
  onClose: () => void;
  onSave: (rules: { id: string; metric: string; operator: "gt" | "lt"; threshold: number }[]) => void;
}) {
  const allMetrics = liveRows.length > 0
    ? liveRows.map((r) => String(r.metric ?? "")).filter(Boolean)
    : OVERVIEW_DEFAULT_METRICS;

  const [localRules, setLocalRules] = useState(rules);
  const [newMetric, setNewMetric] = useState(allMetrics[0] ?? "");
  const [newOperator, setNewOperator] = useState<"gt" | "lt">("gt");
  const [newThreshold, setNewThreshold] = useState("");

  const addRule = () => {
    const t = Number(newThreshold);
    if (newThreshold.trim() === "" || Number.isNaN(t)) return;
    const rule = { id: `r-${Date.now()}`, metric: newMetric, operator: newOperator, threshold: t };
    setLocalRules((prev) => [...prev, rule]);
    setNewThreshold("");
  };

  const removeRule = (id: string) => setLocalRules((prev) => prev.filter((r) => r.id !== id));

  const breachStatus = (rule: { metric: string; operator: "gt" | "lt"; threshold: number }) => {
    const row = liveRows.find((r) => String(r.metric ?? "") === rule.metric);
    if (!row) return null;
    const raw = typeof row.raw === "number" ? row.raw : Number(row.value);
    if (Number.isNaN(raw)) return null;
    return rule.operator === "gt" ? raw > rule.threshold : raw < rule.threshold;
  };

  return (
    <form
      className="panel content-panel form--item-width"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(localRules);
      }}
    >
      <div className="form--panel-scroll custom-scrollbar">
        <div className="acc-list">
          <section className="acc">
            <div className="acc-cont">
              <div className="layout-panel-header">
                <span>Define threshold rules. A breached rule marks the metric row with an alert.</span>
              </div>
              {localRules.length > 0 ? (
                <table className="table metric-table alert-rules-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Operator</th>
                      <th>Threshold</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {localRules.map((rule) => {
                      const breached = breachStatus(rule);
                      return (
                        <tr key={rule.id} className={breached === true ? "row-alert" : ""}>
                          <td>{rule.metric}</td>
                          <td>{rule.operator === "gt" ? ">" : "<"}</td>
                          <td>{rule.threshold}</td>
                          <td>{breached === true ? "ALERT" : breached === false ? "OK" : "—"}</td>
                          <td>
                            <button
                              className="btn btn-red btn-md"
                              onClick={() => removeRule(rule.id)}
                              type="button"
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="muted-value">No alert rules defined.</div>
              )}
              <div className="alert-rule-add">
                <div className="f-item">
                  <label><span>Metric</span></label>
                  <div className="f-row">
                    <select value={newMetric} onChange={(e) => setNewMetric(e.target.value)}>
                      {allMetrics.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                </div>
                <div className="f-item">
                  <label><span>Operator</span></label>
                  <div className="f-row">
                    <select value={newOperator} onChange={(e) => setNewOperator(e.target.value as "gt" | "lt")}>
                      <option value="gt">greater than (&gt;)</option>
                      <option value="lt">less than (&lt;)</option>
                    </select>
                  </div>
                </div>
                <div className="f-item">
                  <label><span>Threshold</span></label>
                  <div className="f-row">
                    <input
                      placeholder="numeric value"
                      type="number"
                      value={newThreshold}
                      onChange={(e) => setNewThreshold(e.target.value)}
                    />
                  </div>
                </div>
                <div className="operation-row">
                  <button className="btn btn-light-green btn-md" onClick={addRule} type="button">
                    Add Rule
                  </button>
                </div>
              </div>
              <div className="operation-row">
                <button className="btn btn-dark-green btn-wide" type="submit">
                  Save Rules
                </button>
                <button className="btn btn-red btn-md" onClick={onClose} type="button">
                  Cancel
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </form>
  );
}

function CreateSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  const [open, setOpen] = useState(true);
  const areaId = `areaid-${title}`;
  const tabId = `tabid-${title}`;

  return (
    <section className={cx("acc create-section", !open && "folded")}>
      <h2 className="acc-title">
        <button
          aria-controls={areaId}
          aria-expanded={open}
          id={tabId}
          onClick={() => setOpen((isOpen) => !isOpen)}
          type="button"
        >
          <span>{title}</span>
        </button>
      </h2>
      {open ? (
        <div className="acc-cont create-section-content" id={areaId} aria-labelledby={tabId}>
          {children}
        </div>
      ) : null}
    </section>
  );
}

const TERMINAL_BANNER = [
  "",
  "  XX   XX  LL       III  NN    NN  KK   KK",
  "   XX XX   LL       III  NNN   NN  KK  KK",
  "    XXX    LL       III  NN NN NN  KKKK",
  "   XX XX   LL       III  NN   NNN  KK  KK",
  "  XX   XX  LLLLLLL  III  NN    NN  KK   KK",
  "",
  "  XLink Control Plane 0.1.0",
  "  Type 'help' for commands.",
  "",
];

const TERMINAL_HELP = [
  "Available commands:",
  "  help                 Show this help",
  "  whoami               Show the current user",
  "  nodes                List nodes",
  "  profiles             List profiles",
  "  assignments          List assignments",
  "  users                List users",
  "  traffic              Show traffic totals",
  "  monitoring           Show monitoring metrics",
  "  scheduler            List scheduler policies",
  "  clear                Clear the screen",
];

function fmtRow(cols: string[], widths: number[]): string {
  return cols.map((c, i) => c.padEnd(widths[i])).join("  ").trimEnd();
}

async function runTerminalCommand(raw: string): Promise<string[]> {
  const parts = raw.trim().split(/\s+/);
  const cmd = (parts[0] ?? "").toLowerCase();
  if (!cmd) return [];

  try {
    switch (cmd) {
      case "help":
        return TERMINAL_HELP;
      case "clear":
        return [" clear"];
      case "whoami": {
        const u = await currentUser();
        return [`${u.username} (${u.role}) <${u.email}>`];
      }
      case "nodes": {
        const page = await listNodes();
        if (!page.items.length) return ["No nodes."];
        const w = [22, 18, 6, 10];
        return [
          fmtRow(["NAME", "HOST", "PORT", "STATUS"], w),
          ...page.items.map((n) =>
            fmtRow([n.name, n.host, String(n.port), n.status], w),
          ),
        ];
      }
      case "profiles": {
        const page = await listProfiles();
        if (!page.items.length) return ["No profiles."];
        const w = [22, 10, 10, 8];
        return [
          fmtRow(["NAME", "PROVIDER", "PROTOCOL", "ACTIVE"], w),
          ...page.items.map((p) =>
            fmtRow([p.name, p.provider_kind, p.protocol, p.is_active ? "yes" : "no"], w),
          ),
        ];
      }
      case "assignments": {
        const page = await listAssignments();
        if (!page.items.length) return ["No assignments."];
        const w = [12, 12, 10, 10];
        return [
          fmtRow(["ASSIGN", "USER", "PROVIDER", "STATUS"], w),
          ...page.items.map((a) =>
            fmtRow([
              a.id.slice(0, 8),
              a.user_id.slice(0, 8),
              a.provider_kind,
              a.status,
            ], w),
          ),
        ];
      }
      case "users": {
        const page = await listUsers();
        if (!page.items.length) return ["No users."];
        const w = [16, 24, 8, 8];
        return [
          fmtRow(["USERNAME", "EMAIL", "ROLE", "ACTIVE"], w),
          ...page.items.map((u) =>
            fmtRow([u.username, u.email, u.role, u.is_active ? "yes" : "no"], w),
          ),
        ];
      }
      case "traffic": {
        const t = await trafficSummary();
        return [
          `total    ${t.total_bytes} bytes`,
          `upload   ${t.upload_bytes} bytes`,
          `download ${t.download_bytes} bytes`,
          `records  ${t.record_count}`,
        ];
      }
      case "monitoring": {
        const snap = await monitoringSummary();
        if (!snap.metrics.length) return ["No metrics."];
        return snap.metrics.map((m) => `${m.name} = ${m.value}`);
      }
      case "scheduler": {
        const policies = await schedulerPolicies();
        return ["Policies:", ...policies.map((p) => `  ${p}`)];
      }
      default:
        return [`Unknown command: ${cmd}. Type 'help'.`];
    }
  } catch (caught) {
    return [caught instanceof ApiError ? `Error: ${caught.message}` : "Error: request failed."];
  }
}

function TerminalView() {
  const [history, setHistory] = useState<string[]>(TERMINAL_BANNER);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [past, setPast] = useState<string[]>([]);
  const [pastIndex, setPastIndex] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [history]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const focusInput = (event: React.MouseEvent) => {
    if (window.getSelection()?.toString()) return;
    if (event.target instanceof HTMLInputElement) return;
    event.preventDefault();
    inputRef.current?.focus();
  };

  const submit = async () => {
    const line = input;
    setInput("");
    setPastIndex(null);
    if (line.trim()) setPast((p) => [...p, line]);
    const out = await (async () => {
      setBusy(true);
      try {
        return await runTerminalCommand(line);
      } finally {
        setBusy(false);
      }
    })();
    if (out.length === 1 && out[0] === " clear") {
      setHistory([]);
      return;
    }
    setHistory((h) => [...h, `[admin@xlink] > ${line}`, ...out]);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !busy) {
      event.preventDefault();
      void submit();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!past.length) return;
      const next = pastIndex === null ? past.length - 1 : Math.max(0, pastIndex - 1);
      setPastIndex(next);
      setInput(past[next]);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (pastIndex === null) return;
      const next = pastIndex + 1;
      if (next >= past.length) {
        setPastIndex(null);
        setInput("");
      } else {
        setPastIndex(next);
        setInput(past[next]);
      }
    }
  };

  return (
    <div className="terminal-shell">
      <h1 className="visually-hidden">Terminal</h1>
      <div aria-label="XLink terminal" className="terminal" onMouseDown={focusInput} ref={scrollRef} role="log">
        {history.map((line, index) => (
          <span key={`${line}-${index}`}>
            {line}
            {"\n"}
          </span>
        ))}
        <span className="terminal-prompt">
          {"[admin@xlink] > "}
          <input
            aria-label="Terminal command"
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
            autoFocus
            className="terminal-input"
            disabled={busy}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            ref={inputRef}
            spellCheck={false}
            value={input}
          />
        </span>
      </div>
      <div className="terminal-statusbar">
        {busy ? "Running…" : "Type 'help' · Press Shift + Tab to leave the terminal"}
      </div>
    </div>
  );
}

function SetupView({
  icon,
  pinned,
  setPinned,
  showNotice,
}: {
  icon: (name: string, className?: string) => ReactNode;
  pinned: boolean;
  setPinned: Dispatch<SetStateAction<boolean>>;
  showNotice: (message: string) => void;
}) {
  return (
    <div className="quickset">
      <div className="form-titlebar">
        {icon("icon-13.svg", "wndw-titlebar-icon icon")}
        <ul className="breadcrumbs">
          <li>
            <h1>XLink Setup</h1>
          </li>
          <li>
            <label>
              Template
              <select defaultValue="production">
                <option value="production">Production VPN Panel</option>
                <option value="staging">Staging Control Panel</option>
                <option value="single-node">Single Node Panel</option>
              </select>
            </label>
          </li>
        </ul>
        <button
          aria-pressed={pinned}
          className={cx("btn btn-icon btn-extra", pinned && "active")}
          onClick={() => {
            setPinned((isPinned) => !isPinned);
            showNotice(pinned ? "Setup unpinned." : "Setup pinned.");
          }}
          title="Pin view"
          type="button"
        >
          {icon("xlink-pin.svg", "icon icon-sm")}
        </button>
      </div>

      <div className="setup-content">
        <form className="setup-panel">
          <div className="setup-head">
            <div className="form-statusbar">
              <span>active</span>
            </div>
          </div>
          <div className="setup-grid">
            <div className="setup-row">
              <SetupSection title="Control Panel">
                <SetupField label="Public URL" value="https://xlink.local" />
                <SetupField label="JWT Algorithm" value="HS256" />
                <SetupField label="Rate Limiter" value="trusted proxy aware" />
                <SetupField label="Redis Strategy" value="fail-open configurable" />
              </SetupSection>
            </div>

            <div className="setup-row">
              <SetupSection title="Provider">
                <SetupField label="Default Provider" value="Xray" />
                <SetupField label="Protocols" value="VLESS, VMess, Trojan" />
                <SetupField label="Renderer Version" value="v1" />
                <SetupField label="Compatibility" value="provider-first" />
              </SetupSection>
            </div>

            <div className="setup-row">
              <SetupSection title="Nodes">
                <SetupField label="Heartbeat Timeout" value="60 seconds" />
                <SetupField label="Stats Sync" value="incremental batches" />
                <SetupField label="Assignment Sync" value="enabled" />
                <SetupField label="Node Auth" value="token hash" />
              </SetupSection>
            </div>

            <div className="setup-row">
              <SetupSection title="Subscriptions">
                <SetupField label="Cache TTL" value="300 seconds" />
                <SetupField label="Feed Hashing" value="enabled" />
                <SetupField label="ETag" value="enabled" />
                <SetupField label="Expiration Guard" value="enabled" />
              </SetupSection>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function SetupSection({ children, title }: { children: ReactNode; title: string }) {
  return (
    <details className="setup-section" open>
      <summary>{title}</summary>
      <div className="setup-section-content">{children}</div>
    </details>
  );
}

function SetupField({ label, value }: { label: string; value: string }) {
  return (
    <fieldset>
      <div className="form-item">
        <label>{label}</label>
        <div className="form-row">
          <input readOnly value={value} />
        </div>
      </div>
    </fieldset>
  );
}

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (username.trim().length === 0) {
      setError("Login is required.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await apiLogin(username.trim(), password);
      onLogin();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.status === 401 ? "Invalid login or password." : caught.message);
      } else {
        setError("Cannot reach the control plane.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login">
      <section>
        <div className="brand">
          <span className="brand-logo">XLink</span>
        </div>
        <form
          autoCapitalize="off"
          autoCorrect="off"
          className="form"
          id="login"
          onSubmit={submit}
        >
          <div className={cx("errorMessage", !error && "is-empty")}>{error}</div>
          <div>
            <label htmlFor="name">Login</label>
            <input
              autoComplete="username"
              autoFocus
              id="name"
              onChange={(event) => setUsername(event.target.value)}
              type="text"
              value={username}
            />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input
              autoComplete="current-password"
              id="password"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </div>
          <div>
            <input
              className="btn btn-dark-green"
              disabled={submitting}
              type="submit"
              value={submitting ? "..." : "Login"}
            />
          </div>
        </form>
        <div className="credits">
          <a href="#xlink">© XLink</a>
        </div>
      </section>
    </div>
  );
}
