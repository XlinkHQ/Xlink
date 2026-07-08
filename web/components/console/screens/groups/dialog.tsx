"use client";

import { Check } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import { ApiError, createGroup, type GroupRead, type ProfileRead, updateGroup } from "@/lib/api";
import { Field } from "../parts";
import { InlineEditPanel } from "../settings-kit";

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
      toast("success", group ? "Service updated." : "Service created.");
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  const title = group ? "Edit service" : "Create service";
  const footer = (
    <>
      <Button type="button" variant="outline" onClick={onClose}>
        Cancel
      </Button>
      <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
        {busy ? "Saving…" : group ? "Save" : "Create service"}
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
      <p className="warp-dlg-section-title">Details</p>
      <div className="warp-dlg-2col">
        <Field label="Name" hint="Shown to admins and in user access.">
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="EU bundle" />
        </Field>
        {!group ? (
          <Field label="Slug" hint="URL-safe id · auto from name.">
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="auto from name" />
          </Field>
        ) : null}
      </div>

      <div className="warp-dlg-divider" />
      <p className="warp-dlg-section-title">Inbounds</p>
      <Field label="Inbounds" hint="Members of this service grant these inbounds.">
        <div className="warp-dlg-chipbox">
          {profiles.length === 0 ? (
            <span className="text-[11px] text-fg-muted">No inbounds available.</span>
          ) : (
            profiles.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => toggle(p.id)}
                className={`warp-pin-chip ${selected.has(p.id) ? "is-on" : ""}`}
              >
                {selected.has(p.id) ? <Check size={10} /> : null}
                {p.name} · {p.protocol} @ {nodeName(p.node_id)}
              </button>
            ))
          )}
        </div>
      </Field>
    </Shell>
  );
}
