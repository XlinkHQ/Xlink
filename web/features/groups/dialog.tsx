"use client";

import { Check } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import { ApiError, createGroup, type GroupRead, type ProfileRead, updateGroup } from "@/lib/api";
import { Field } from "@/shared/parts";
import { InlineEditPanel } from "@/shared/settings-kit";
import { useT } from "@/lib/i18n";

export function GroupDialog({
  group,
  profiles,
  nodeName,
  onClose,
  onSaved,
  variant = "modal",
}: {
  group: GroupRead | null;
  profiles: ProfileRead[];
  nodeName: (id: string) => string;
  onClose: () => void;
  onSaved: () => void;
  variant?: "modal" | "inline";
}) {
  const t = useT();
  const [name, setName] = useState(group?.name ?? "");
  const [slug, setSlug] = useState(group?.slug ?? "");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(group?.profile_ids ?? []));
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const profile_ids = [...selected];
      if (group) {
        await updateGroup(group.id, { name: name.trim(), profile_ids });
      } else {
        await createGroup({
          name: name.trim(),
          slug: slug.trim() || name.trim().toLowerCase().replace(/\s+/g, "-"),
          profile_ids,
        });
      }
      toast("success", group ? t("groups.updated") : t("groups.created"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const title = group ? t("groups.editService") : t("groups.createService");
  const footer = (
    <>
      <Button type="button" variant="outline" onClick={onClose}>
        {t("action.cancel")}
      </Button>
      <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
        {busy ? t("common.saving") : group ? t("action.save") : t("groups.createService")}
      </Button>
    </>
  );
  const Shell = variant === "inline" ? InlineEditPanel : Modal;
  return (
    <Shell
      title={title}
      width="sm:w-[40rem]"
      onClose={onClose}
      onSubmit={submit}
      footer={footer}
    >
      <p className="warp-dlg-section-title">{t("groups.details")}</p>
      <div className="warp-dlg-2col">
        <Field label={t("common.name")} hint={t("groups.nameHint")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="EU bundle" />
        </Field>
        {!group ? (
          <Field label={t("groups.slug")} hint={t("groups.slugHint")}>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder={t("groups.slugPlaceholder")} />
          </Field>
        ) : null}
      </div>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">{t("groups.inbounds")}</p>
      <Field label={t("groups.inbounds")} hint={t("groups.inboundsHint")}>
        <div className="warp-dlg-chipbox">
          {profiles.length === 0 ? (
            <span className="text-[11px] text-fg-muted">{t("groups.noInboundsAvailable")}</span>
          ) : (
            profiles.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => toggle(p.id)}
                className={`warp-pin-chip ${selected.has(p.id) ? "is-on" : ""}`}
              >
                {selected.has(p.id) ? <Check size={10} aria-hidden /> : null}
                {p.name} · {p.protocol} @ {nodeName(p.node_id)}
              </button>
            ))
          )}
        </div>
      </Field>
    </Shell>
  );
}
