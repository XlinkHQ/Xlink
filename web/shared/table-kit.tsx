"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { copyText } from "@/lib/clipboard";

export function CopyValue({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        const ok = await copyText(value);
        if (!ok) return;
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex max-w-full items-center gap-1.5 text-fg-muted transition-colors hover:text-fg"
      title="Copy"
    >
      <span className="truncate font-mono text-[11px] text-fg">{label ?? value}</span>
      {copied ? (
        <Check className="h-3 w-3 flex-none text-success" aria-hidden />
      ) : (
        <Copy className="h-3 w-3 flex-none" aria-hidden />
      )}
    </button>
  );
}
