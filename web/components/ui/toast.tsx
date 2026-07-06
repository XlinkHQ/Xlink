"use client";

import { CircleCheck, CircleX, Info, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type ToastType = "success" | "error" | "info";
type Toast = { id: number; type: ToastType; message: string };

const EVENT = "xlink-toast";

export function toast(type: ToastType, message: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { type, message } }));
}

function VariantIcon({ type }: { type: ToastType }) {
  if (type === "error") return <CircleX strokeWidth={1.8} aria-hidden />;
  if (type === "info") return <Info strokeWidth={1.8} aria-hidden />;
  return <CircleCheck strokeWidth={1.8} aria-hidden />;
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
        <div key={t.id} className={`warp-toast warp-toast-${t.type}`} role="status">
          <div className="warp-toast-body">
            <span className="warp-toast-ico">
              <VariantIcon type={t.type} />
            </span>
            <div className="warp-toast-text">
              <p>{t.message}</p>
            </div>
          </div>
          <button type="button" aria-label="Close" onClick={() => close(t.id)}>
            <span>
              <X strokeWidth={1.8} aria-hidden />
            </span>
          </button>
        </div>
      ))}
    </div>
  );
}
