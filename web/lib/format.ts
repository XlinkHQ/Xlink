
export function bytes(v: number): string {
  if (!Number.isFinite(v) || v < 0) return "0 B";
  if (v < 1024) return `${v} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let size = v / 1024;
  let i = 0;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i += 1;
  }
  return `${size.toFixed(1)} ${units[i]}`;
}
