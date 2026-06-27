"use client";

import { useEffect, useMemo, useState } from "react";
import { NAV_ITEMS, SearchIcon } from "./nav";

export function CommandPalette({
  onSelect,
  open,
  onOpenChange,
}: {
  onSelect: (key: string) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const isOpen = open ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!isOpen);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, setOpen]);

  useEffect(() => {
    if (isOpen) {
      setQ("");
      setActive(0);
    }
  }, [isOpen]);

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return NAV_ITEMS.filter((i) => !needle || i.label.toLowerCase().includes(needle));
  }, [q]);

  if (!isOpen) return null;

  const choose = (key: string) => {
    onSelect(key);
    setOpen(false);
  };

  return (
    <div className="warp-cmd-overlay" onMouseDown={() => setOpen(false)} role="presentation">
      <div
        className="warp-cmd"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="warp-cmd-input">
          <SearchIcon aria-hidden size={14} />
          <input
            autoFocus
            value={q}
            placeholder="Jump to…"
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
              else if (e.key === "Enter" && items[active]) { e.preventDefault(); choose(items[active].key); }
            }}
          />
          <kbd className="warp-cmd-kbd">ESC</kbd>
        </div>
        <div className="warp-cmd-list" role="listbox">
          {items.length === 0 ? (
            <div className="warp-cmd-empty">No matches.</div>
          ) : (
            items.map((it, i) => {
              const ItemIcon = it.icon;
              return (
                <button
                  key={it.key}
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  className={`warp-cmd-item${i === active ? " is-active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(it.key)}
                >
                  <ItemIcon size={16} aria-hidden />
                  {it.label}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
