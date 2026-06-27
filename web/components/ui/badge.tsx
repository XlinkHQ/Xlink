import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Variant = "online" | "offline" | "warning" | "error" | "success" | "info";
export type Tone = "neutral" | "success" | "warning" | "danger" | "muted";

const VARIANT_VAR: Record<Variant, string | null> = {
  online: "var(--green)",
  success: "var(--green)",
  warning: "var(--orange)",
  error: "var(--red)",
  info: "var(--primary)", // primary (blue)
  offline: null, // neutral grey
};

const TONE_TO_VARIANT: Record<Tone, Variant> = {
  success: "success",
  warning: "warning",
  danger: "error",
  neutral: "info",
  muted: "offline",
};

export function toneForStatus(status: string): Tone {
  const s = status.toLowerCase();
  if (["active", "online", "healthy", "ok", "yes", "server verified"].includes(s)) return "success";
  if (["expired", "expiring", "pending", "maintenance", "near expiry"].includes(s)) return "warning";
  if (["failed", "error", "alert", "sync error", "provider error", "unreachable"].includes(s))
    return "danger";
  if (["disabled", "offline", "no", "suspended"].includes(s)) return "muted";
  return "neutral";
}

export function variantForStatus(status: string): Variant {
  return TONE_TO_VARIANT[toneForStatus(status)];
}

export function Badge({
  variant,
  tone,
  dot = false,
  children,
  className,
}: {
  variant?: Variant;
  
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const v: Variant = variant ?? (tone ? TONE_TO_VARIANT[tone] : "info");
  const hue = VARIANT_VAR[v];
  const style: CSSProperties | undefined = hue
    ? { backgroundColor: `color-mix(in srgb, ${hue} 12%, transparent)`, color: hue }
    : undefined;
  return (
    <span
      className={cn(
        "inline-flex h-[25px] items-center gap-1.5 rounded-full border border-hairline px-2 text-xs font-medium",
        hue ? "" : "bg-muted text-fg-muted",
        className,
      )}
      style={style}
    >
      {dot ? (
        <span
          className="h-[9px] w-[9px] rounded-full"
          style={{ backgroundColor: hue ?? "var(--body-muted)" }}
        />
      ) : null}
      {children}
    </span>
  );
}
