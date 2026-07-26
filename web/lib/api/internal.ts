import type { CursorPage } from "./core";


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
