"use client";

import { useEffect, useMemo, useRef } from "react";

type Token = { text: string; cls: string };

function tokenize(src: string): Token[] {
  const out: Token[] = [];
  const re =
    /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)|([{}[\],:])|(\s+)|([^\s{}[\],:"]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    if (m[1]) out.push({ text: m[1], cls: "jk" });
    else if (m[2]) out.push({ text: m[2], cls: "js" });
    else if (m[3]) out.push({ text: m[3], cls: "jn" });
    else if (m[4]) out.push({ text: m[4], cls: "jb" });
    else if (m[5]) out.push({ text: m[5], cls: "jp" });
    else if (m[6]) out.push({ text: m[6], cls: "" });
    else out.push({ text: m[0], cls: "" });
  }
  return out;
}

export function JsonEditor({
  value,
  onChange,
  rows = 14,
  disabled,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  disabled?: boolean;
  placeholder?: string;
}) {
  const tokens = useMemo(() => tokenize(value), [value]);
  const preRef = useRef<HTMLPreElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const pendingCaret = useRef<number | null>(null);
  useEffect(() => {
    if (pendingCaret.current !== null && taRef.current) {
      const pos = pendingCaret.current;
      taRef.current.selectionStart = taRef.current.selectionEnd = pos;
      pendingCaret.current = null;
    }
  }, [value]);
  return (
    <div className="warp-json-editor">
      <pre className="warp-json-pre" aria-hidden ref={preRef}>
        {tokens.map((t, i) =>
          t.cls ? (
            <span key={i} className={t.cls}>
              {t.text}
            </span>
          ) : (
            t.text
          ),
        )}
        {"\n"}
      </pre>
      <textarea
        ref={taRef}
        className="warp-json-ta"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          if (preRef.current) {
            preRef.current.scrollTop = e.currentTarget.scrollTop;
            preRef.current.scrollLeft = e.currentTarget.scrollLeft;
          }
        }}
        spellCheck={false}
        disabled={disabled}
        placeholder={placeholder}
        rows={rows}
        onKeyDown={(e) => {
          if (e.key === "Tab") {
            e.preventDefault();
            const ta = e.currentTarget;
            const s = ta.selectionStart;
            const en = ta.selectionEnd;
            const next = value.slice(0, s) + "  " + value.slice(en);
            pendingCaret.current = s + 2;
            onChange(next);
          }
        }}
      />
    </div>
  );
}
