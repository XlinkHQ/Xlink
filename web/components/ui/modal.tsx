import { X } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Modal({
  title,
  onClose,
  onSubmit,
  footer,
  children,
  width = "sm:w-[34rem]",
}: {
  title: string;
  onClose: () => void;
  onSubmit?: (e: FormEvent) => void;
  footer?: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  return (
    <div
      className="warp-modal-overlay fixed inset-0 z-[700] grid place-items-end justify-center bg-black/40 p-0 backdrop-blur-sm sm:place-items-center sm:p-4"
      onMouseDown={onClose}
    >
      <form
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={onSubmit}
        className={cn(
          "warp-modal-panel flex max-h-[92vh] w-full max-w-[100vw] flex-col overflow-hidden rounded-t-2xl bg-canvas shadow-pop sm:max-w-[95vw] sm:rounded-xl",
          width,
        )}
      >
        <div className="flex flex-none items-center justify-between border-b border-hairline px-5 py-4 sm:px-6">
          <h3 className="text-base font-semibold text-fg">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-9 w-9 place-items-center rounded text-fg-muted transition-colors hover:bg-muted hover:text-fg sm:h-7 sm:w-7"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div
          className="flex min-h-0 flex-col gap-3.5 overflow-auto p-4 sm:p-5"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
        >
          {children}
        </div>
        {footer ? (
          <div
            className="flex flex-none justify-end gap-2 border-t border-hairline px-5 py-4 sm:px-6"
            style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
          >
            {footer}
          </div>
        ) : null}
      </form>
    </div>
  );
}
