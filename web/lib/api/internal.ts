import type { CursorPage } from "./core";

// Internal helpers shared across domain modules. NOT re-exported from the
// barrel (@/lib/api) — these are implementation details, not public API.

export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

// The backend clamps page size to max_page_size (100), so "give me everything"
// callers must walk the cursor. Capped so a huge install can't spin forever.
const MAX_LIST_PAGES = 50;

export async function fetchAllPages<T>(
  page: (cursor?: string) => Promise<CursorPage<T>>,
  what: string,
): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < MAX_LIST_PAGES; i += 1) {
    const res = await page(cursor);
    items.push(...res.items);
    if (!res.next_cursor) return items;
    cursor = res.next_cursor;
  }
  console.warn(
    `${what}: stopped after ${MAX_LIST_PAGES} pages (${items.length} items); list may be incomplete.`,
  );
  return items;
}
