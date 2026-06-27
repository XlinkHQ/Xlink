"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function Avatar({
  name,
  online,
}: {
  name: string;
  online?: boolean;
}) {
  const initials =
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? "")
      .join("") || "?";
  return (
    <span className="relative inline-flex h-6 w-6 flex-none items-center justify-center rounded-full bg-primary text-[11px] font-medium text-primary-fg">
      {initials}
      {online != null ? (
        <span
          className={cn(
            "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-canvas",
            online ? "bg-success" : "bg-fg-muted",
          )}
        />
      ) : null}
    </span>
  );
}

export function Drawer({
  title,
  onClose,
  onEdit,
  children,
  width = "w-96",
  panelClassName = "bg-canvas",
}: {
  title: ReactNode;
  onClose: () => void;
  onEdit?: () => void;
  children: ReactNode;
  
  width?: string;
  
  panelClassName?: string;
}) {
  return (
    <div className="fixed inset-0 z-[55] flex justify-end bg-black/30" onMouseDown={onClose}>
      <aside
        onMouseDown={(e) => e.stopPropagation()}
        className={cn(
          "flex h-full max-w-full flex-col gap-4 overflow-auto border-l border-hairline p-5",
          panelClassName,
          width,
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-fg">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded text-fg-muted hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-col">{children}</div>
        {onEdit ? (
          <div className="mt-auto flex justify-end">
            <Button variant="primary" onClick={onEdit}>
              Edit
            </Button>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

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
    <label className="flex flex-col gap-1.5 text-sm font-medium text-fg">
      <span className="flex items-baseline justify-between gap-2">
        {label}
        {hint ? <span className="text-[11px] font-normal text-fg-muted">{hint}</span> : null}
      </span>
      {children}
    </label>
  );
}
