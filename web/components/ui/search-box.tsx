"use client";

import { useEffect, useRef, useState } from "react";
import { DgSearch } from "../console/dg-icons";
import { Kbd } from "./kbd";

export function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [isMac, setIsMac] = useState(true);

  useEffect(() => {
    setIsMac(/mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent));
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
        ref.current?.select();
      }
      if (e.key === "Escape" && document.activeElement === ref.current) {
        ref.current?.blur();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <span className="warp-tb-search-wrap warp-searchbox" style={{ maxWidth: 321, flex: 1 }}>
      <DgSearch size={16} />
      <input
        ref={ref}
        className="warp-tb-search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      <span className="warp-searchbox-kbd" aria-hidden>
        <Kbd>{isMac ? "⌘" : "Ctrl"}</Kbd>
        <Kbd>K</Kbd>
      </span>
    </span>
  );
}
