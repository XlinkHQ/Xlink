import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "outline" | "ghost" | "danger" | "soft";
type Size = "sm" | "md" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:brightness-110",
  outline: "border border-hairline bg-surface text-fg hover:bg-muted",
  ghost: "bg-transparent text-fg hover:bg-muted",
  danger: "bg-danger text-white hover:brightness-110",
  soft: "bg-muted text-fg hover:bg-muted",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm gap-1.5",
  md: "h-10 px-4 py-2 text-sm gap-2",
  icon: "h-10 w-10 justify-center",
};

export function Button({
  variant = "soft",
  size = "md",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children?: ReactNode;
}) {
  return (
    <button
      className={cn(
        "inline-flex cursor-pointer items-center justify-center whitespace-nowrap rounded-md font-medium transition-[background-color,filter] disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
