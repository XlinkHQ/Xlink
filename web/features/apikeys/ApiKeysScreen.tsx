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
  WarpError,
  WarpHead,
  WarpRow,
  WarpSkeleton,
  WarpTableCard,
} from "@/shared/warp-table";
import { DgAddUser } from "@/components/console/dg-icons";
import { type TranslateFn, useT } from "@/lib/i18n";

function fmtDate(iso: string | null, t: TranslateFn): string {
  if (!iso) return t("common.never");
  return new Date(iso).toLocaleDateString();
}

function relTime(iso: string | null, t: TranslateFn): string {
  if (!iso) return t("common.never");
  const s = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return t("common.secondsAgo", { n: s });
  if (s < 3600) return t("common.minutesAgo", { n: Math.floor(s / 60) });
  if (s < 86400) return t("common.hoursAgo", { n: Math.floor(s / 3600) });
  return new Date(iso).toLocaleDateString();
}

export function ApiKeysScreen() {
  const t = useT();
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
      toast("error", e instanceof ApiError ? e.message : t("apikeys.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (k: ApiKey) => {
    if (!(await confirmDialog({ title: t("apikeys.disableConfirmTitle", { name: k.name || k.prefix }), message: t("apikeys.disableConfirmMessage"), confirmLabel: t("apikeys.disable"), danger: true }))) return;
    try {
      await revokeApiKey(k.id);
      toast("success", t("apikeys.keyDisabled"));
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("apikeys.disableFailed"));
    }
  };

  const enable = async (k: ApiKey) => {
    try {
      await enableApiKey(k.id);
      toast("success", t("apikeys.keyEnabled"));
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("apikeys.enableFailed"));
    }
  };

  const purge = async (k: ApiKey) => {
    if (!(await confirmDialog({ title: t("apikeys.deleteConfirmTitle", { name: k.name || k.prefix }), message: t("apikeys.deleteConfirmMessage"), confirmLabel: t("action.delete"), danger: true }))) return;
    try {
      await purgeApiKey(k.id);
      toast("success", t("apikeys.keyDeleted"));
      reload();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("apikeys.deleteFailed"));
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="warp-table-top">
        <span className="title">{t("apikeys.title")}</span>
        <div className="right">
          <WarpButton primary onClick={openAdd}>
            <DgAddUser size={16} /> {t("apikeys.addKey")}
          </WarpButton>
        </div>
      </div>

      <WarpTableCard className="warp-users-table">
        <WarpHead cols={[t("common.name"), t("apikeys.lastUsed"), t("common.created")]} actions />
        {q.isLoading ? (
          <WarpSkeleton />
        ) : q.isError ? (
          <WarpError onRetry={() => q.refetch()} />
        ) : keys.length === 0 ? (
          <WarpEmpty>
            {t("apikeys.noKeys")}
          </WarpEmpty>
        ) : (
          keys.map((k) => (
            <WarpRow
              key={k.id}
              menu={[
                k.revoked_at
                  ? { label: t("action.enable"), icon: "enable", onClick: () => enable(k) }
                  : { label: t("action.disable"), icon: "disable", onClick: () => revoke(k) },
                { label: t("action.delete"), icon: "trash", danger: true, onClick: () => purge(k) },
              ]}
              cells={[
                <span className="font-medium">{k.name || `xlk_${k.prefix}…`}</span>,
                <span className="text-fg-muted">{relTime(k.last_used_at, t)}</span>,
                <span className="text-fg-muted">{fmtDate(k.created_at, t)}</span>,
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
            {q.isFetchingNextPage ? t("common.loading") : t("common.loadMore")}
          </button>
        </div>
      ) : null}

      {adding ? (
        <Modal
          title={t("apikeys.addKeyTitle")}
          onClose={() => setAdding(false)}
          onSubmit={(e) => {
            e.preventDefault();
            if (!busy) create();
          }}
          footer={
            <>
              <button type="button" className="warp-tb-button" onClick={() => setAdding(false)} disabled={busy}>
                {t("action.cancel")}
              </button>
              <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy}>
                {busy ? t("common.creating") : t("action.create")}
              </button>
            </>
          }
        >
          <Field label={t("common.name")} hint={t("apikeys.nameHint")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("apikeys.namePlaceholder")} autoFocus autoComplete="off" />
          </Field>
        </Modal>
      ) : null}

      {fresh ? (
        <Modal
          title={t("apikeys.createdTitle")}
          onClose={() => setFresh(null)}
          footer={
            <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={() => setFresh(null)}>
              {t("action.close")}
            </button>
          }
        >
          <div className="warp-totp-banner">
            <AlertTriangle size={16} strokeWidth={1.9} aria-hidden />
            <span>{t("apikeys.copyOnceWarning")}</span>
          </div>
          <label className="warp-totp-field">
            <span className="warp-totp-label">{t("apikeys.apiKey")}</span>
            <button
              type="button"
              className="warp-totp-copy"
              title={t("apikeys.copyApiKey")}
              onClick={() => {
                void copyText(fresh);
                toast("success", t("apikeys.apiKeyCopied"));
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
