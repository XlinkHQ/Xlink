"use client";

import { useEffect, useRef, useState } from "react";

type ToastType = "success" | "error" | "info";
type Toast = { id: number; type: ToastType; message: string };

const EVENT = "xlink-toast";

export function toast(type: ToastType, message: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { type, message } }));
}

const TITLES: Record<ToastType, string> = {
  success: "Successful",
  error: "Unsuccessful",
  info: "Notice",
};

function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}
function IconClose() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function Toaster() {
  const [items, setItems] = useState<Toast[]>([]);
  const counter = useRef(0);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail as { type: ToastType; message: string };
      counter.current += 1;
      const t: Toast = { id: counter.current, type: detail.type, message: detail.message };
      setItems((s) => [...s, t]);
      window.setTimeout(() => setItems((s) => s.filter((x) => x.id !== t.id)), 4500);
    };
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
  }, []);

  const close = (id: number) => setItems((s) => s.filter((x) => x.id !== id));

  return (
    <div className="warp-toast-wrap">
      {items.map((t) => (
        <div key={t.id} className="warp-toast">
          <div>
            <span className={`warp-toast-ico ${t.type === "error" ? "warp-toast-x" : "warp-toast-check"}`}>
              {t.type === "error" ? <IconClose /> : <IconCheck />}
            </span>
            <div>
              <h4>{TITLES[t.type]}</h4>
              <p>{t.message}</p>
            </div>
          </div>
          <button type="button" aria-label="Close" onClick={() => close(t.id)}>
            <span><IconClose /></span>
          </button>
        </div>
      ))}
    </div>
  );
}
