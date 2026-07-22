
const BYTES_PER_GIB = 1024 ** 3;

// GiB <-> bytes for data-limit form fields. toGiB returns the raw number so each
// call site keeps its own formatting (.toFixed(0)/.toString()/.toFixed(1)) —
// behavior-identical to the inline `/ 1024 ** 3`. fromGiB matches the inline
// `Math.round(x * 1024 ** 3)` used on submit.
export function toGiB(bytesValue: number): number {
  return bytesValue / BYTES_PER_GIB;
}

export function fromGiB(gib: number): number {
  return Math.round(gib * BYTES_PER_GIB);
}

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

