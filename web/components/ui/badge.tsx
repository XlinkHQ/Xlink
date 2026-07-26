import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "online" | "offline" | "warning" | "error" | "success" | "info";
type Tone = "neutral" | "success" | "warning" | "danger" | "muted";
type ShadVariant = "default" | "secondary" | "destructive" | "outline";

const VARIANT_VAR: Record<Variant, string | null> = {
  online: "var(--green)",
  success: "var(--green)",
  warning: "var(--orange)",
  error: "var(--red)",
  info: "var(--primary)",
  offline: null,
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

const SHAD_CLASS: Record<ShadVariant, string> = {
  default: "warp-badge2 is-default",
  secondary: "warp-badge2 is-secondary",
  destructive: "warp-badge2 is-destructive",
  outline: "warp-badge2 is-outline",
};

export function Badge({
  variant,
  tone,
  dot = false,
  children,
  className,
}: {
  variant?: Variant | ShadVariant;
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  if (variant && variant in SHAD_CLASS) {
    return (
      <span className={cn(SHAD_CLASS[variant as ShadVariant], className)}>
        {dot ? <span className="warp-badge2-dot" /> : null}
        {children}
      </span>
    );
  }

  const v: Variant = (variant as Variant) ?? (tone ? TONE_TO_VARIANT[tone] : "info");
  const hue = VARIANT_VAR[v];
  const style: CSSProperties | undefined = hue
    ? { backgroundColor: `color-mix(in srgb, ${hue} 12%, transparent)`, color: hue }
    : undefined;
  return (
    <span
      className={cn(
        "inline-flex h-[18px] items-center gap-1.5 rounded-full px-2 text-[11px] font-medium",
        hue ? "" : "bg-muted text-fg-muted",
        className,
      )}
      style={style}
    >
      {dot ? (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: hue ?? "var(--body-muted)" }}
        />
      ) : null}
      {children}
    </span>
  );
}
