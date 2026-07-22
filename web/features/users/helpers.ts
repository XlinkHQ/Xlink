export function readPref(k: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(`xlink.${k}`); } catch { return null; }
}
export function writePref(k: string, v: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(`xlink.${k}`, v); } catch { /* ignore */ }
}

export function relTimeShort(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function initialsOf(name: string): string {
  const s = name.trim();
  if (!s) return "?";
  const parts = s.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return s.slice(0, 2).toUpperCase();
}
