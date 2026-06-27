"use client";

import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Menu, MoreHorizontal, Plus, Trash } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "@/lib/icons";

export type WarpMenuItem = {
  label: string;
  icon?: string;  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

export function WarpMenu({ items, label }: { items: WarpMenuItem[]; label?: string }) {
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
          <Menu size={14} /> {label}
        </button>
      ) : (
        <button
          ref={btnRef}
          type="button"
          title="More options"
          className="warp-tb-rowicon"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <MoreHorizontal size={12} />
        </button>
      )}
      {open && typeof document !== "undefined"
        ? createPortal(
            <div className={document.querySelector(".xlink-dark") ? "xlink-dark" : undefined}>
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

export function WarpStatRow({ children }: { children: ReactNode }) {
  return <div className="warp-tb-stats">{children}</div>;
}

export function WarpStat({ label, value, tone = "green" }: { label: string; value: ReactNode; tone?: BadgeTone }) {
  return (
    <div className="warp-tb-stat">
      <h5>{label}:</h5>
      <WarpBadge tone={tone}>{value}</WarpBadge>
    </div>
  );
}

export function WarpTableCard({
  toolbar,
  search,
  children,
}: {
  toolbar?: ReactNode;
  search?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="warp-tb-card">
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

export function WarpIdCell({
  id,
  onDelete,
  onMore,
  menu,
}: {
  id: ReactNode;
  onDelete?: () => void;
  onMore?: () => void;
  menu?: WarpMenuItem[];
}) {
  return (
    <span className="warp-tb-idcell">
      {id}
      {onDelete ? (
        <button
          type="button"
          title="Delete"
          className="warp-tb-rowicon warp-tb-del"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          <Trash size={12} />
        </button>
      ) : null}
      {menu ? (
        <WarpMenu items={menu} />
      ) : onMore ? (
        <button
          type="button"
          title="More options"
          className="warp-tb-rowicon"
          onClick={(e) => {
            e.stopPropagation();
            onMore();
          }}
        >
          <MoreHorizontal size={12} />
        </button>
      ) : null}
    </span>
  );
}

type BadgeTone = "green" | "red" | "blue" | "orange" | "gray";
export function WarpBadge({ tone = "gray", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`warp-tb-badge ${tone}`}>{children}</span>;
}

export function WarpTraffic({
  pct,
  label,
  tone,
}: {
  pct: number;
  label: ReactNode;
  tone?: "default" | "unlimited" | "danger";
}) {
  const w = Math.min(100, Math.max(0, pct));
  return (
    <span className="warp-tb-traffic">
      <span className={cn("warp-tb-bar", tone === "unlimited" && "is-unlimited", tone === "danger" && "is-danger")}>
        <div style={{ width: `${w}%` }} />
      </span>
      <span className="warp-tb-traffic-val">{label}</span>
    </span>
  );
}

export function WarpRadial({
  pct,
  label,
  tone = "blue",
}: {
  pct: number;
  label: ReactNode;
  tone?: "blue" | "green" | "orange" | "red";
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
  icon?: string;  cta?: { label: string; onClick: () => void };
}) {
  return (
    <div className="warp-tb-empty">
      {icon ? <span className="warp-tb-empty-ico"><Icon name={icon} size={28} /></span> : null}
      <p className="warp-tb-empty-text">{children}</p>
      {cta ? (
        <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={cta.onClick}>
          <Plus size={14} /> {cta.label}
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
