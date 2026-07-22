import {
  ArchiveRestore,
  Ban,
  Check,
  Download,
  Hash,
  type LucideIcon,
  Pencil,
  Power,
  RefreshCw,
  SquareCode,
  TimerReset,
  Trash,
  Unlink,
  Wifi,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  check: Check,
  "copy-id": Hash,
  "copy-link": SquareCode,
  delete: Trash,
  disable: Ban,
  download: Download,
  edit: Pencil,
  enable: Power,
  ping: Wifi,
  refresh: RefreshCw,
  "reset-usage": TimerReset,
  restore: ArchiveRestore,
  revoke: Unlink,
  trash: Trash,
};

function resolveIcon(name: string): LucideIcon | null {
  return ICONS[name] ?? null;
}

export function Icon({ name, size = 14 }: { name?: string; size?: number }) {
  if (!name) return null;
  const Cmp = resolveIcon(name);
  return Cmp ? <Cmp size={size} /> : null;
}
