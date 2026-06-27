"use client";

import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Menu, MoreHorizontal, Plus, Trash } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "@/lib/icons";
import { useTheme } from "@/lib/theme";

export type WarpMenuItem = {
  label: string;
  icon?: string;  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

export function WarpMenu({ items, label }: { items: WarpMenuItem[]; label?: string }) {
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

function SortArrow({ dir }: { dir?: "asc" | "desc" }) {
  return (
    <svg
      className={`warp-th-arrow${dir ? " is-active" : ""}${dir === "asc" ? " is-asc" : ""}`}
      width="12"
      height="12"
      viewBox="0 0 16 16"
      role="img"
      focusable="false"
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
    >
      <path d="M11.5361 10.2745C11.8024 10.0029 11.8249 9.56807 11.5762 9.26961C11.3275 8.97139 10.8961 8.91526 10.5811 9.12801L10.5195 9.17391L8.00001 11.2735L5.48048 9.17391L5.41895 9.12801C5.10388 8.91526 4.67252 8.97139 4.42384 9.26961C4.17512 9.56807 4.19758 10.0029 4.46387 10.2745L4.51954 10.3263L7.51954 12.8263C7.79767 13.058 8.20234 13.058 8.48048 12.8263L11.4805 10.3263L11.5361 10.2745Z" />
      <path d="M8.75 12.25C8.75 12.6642 8.41421 13 8 13C7.58579 13 7.25 12.6642 7.25 12.25L7.25 3.75C7.25 3.33579 7.58579 3 8 3C8.41421 3 8.75 3.33579 8.75 3.75V12.25Z" />
    </svg>
  );
}

export function WarpHead({
  cols,
  actions,
  sortKey,
  sortDir,
  onSort,
}: {
  cols: ReactNode[];
  actions?: boolean;
  sortKey?: number | null;
  sortDir?: "asc" | "desc";
  onSort?: (index: number) => void;
}) {
  return (
    <div className="warp-tb-head">
      {cols.map((c, i) => {
        const sortable = Boolean(onSort) && c != null && c !== "";
        const active = sortKey === i;
        if (!sortable) {
          return (
            <span key={i} className="warp-tb-cell">
              {c}
            </span>
          );
        }
        return (
          <span key={i} className="warp-tb-cell">
            <button
              type="button"
              className={`warp-th-btn${active ? " is-active" : ""}`}
              onClick={() => onSort?.(i)}
            >
              <span>{c}</span>
              <SortArrow dir={active ? sortDir : undefined} />
            </button>
          </span>
        );
      })}
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
  const theme = useTheme();
  const [ctx, setCtx] = useState<{ x: number; y: number } | null>(null);
  const clickTimer = useRef<number | null>(null);

  const openMenu = (e: React.MouseEvent) => {
    if (!menu || menu.length === 0) return;
    e.preventDefault();
    e.stopPropagation();
    if (clickTimer.current) { window.clearTimeout(clickTimer.current); clickTimer.current = null; }
    const W = 200;
    let x = e.clientX;
    if (x + W > window.innerWidth - 8) x = window.innerWidth - 8 - W;
    setCtx({ x: Math.max(8, x), y: e.clientY });
  };

  // Delay single-click (detail) so a double-click can cancel it and open the menu instead.
  const handleClick = () => {
    if (!onClick) return;
    if (!menu) { onClick(); return; }
    if (clickTimer.current) window.clearTimeout(clickTimer.current);
    clickTimer.current = window.setTimeout(() => { clickTimer.current = null; onClick(); }, 220);
  };

  return (
    <div
      className="warp-tb-row"
      onClick={handleClick}
      onDoubleClick={menu ? openMenu : undefined}
      onContextMenu={menu ? openMenu : undefined}
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
      {ctx && typeof document !== "undefined"
        ? createPortal(
            <div className={theme === "dark" ? "xlink-dark" : undefined}>
              <button
                type="button"
                aria-hidden
                tabIndex={-1}
                className="warp-menu-scrim"
                onClick={() => setCtx(null)}
                onContextMenu={(e) => { e.preventDefault(); setCtx(null); }}
              />
              <div
                role="menu"
                className="warp-menu-pop"
                style={{ top: ctx.y, left: ctx.x, right: "auto" }}
              >
                {menu?.map((it) => (
                  <button
                    key={it.label}
                    type="button"
                    role="menuitem"
                    disabled={it.disabled}
                    onClick={() => { setCtx(null); it.onClick(); }}
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
