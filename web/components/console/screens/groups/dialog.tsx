"use client";

import { Check, ChevronDown } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "@/components/ui/toast";
import { ApiError, createGroup, type GroupRead, type ProfileRead, updateGroup } from "@/lib/api";
import { cn } from "@/lib/cn";

export function GroupDialog({
  group,
  profiles,
  nodeName,
  onClose,
  onSaved,
}: {
  group: GroupRead | null;
  profiles: ProfileRead[];
  nodeName: (id: string) => string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(group?.name ?? "");
  const [slug, setSlug] = useState(group?.slug ?? "");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(group?.profile_ids ?? []));
  const [pickerOpen, setPickerOpen] = useState(false);
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

  return (
    <div className="warp-dlg-overlay" onMouseDown={onClose}>
      <form className="warp-dlg" onMouseDown={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="warp-dlg-header">
          <span className="warp-dlg-grab" />
          <p>{group ? "Edit Service" : "Create Service"}</p>
        </div>

        <div className="warp-dlg-body">
          <div className="warp-dlg-field">
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="EU bundle" />
          </div>
          {!group ? (
            <div className="warp-dlg-field">
              <label>Slug</label>
              <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="auto from name" />
            </div>
          ) : null}

          <div className="warp-dlg-field" style={{ alignItems: "flex-start" }}>
            <label>Inbounds</label>
            <div className="warp-dlg-picker">
              <button
                type="button"
                className="warp-dlg-picker-trigger"
                onClick={() => setPickerOpen((o) => !o)}
              >
                <span className="truncate">
                  {selected.size === 0 ? "Select inbounds" : `${selected.size} selected`}
                </span>
                <ChevronDown size={14} style={{ transform: pickerOpen ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
              </button>
              {pickerOpen ? (
                <div className="warp-dlg-picker-list">
                  {profiles.length === 0 ? (
                    <p className="px-2 py-2 text-xs text-fg-muted">No inbounds available.</p>
                  ) : (
                    profiles.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => toggle(p.id)}
                        className={cn("warp-dlg-picker-item", selected.has(p.id) && "is-sel")}
                      >
                        <span className="warp-dlg-check">{selected.has(p.id) ? <Check size={14} /> : null}</span>
                        <span className="truncate">{p.name} · {p.protocol} @ {nodeName(p.node_id)}</span>
                      </button>
                    ))
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="warp-dlg-footer">
          <button type="button" className="warp-tb-button" onClick={onClose}>Cancel</button>
          <button type="submit" className="warp-tb-button warp-tb-button-primary" disabled={busy || !name.trim()}>
            {busy ? "Saving…" : group ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
