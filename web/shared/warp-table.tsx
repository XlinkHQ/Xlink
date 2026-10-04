"use client";

import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Menu, Plus, RotateCw, Trash } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon, type IconName } from "@/lib/icons";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

function DotsMenu({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden>
      <path
        d="M17 9.56C17 10.42 16.3 11.12 15.44 11.12C14.58 11.12 13.88 10.42 13.88 9.56C13.88 8.7 14.58 8 15.44 8C16.3 8 17 8.7 17 9.56ZM10 8C9.14 8 8.44 8.7 8.44 9.56C8.44 10.42 9.14 11.12 10 11.12C10.86 11.12 11.56 10.42 11.56 9.56C11.56 8.7 10.86 8 10 8ZM4.56 8C3.7 8 3 8.7 3 9.56C3 10.42 3.7 11.12 4.56 11.12C5.42 11.12 6.12 10.42 6.12 9.56C6.12 8.7 5.42 8 4.56 8Z"
        fill="currentColor"
      />
    </svg>
  );
}

export type WarpMenuItem = {
  label: string;
  icon?: IconName;  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

export function WarpMenu({ items, label }: { items: WarpMenuItem[]; label?: string }) {
  const t = useT();
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const update = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      const width = Math.min(192, Math.max(0, window.innerWidth - 20));
      let left = r.right - width;
      if (left < 8) left = 8;
      if (left + width > window.innerWidth - 8) left = window.innerWidth - 8 - width;
      left = Math.max(8, left);
      setPos({ top: r.bottom + 6, left });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  return (
    <span className="warp-menu" onClick={(e) => e.stopPropagation()}>
      {label ? (
        <button
          ref={btnRef}
          type="button"
          className="warp-tb-button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <Menu size={14} aria-hidden /> {label}
        </button>
      ) : (
        <button
          ref={btnRef}
          type="button"
          title={t("table.moreOptions")}
          aria-label={t("table.moreOptions")}
          className="warp-tb-rowicon"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <DotsMenu size={18} />
        </button>
      )}
      {open && typeof document !== "undefined"
        ? createPortal(
            <div className={theme === "dark" ? "xlink-dark" : undefined}>
              <button
                type="button"
                aria-hidden
                tabIndex={-1}
                className="warp-menu-scrim"
                onClick={() => setOpen(false)}
              />
              <div
                role="menu"
                className="warp-menu-pop"
                style={pos ? { top: pos.top, left: pos.left, right: "auto" } : { visibility: "hidden" }}
              >
                {items.map((it) => (
                  <button
                    key={it.label}
                    type="button"
                    role="menuitem"
                    disabled={it.disabled}
                    onClick={() => {
                      setOpen(false);
                      it.onClick();
                    }}
                    className={cn("warp-menu-item", it.danger && "is-danger")}
                  >
                    {it.icon ? <Icon name={it.icon} size={13} /> : null}
                    {it.label}
                  </button>
                ))}
              </div>
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

export function WarpTableCard({
  toolbar,
  search,
  children,
  className,
}: {
  toolbar?: ReactNode;
  search?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className ? `warp-tb-card ${className}` : "warp-tb-card"}>
      {toolbar ? <div className="warp-tb-toolbar">{toolbar}</div> : null}
      {search ? (
        <>
          <div className="warp-tb-divider" />
          <div className="warp-tb-searchbar">{search}</div>
        </>
      ) : null}
      <div className="warp-tb-scroll">{children}</div>
    </div>
  );
}

export function WarpButton({
  children,
  onClick,
  primary,
}: {
  children: ReactNode;
  onClick?: () => void;
  primary?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} className={cn("warp-tb-button", primary && "warp-tb-button-primary")}>
      {children}
    </button>
  );
}

export function WarpHead({ cols, actions }: { cols: ReactNode[]; actions?: boolean }) {
  return (
    <div className="warp-tb-head">
      {cols.map((c, i) => (
        <span key={i} className="warp-tb-cell">
          {c}
        </span>
      ))}
      {actions ? <span className="warp-tb-cell warp-tb-cell-actions" /> : null}
    </div>
  );
}

export function WarpRow({
  cells,
  onClick,
  menu,
}: {
  cells: ReactNode[];
  onClick?: () => void;
  menu?: WarpMenuItem[];
}) {
  return (
    <div
      className="warp-tb-row"
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {cells.map((c, i) => (
        <span key={i} className="warp-tb-cell">
          {c}
        </span>
      ))}
      {menu ? (
        <span className="warp-tb-cell warp-tb-cell-actions" onClick={(e) => e.stopPropagation()}>
          <WarpMenu items={menu} />
        </span>
      ) : null}
    </div>
  );
}

type BadgeTone = "green" | "red" | "blue" | "orange" | "gray" | "teal" | "violet" | "amber";
export function WarpBadge({ tone = "gray", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`warp-tb-badge ${tone}`}>{children}</span>;
}

export function WarpRadial({
  pct,
  label,
  tone = "blue",
}: {
  pct: number;
  label: ReactNode;
  tone?: "blue" | "green" | "red";
}) {
  const p = Math.min(100, Math.max(0, pct));
  const r = 9;
  const c = 2 * Math.PI * r;
  const off = c * (1 - p / 100);
  return (
    <span className="warp-radial">
      <svg width="24" height="24" viewBox="0 0 24 24" className="warp-radial-svg">
        <circle cx="12" cy="12" r={r} className="warp-radial-track" />
        <circle
          cx="12"
          cy="12"
          r={r}
          className={cn("warp-radial-fill", `is-${tone}`)}
          strokeDasharray={c}
          strokeDashoffset={off}
          transform="rotate(-90 12 12)"
        />
      </svg>
      <span className="warp-radial-label">{label}</span>
    </span>
  );
}

export function WarpEmpty({
  children,
  icon,
  cta,
}: {
  children: ReactNode;
  icon?: IconName;  cta?: { label: string; onClick: () => void };
}) {
  return (
    <div className="warp-tb-empty">
      {icon ? <span className="warp-tb-empty-ico"><Icon name={icon} size={28} /></span> : null}
      <p className="warp-tb-empty-text">{children}</p>
      {cta ? (
        <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={cta.onClick}>
          <Plus size={14} aria-hidden /> {cta.label}
        </button>
      ) : null}
    </div>
  );
}

export function WarpError({
  onRetry,
  message,
}: {
  onRetry?: () => void;
  message?: ReactNode;
}) {
  const t = useT();
  return (
    <div className="warp-tb-empty">
      <span className="warp-tb-empty-ico"><AlertTriangle size={28} aria-hidden /></span>
      <p className="warp-tb-empty-text">{message ?? t("common.loadFailed")}</p>
      {onRetry ? (
        <button type="button" className="warp-tb-button" onClick={onRetry}>
          <RotateCw size={14} aria-hidden /> {t("action.retry")}
        </button>
      ) : null}
    </div>
  );
}

export function WarpSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="warp-tb-skel">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="warp-tb-skel-row">
          <span className="warp-tb-skel-bar" style={{ width: "12%" }} />
          <span className="warp-tb-skel-bar" style={{ width: "28%" }} />
          <span className="warp-tb-skel-bar" style={{ width: "20%" }} />
          <span className="warp-tb-skel-bar" style={{ width: "16%" }} />
        </div>
      ))}
    </div>
  );
}
