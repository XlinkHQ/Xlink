"use client";

import type { ReactNode } from "react";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="warp-field-row">
      <span className="warp-field-label">{label}</span>
      {children}
      {hint ? <span className="warp-field-helper">{hint}</span> : null}
    </label>
  );
}
