import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return <kbd className={cn("warp-kbd", className)}>{children}</kbd>;
}
