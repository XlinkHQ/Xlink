"use client";

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

type Token = { text: string; cls: string };

function tokenizeHtml(src: string): Token[] {
  const out: Token[] = [];
  const re =
    /(<!--[\s\S]*?-->)|(<\/?)([a-zA-Z][\w-]*)|([a-zA-Z-]+)(=)("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\{\{\w+\}\})|(>)|(<)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  const push = (text: string, cls: string) => out.push({ text, cls });
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) push(src.slice(last, m.index), "");
    if (m[1]) push(m[1], "c-comment");
    else if (m[2]) {
      push(m[2], "c-punct");
      push(m[3], "c-tag");
    } else if (m[4]) {
      push(m[4], "c-attr");
      push(m[5], "c-punct");
      push(m[6], "c-string");
    } else if (m[7]) push(m[7], "c-ph");
    else if (m[8]) push(m[8], "c-punct");
    else if (m[9]) push(m[9], "c-punct");
    last = m.index + m[0].length;
  }
  if (last < src.length) push(src.slice(last), "");
  return out;
}

export function CodeEditor({
  value,
  onChange,
  rows = 16,
  placeholder,
  light,
}: {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
  light?: boolean;
}) {
  const tokens = useMemo(() => tokenizeHtml(value), [value]);
  const lineCount = useMemo(() => Math.max(1, value.split("\n").length), [value]);
  const preRef = useRef<HTMLPreElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [pendingCursorPos, setPendingCursorPos] = useState<number | null>(null);
  useEffect(() => {
    if (pendingCursorPos !== null && taRef.current) {
      taRef.current.selectionStart = taRef.current.selectionEnd = pendingCursorPos;
      setPendingCursorPos(null);
    }
  }, [value, pendingCursorPos]);
  const nodes: ReactNode[] = tokens.map((t, i) =>
    t.cls ? (
      <span key={i} className={t.cls}>
        {t.text}
      </span>
    ) : (
      <span key={i}>{t.text}</span>
    ),
  );
  return (
    <div className={`warp-code-editor warp-code-editor-gutter${light ? " is-light" : ""}`}>
      <div className="warp-code-lines" aria-hidden ref={gutterRef}>
        {Array.from({ length: lineCount }, (_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
      <pre className="warp-code-pre" aria-hidden ref={preRef}>
        {nodes}
        {"\n"}
      </pre>
      <textarea
        ref={taRef}
        className="warp-code-ta"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          if (preRef.current) {
            preRef.current.scrollTop = e.currentTarget.scrollTop;
            preRef.current.scrollLeft = e.currentTarget.scrollLeft;
          }
          if (gutterRef.current) {
            gutterRef.current.scrollTop = e.currentTarget.scrollTop;
          }
        }}
        spellCheck={false}
        placeholder={placeholder}
        rows={rows}
        onKeyDown={(e) => {
          if (e.key === "Tab") {
            e.preventDefault();
            const ta = e.currentTarget;
            const s = ta.selectionStart;
            const en = ta.selectionEnd;
            onChange(value.slice(0, s) + "  " + value.slice(en));
            setPendingCursorPos(s + 2);
          }
        }}
      />
    </div>
  );
}
