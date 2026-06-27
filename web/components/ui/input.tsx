import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const base =
  "h-10 w-full rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-fg outline-none transition-[border-color,box-shadow] placeholder:text-fg-muted focus:border-primary focus:shadow-focus-ring disabled:cursor-not-allowed disabled:bg-subtle disabled:text-fg-muted disabled:opacity-70";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(base, className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(base, "cursor-pointer", className)} {...props} />;
}
