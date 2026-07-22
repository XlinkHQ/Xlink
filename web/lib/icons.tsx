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

const ICONS = {
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
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

function resolveIcon(name: IconName): LucideIcon | null {
  return ICONS[name] ?? null;
}

export function Icon({ name, size = 14 }: { name?: IconName; size?: number }) {
  if (!name) return null;
  const Cmp = resolveIcon(name);
  return Cmp ? <Cmp size={size} /> : null;
}
