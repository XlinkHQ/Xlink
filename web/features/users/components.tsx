"use client";

import { ChevronDown, ChevronUp } from "lucide-react";

export type SortCol = "name" | "username" | "email" | "online" | "status" | "traffic" | "expiration";
export type SortDir = "asc" | "desc";
export type BadgeVariant = "success" | "critical" | "neutral" | "warning" | "info";

export function Badge({ variant, children }: { variant: BadgeVariant; children: React.ReactNode }) {
  return <span className={`warp-badge ${variant}`}>{children}</span>;
}

export function UserNameCell({ name, online }: { name: string; online: boolean }) {
  return (
    <span className="warp-user-namecell">
      <span
        className={`warp-user-online-dot ${online ? "is-on" : "is-off"}`}
        aria-label={online ? "online" : "offline"}
        title={online ? "Online" : "Offline"}
      />
      <span className="warp-user-name">{name}</span>
    </span>
  );
}

export function SortTh({
  col,
  label,
  sortCol,
  sortDir,
  onSort,
}: {
  col: SortCol;
  label: string;
  sortCol: SortCol | null;
  sortDir: SortDir;
  onSort: (c: SortCol) => void;
}) {
  const active = sortCol === col;
  return (
    <button type="button" className={`warp-th-sort${active ? " is-active" : ""}`} onClick={() => onSort(col)}>
      <span>{label}</span>
      {active ? (
        sortDir === "asc" ? <ChevronUp size={13} strokeWidth={2} aria-hidden /> : <ChevronDown size={13} strokeWidth={2} aria-hidden />
      ) : null}
    </button>
  );
}

export function PdRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="warp-pd-row">
      <span className="warp-pd-row-label">{label}</span>
      <span className="warp-pd-row-value">{value}</span>
    </div>
  );
}

export function FactorRow({
  icon,
  title,
  availability,
  badge,
}: {
  icon: React.ReactNode;
  title: string;
  availability: string;
  badge: React.ReactNode;
}) {
  return (
    <div className="warp-pd-factor">
      <div className="track">
        <div className="info">
          {icon}
          <p className="factor-name">{title}</p>
          <div className="badges">{badge}</div>
        </div>
        <div className="avail-line">
          <div className="fill" />
          <p className="availability">{availability}</p>
        </div>
      </div>
    </div>
  );
}
