"use client";

import { createContext, useContext, useEffect, useRef } from "react";

export type SaveReg = { fn: () => Promise<void> | void; busy: boolean } | null;

export const SettingsSaveContext = createContext<(reg: SaveReg) => void>(() => {});

export function useRegisterSave(fn: () => Promise<void> | void, busy = false): void {
  const register = useContext(SettingsSaveContext);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    register({ fn: () => fnRef.current(), busy });
    return () => register(null);
  }, [register, busy]);
}

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
