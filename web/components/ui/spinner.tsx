import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export function Spinner({
  size = 16,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return <Loader2 size={size} strokeWidth={2} className={cn("warp-spin", className)} aria-hidden />;
}
