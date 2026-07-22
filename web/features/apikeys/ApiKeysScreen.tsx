"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "@/components/ui/toast";
import { confirmDialog } from "@/components/ui/dialog";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { Field } from "@/shared/parts";
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
import { AlertTriangle, Copy } from "lucide-react";
import {
  WarpButton,
  WarpEmpty,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { DgAddUser } from "@/components/console/dg-icons";

function fmtDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleDateString();
}

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

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<string | null>(null);

  const reload = () => qc.invalidateQueries({ queryKey: ["api-keys"] });

  const openAdd = () => {
    setName("");
    setAdding(true);
  };

  const create = async () => {
    setBusy(true);
    try {
      const res = await createApiKey(name.trim());
      setAdding(false);
      setName("");
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
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">API keys</span>
        <div className="right">
          <WarpButton primary onClick={openAdd}>
            <DgAddUser size={16} /> Add key
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={["Name", "Last used", "Created"]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : keys.length === 0 ? (
          <WarpEmpty>
            No API keys yet. Create one to automate the panel.
          </WarpEmpty>
        ) : (
          keys.map((k) => (
            <WarpRow
              key={k.id}
              menu={[
                k.revoked_at
                  ? { label: "Enable", icon: "enable", onClick: () => enable(k) }
                  : { label: "Disable", icon: "disable", onClick: () => revoke(k) },
                { label: "Delete", icon: "trash", danger: true, onClick: () => purge(k) },
              ]}
              cells={[
                <span className="font-medium">{k.name || `xlk_${k.prefix}…`}</span>,
                <span className="text-fg-muted">{relTime(k.last_used_at)}</span>,
                <span className="text-fg-muted">{fmtDate(k.created_at)}</span>,
              ]}
            />
          ))
        )}
      </WarpTableCard>

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

      {adding ? (
        <Modal
          title="Add API key"
          onClose={() => setAdding(false)}
          onSubmit={(e) => {
            e.preventDefault();
            if (!busy) create();
          }}
          footer={
            <>
              <button type="button" className="warp-tb-button" onClick={() => setAdding(false)} disabled={busy}>
                Cancel
              </button>
              <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy}>
                {busy ? "Creating…" : "Create"}
              </button>
            </>
          }
        >
          <Field label="Name" hint="A label to recognise this key later.">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="CI deploy" autoFocus autoComplete="off" />
          </Field>
        </Modal>
      ) : null}

      {fresh ? (
        <Modal
          title="API key created"
          onClose={() => setFresh(null)}
          footer={
            <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setFresh(null)}>
              Close
            </button>
          }
        >
          <div className="warp-totp-banner">
            <AlertTriangle size={16} strokeWidth={1.9} aria-hidden />
            <span>Copy this key now — for security it is shown only once and can’t be retrieved later.</span>
          </div>
          <label className="warp-totp-field">
            <span className="warp-totp-label">API key</span>
            <button
              type="button"
              className="warp-totp-copy"
              title="Copy API key"
              onClick={() => {
                void copyText(fresh);
                toast("success", "API key copied.");
              }}
            >
              <code>{fresh}</code>
              <Copy size={16} strokeWidth={1.8} aria-hidden />
            </button>
          </label>
        </Modal>
      ) : null}
    </div>
  );
}
