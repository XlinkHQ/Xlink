"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import {
  ApiError,
  type ApiKey,
  createApiKey,
  enableApiKey,
  listApiKeys,
  purgeApiKey,
  revokeApiKey,
} from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { Copy, Plus, Trash } from "lucide-react";
import { Switch } from "./subscription-settings";

function relTime(iso: string | null): string {
  if (!iso) return "Never";
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function ApiKeysScreen() {
  const qc = useQueryClient();
  const q = useInfiniteQuery({
    queryKey: ["api-keys"],
    queryFn: ({ pageParam }) => listApiKeys({ limit: 50, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const keys = (q.data?.pages.flatMap((p) => p?.items ?? []).filter(Boolean) ?? []) as ApiKey[];
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<string | null>(null);

  const reload = () => qc.invalidateQueries({ queryKey: ["api-keys"] });

  const create = async () => {
    setBusy(true);
    try {
      const res = await createApiKey("");
      setFresh(res.token);
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not create key.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (k: ApiKey) => {
    if (!(await confirmDialog({ title: `Disable key "${k.name || k.prefix}"?`, message: "Any automation using it stops working.", confirmLabel: "Disable", danger: true }))) return;
    try {
      await revokeApiKey(k.id);
      toast("success", "Key disabled.");
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Disable failed.");
    }
  };

  const enable = async (k: ApiKey) => {
    try {
      await enableApiKey(k.id);
      toast("success", "Key enabled.");
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Enable failed.");
    }
  };

  const purge = async (k: ApiKey) => {
    if (!(await confirmDialog({ title: `Delete key "${k.name || k.prefix}"?`, message: "This permanently removes the key and cannot be undone.", confirmLabel: "Delete", danger: true }))) return;
    try {
      await purgeApiKey(k.id);
      toast("success", "Key deleted.");
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center justify-end">
        <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={create} disabled={busy}>
          <Plus size={14} /> {busy ? "Creating…" : "Create key"}
        </button>
      </div>

      {fresh ? (
        <div className="warp-key-reveal">
          <div className="warp-key-reveal-row">
            <code>{fresh}</code>
            <button
              type="button"
              className="warp-tb-button"
              onClick={() => {
                void copyText(fresh);
                toast("success", "API key copied.");
              }}
            >
              <Copy size={14} /> Copy
            </button>
            <button type="button" className="warp-tb-button" onClick={() => setFresh(null)}>
              Done
            </button>
          </div>
        </div>
      ) : null}

      <div className="-mx-4 w-[calc(100%+2rem)] overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="warp-thead text-left">
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Key</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Last used</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Created</th>
              <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-widest text-fg-muted">Status</th>
              <th className="w-16 px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-fg-muted">Loading…</td></tr>
            ) : keys.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-fg-muted">No API keys yet. Create one to automate the panel.</td></tr>
            ) : (
              keys.map((k) => (
                <tr key={k.id} className="hover:bg-muted">
                  <td className="px-4 py-2.5 warp-tb-mono text-xs font-medium text-fg">xlk_{k.prefix}…</td>
                  <td className="px-4 py-2.5 text-fg-muted">{relTime(k.last_used_at)}</td>
                  <td className="px-4 py-2.5 text-fg-muted">{new Date(k.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2.5">
                    <Switch
                      checked={!k.revoked_at}
                      onChange={(on) => (on ? enable(k) : revoke(k))}
                    />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button type="button" className="warp-tb-rowicon warp-tb-del" title="Delete" onClick={() => purge(k)}>
                      <Trash size={12} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {q.hasNextPage ? (
          <div className="mt-3 flex justify-center">
            <button
              type="button"
              className="warp-tb-button"
              onClick={() => q.fetchNextPage()}
              disabled={q.isFetchingNextPage}
            >
              {q.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
