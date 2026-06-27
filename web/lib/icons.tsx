import {
  ArchiveRestore,
  Ban,
  Download,
  Globe,
  Hash,
  Key,
  Layers,
  Link,
  type LucideIcon,
  Package,
  Pencil,
  Power,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Server,
  ShieldCheck,
  SquareCode,
  TimerReset,
  Trash,
  Unlink,
  User,
  Users,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  ban: Ban,
  download: Download,
  globe: Globe,
  hashtag: Hash,
  key: Key,
  "layer-group": Layers,
  link: Link,
  pen: Pencil,
  "power-off": Power,
  rotate: RotateCw,
  "rotate-left": RotateCcw,
  server: Server,
  "shield-halved": ShieldCheck,
  trash: Trash,
  user: User,
  "user-shield": ShieldCheck,
  users: Users,
  edit: Pencil,
  delete: Trash,
  disable: Ban,
  enable: Power,
  "reset-usage": TimerReset,
  restore: ArchiveRestore,
  refresh: RefreshCw,
  revoke: Unlink,
  "copy-id": Hash,
  "copy-link": SquareCode,
  package: Package,
};

export function resolveIcon(name: string): LucideIcon | null {
  return ICONS[name.replace(/^fa-/, "")] ?? null;
}

export function Icon({ name, size = 14 }: { name?: string; size?: number }) {
  if (!name) return null;
  const Cmp = resolveIcon(name);
  return Cmp ? <Cmp size={size} /> : null;
}
