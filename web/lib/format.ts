
const BYTES_PER_GIB = 1024 ** 3;

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

const DATE_LOCALE = "en-US";

export function formatDate(iso: string | number | Date): string {
  return new Date(iso).toLocaleDateString(DATE_LOCALE);
}

export function formatDateTime(iso: string | number | Date): string {
  return new Date(iso).toLocaleString(DATE_LOCALE);
}

