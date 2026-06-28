"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { Info, TriangleAlert } from "lucide-react";

type ConfirmOptions = {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type PromptOptions = ConfirmOptions & {
  placeholder?: string;
  defaultValue?: string;
};

type SelectOption = { value: string; label: string; hint?: string; disabled?: boolean };

type SelectOptions = ConfirmOptions & {
  options: SelectOption[];
  defaultValue?: string;
  emptyLabel?: string;
};

type Request =
  | { id: number; kind: "confirm"; opts: ConfirmOptions; resolve: (v: boolean) => void }
  | { id: number; kind: "prompt"; opts: PromptOptions; resolve: (v: string | null) => void }
  | { id: number; kind: "select"; opts: SelectOptions; resolve: (v: string | null) => void };

const EVENT = "xlink-dialog";
let counter = 0;

export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  return new Promise((resolve) => {
    counter += 1;
    window.dispatchEvent(
      new CustomEvent(EVENT, { detail: { id: counter, kind: "confirm", opts, resolve } }),
    );
  });
}

export function promptDialog(opts: PromptOptions): Promise<string | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    counter += 1;
    window.dispatchEvent(
      new CustomEvent(EVENT, { detail: { id: counter, kind: "prompt", opts, resolve } }),
    );
  });
}

export function selectDialog(opts: SelectOptions): Promise<string | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    counter += 1;
    window.dispatchEvent(
      new CustomEvent(EVENT, { detail: { id: counter, kind: "select", opts, resolve } }),
    );
  });
}

export function DialogHost() {
  const [queue, setQueue] = useState<Request[]>([]);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const req = queue[0] ?? null;

  useEffect(() => {
    const handler = (event: Event) => {
      const r = (event as CustomEvent).detail as Request;
      setQueue((q) => [...q, r]);
    };
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
  }, []);

  useEffect(() => {
    if (req) {
      if (req.kind === "prompt" || req.kind === "select") setValue(req.opts.defaultValue ?? "");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [req]);

  if (!req) return null;

  const cancelValue = req.kind === "confirm" ? false : null;

  const close = (result: boolean | string | null) => {
    if (req.kind === "confirm") (req.resolve as (v: boolean) => void)(result as boolean);
    else (req.resolve as (v: string | null) => void)(result as string | null);
    setQueue((q) => q.slice(1));
    setValue("");
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") close(cancelValue);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (req.kind === "prompt") close(value);
    else if (req.kind === "select") {
      if (!value) return;
      close(value);
    } else close(true);
  };

  const o = req.opts;
  return (
    <div
      className="warp-confirm-overlay"
      onMouseDown={() => close(req.kind === "confirm" ? false : null)}
      role="presentation"
    >
      <form
        className="warp-confirm"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-label={o.title}
      >
        <div className="warp-confirm-head">
          {req.kind === "confirm" ? (
            <span className={`warp-confirm-icon ${o.danger ? "is-danger" : "is-info"}`}>
              {o.danger ? <TriangleAlert size={16} aria-hidden /> : <Info size={16} aria-hidden />}
            </span>
          ) : null}
          <div className="warp-confirm-headtext">
            <h4 className="warp-confirm-title">{o.title}</h4>
            {o.message ? <p className="warp-confirm-msg">{o.message}</p> : null}
          </div>
        </div>
        {req.kind === "prompt" ? (
          <input
            ref={inputRef}
            className="warp-confirm-input"
            value={value}
            placeholder={req.opts.placeholder}
            onChange={(e) => setValue(e.target.value)}
          />
        ) : null}
        {req.kind === "select" ? (
          <div className="warp-confirm-select" role="listbox" aria-label={o.title}>
            {req.opts.options.length === 0 ? (
              <p className="warp-confirm-msg">{req.opts.emptyLabel ?? "No options available."}</p>
            ) : (
              req.opts.options.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={value === opt.value}
                  disabled={opt.disabled}
                  className={`warp-confirm-option ${value === opt.value ? "is-selected" : ""} ${opt.disabled ? "is-disabled" : ""}`}
                  onClick={() => !opt.disabled && close(opt.value)}
                >
                  <span className="warp-confirm-option-label">{opt.label}</span>
                  {opt.hint ? <span className="warp-confirm-option-hint">{opt.hint}</span> : null}
                </button>
              ))
            )}
          </div>
        ) : null}
        <div className="warp-confirm-actions">
          <button type="button" className="warp-tb-button" onClick={() => close(cancelValue)}>
            {o.cancelLabel ?? "Cancel"}
          </button>
          {req.kind === "select" ? null : (
            <button
              type="submit"
              className={`warp-tb-button ${o.danger ? "warp-tb-button-danger" : "warp-tb-button-primary"}`}
            >
              {o.confirmLabel ?? "Confirm"}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
