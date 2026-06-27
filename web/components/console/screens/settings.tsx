"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { ApiError, restartPanel } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { ApiKeysScreen } from "./api-keys";
import { AuditLogScreen } from "./audit-log";
import { BackupScreen } from "./panels";
import { SecuritySettingsScreen } from "./security-settings";
import { SubscriptionSettingsScreen } from "./subscription-settings";

type SaveReg = { fn: () => Promise<void> | void; busy: boolean } | null;
const SettingsSaveContext = createContext<(reg: SaveReg) => void>(() => {});

export function useRegisterSave(fn: () => Promise<void> | void, busy = false): void {
  const register = useContext(SettingsSaveContext);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    register({ fn: () => fnRef.current(), busy });
    return () => register(null);
  }, [register, busy]);
}

const TABS: Array<{ key: string; label: string; Comp: () => React.JSX.Element }> = [
  { key: "subscription", label: "Subscription", Comp: SubscriptionSettingsScreen },
  { key: "security", label: "Security", Comp: SecuritySettingsScreen },
  { key: "backup", label: "Backup", Comp: BackupScreen },
  { key: "apikeys", label: "API Keys", Comp: ApiKeysScreen },
  { key: "audit", label: "Audit Log", Comp: AuditLogScreen },
];

export function SettingsRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="warp-set-row">
      <div className="warp-set-row-label">
        <h4>{label}</h4>
        {hint ? <p>{hint}</p> : null}
      </div>
      <div className="warp-set-row-control">{children}</div>
    </div>
  );
}

export function SettingsScreen() {
  const [tab, setTab] = useState("subscription");
  const Active = TABS.find((t) => t.key === tab)?.Comp ?? SubscriptionSettingsScreen;
  const [saveReg, setSaveReg] = useState<SaveReg>(null);

  const restart = async () => {
    try {
      await restartPanel();
      toast("success", "Panel is restarting…");
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Restart failed.");
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-set-topbar">
        {saveReg ? (
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            disabled={saveReg.busy}
            onClick={() => saveReg.fn()}
          >
            {saveReg.busy ? "Saving…" : "Save"}
          </button>
        ) : null}
        <button type="button" className="warp-tb-button warp-tb-button-danger" onClick={restart}>
          Restart Panel
        </button>
      </div>

      <div className="warp-set-card">
        <div className="warp-set-menu">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(t.key === tab && "warp-set-active")}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="warp-set-body">
          <SettingsSaveContext.Provider value={setSaveReg}>
            <Active />
          </SettingsSaveContext.Provider>
        </div>
      </div>
    </div>
  );
}
