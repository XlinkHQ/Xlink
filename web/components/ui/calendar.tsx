"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const WD = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function Calendar({
  selected,
  onSelect,
}: {
  selected?: Date | null;
  onSelect: (d: Date) => void;
}) {
  const [view, setView] = useState<Date>(() => selected ?? new Date());
  const year = view.getFullYear();
  const month = view.getMonth();
  const today = new Date();

  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const cells: (Date | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="warp-cal">
      <div className="warp-cal-head">
        <button
          type="button"
          className="warp-cal-nav"
          onClick={() => setView(new Date(year, month - 1, 1))}
          aria-label="Previous month"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="warp-cal-title">
          {MONTHS[month]} {year}
        </span>
        <button
          type="button"
          className="warp-cal-nav"
          onClick={() => setView(new Date(year, month + 1, 1))}
          aria-label="Next month"
        >
          <ChevronRight size={16} />
        </button>
      </div>
      <div className="warp-cal-grid">
        {WD.map((w) => (
          <span key={w} className="warp-cal-wd">
            {w}
          </span>
        ))}
        {cells.map((d, i) =>
          d === null ? (
            <span key={`e${i}`} className="warp-cal-cell is-empty" />
          ) : (
            <button
              key={d.toISOString()}
              type="button"
              className={
                "warp-cal-cell" +
                (selected && sameDay(d, selected) ? " is-selected" : "") +
                (sameDay(d, today) ? " is-today" : "")
              }
              onClick={() => onSelect(d)}
            >
              {d.getDate()}
            </button>
          ),
        )}
      </div>
    </div>
  );
}

export function DatePicker({
  value,
  onChange,
  placeholder = "Pick a date",
}: {
  value: string;
  onChange: (iso: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = (() => {
    if (!value) return null;
    const [y, m, d] = value.split("-").map(Number);
    return y && m && d ? new Date(y, m - 1, d) : new Date(value);
  })();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const label = selected
    ? selected.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
    : placeholder;

  return (
    <div className="warp-datepick" ref={ref}>
      <button
        type="button"
        className={"warp-datepick-btn" + (selected ? "" : " is-placeholder")}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      {open ? (
        <div className="warp-datepick-pop">
          <Calendar
            selected={selected}
            onSelect={(d) => {
              const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
              onChange(iso);
              setOpen(false);
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
