"use client";

import { X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";



export function SettingsSection({
  icon: Icon,
  title,
  description,
  divider = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  divider?: boolean;
  children: ReactNode;
}) {
  return (
    <>
      {divider ? <div className="warp-ss-divider" /> : null}
      <section className="warp-ss-section">
        <span className="warp-ss-marker">
          <Icon size={20} strokeWidth={1.8} aria-hidden />
        </span>
        <div className="warp-ss-body">
          <div className="warp-ss-head">
            <h4 className="warp-ss-title">{title}</h4>
            {description ? <p className="warp-ss-desc">{description}</p> : null}
          </div>
          <div className="warp-ss-fields">{children}</div>
        </div>
      </section>
    </>
  );
}

export function InlineEditPanel({
  title,
  onClose,
  onSubmit,
  footer,
  children,
  className,
}: {
  title: string;
  onClose: () => void;
  onSubmit?: (e: FormEvent) => void;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  width?: string;
}) {
  const t = useT();
  return (
    <form
      onSubmit={onSubmit}
      className={cn("warp-settings-card mt-4 flex w-full flex-col overflow-hidden p-0", className)}
    >
      <div className="flex flex-none items-center justify-between border-b border-hairline px-5 py-4">
        <h3 className="text-base font-medium text-fg">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("action.close")}
          className="grid h-7 w-7 place-items-center rounded text-fg-muted transition-colors hover:bg-muted hover:text-fg"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex min-h-0 flex-col gap-3.5 p-5">{children}</div>
      {footer ? (
        <div className="flex flex-none justify-end gap-2 border-t border-hairline px-5 py-4">
          {footer}
        </div>
      ) : null}
    </form>
  );
}
