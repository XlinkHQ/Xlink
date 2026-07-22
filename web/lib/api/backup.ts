import { ApiError, apiFetch, apiFetchRaw } from "./core";

export function exportBackup(body: Record<string, unknown> = {}) {
  return apiFetch<Record<string, unknown>>("/backup/export", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function importBackupDb(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetchRaw("/backup/import-db", { method: "POST", body: form });
  if (!res.ok) throw new ApiError(await res.text().catch(() => "Import failed"), res.status);
}

export async function downloadBackupDb(): Promise<void> {
  const res = await apiFetchRaw("/backup/export-db");
  if (!res.ok) throw new ApiError(await res.text().catch(() => "Export failed"), res.status);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? "xlink-db.dump";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
