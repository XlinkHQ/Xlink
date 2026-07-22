"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { toast } from "@/components/ui/toast";
import { ApiError, createNode, type NodeRead, setNodeStatus, updateNode } from "@/lib/api";
import { Field } from "@/shared/parts";
import { InlineEditPanel } from "@/shared/settings-kit";
import { STATUSES } from "./util";

export function NodeDialog({
  node,
  onClose,
  onSaved,
  variant = "modal",
}: {
  node: NodeRead | null;
  onClose: () => void;
  onSaved: () => void;
  variant?: "modal" | "inline";
}) {
  const Shell = variant === "inline" ? InlineEditPanel : Modal;
  const [name, setName] = useState(node?.name ?? "");
  const [slug, setSlug] = useState(node?.slug ?? "");
  const [host, setHost] = useState(node?.host ?? "");
  const [port, setPort] = useState(String(node?.port ?? 443));
  const [usageCoefficient, setUsageCoefficient] = useState(
    String(node?.usage_coefficient ?? 1),
  );
  const [status, setStatus] = useState(node?.status ?? "active");
  const md = (node?.metadata ?? {}) as Record<string, unknown>;
  const [region, setRegion] = useState(md.region != null ? String(md.region) : "");
  const [trafficLoad, setTrafficLoad] = useState(
    md.traffic_load != null ? String(md.traffic_load) : "",
  );
  const [meta, setMeta] = useState(() => {
    const rest = Object.fromEntries(
      Object.entries(md).filter(([k]) => k !== "region" && k !== "traffic_load"),
    );
    return Object.keys(rest).length > 0 ? JSON.stringify(rest, null, 2) : "";
  });
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      let metadata: Record<string, unknown> = {};
      if (meta.trim()) {
        try {
          metadata = JSON.parse(meta);
        } catch {
          throw new ApiError("Metadata must be valid JSON.", 400);
        }
      }
      if (region.trim()) metadata.region = region.trim();
      if (trafficLoad.trim() !== "" && !Number.isNaN(Number(trafficLoad))) metadata.traffic_load = Number(trafficLoad);
      const coeff = Number(usageCoefficient);
      const portNum = Number(port);
      const body: Record<string, unknown> = {
        name: name.trim(),
        host: host.trim(),
        port: portNum > 0 && Number.isInteger(portNum) ? portNum : 443,
        usage_coefficient: Number.isFinite(coeff) && coeff > 0 ? coeff : 1,
        metadata,
      };
      if (node) {
        await updateNode(node.id, body);
        if (status !== node.status) await setNodeStatus(node.id, status);
      } else {
        body.max_users = 1_000_000;
        body.slug =
          slug.trim() ||
          name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") ||
          "node";
        await createNode(body);
      }
      toast("success", node ? "Node updated." : "Node created.");
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title={node ? "Edit Node" : "Add Node"}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={busy || !name.trim() || !host.trim()}>
            {busy ? "Saving…" : node ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <Field label="Name">
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="edge-fra-1" />
      </Field>
      {!node ? (
        <Field label="Slug">
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="auto from name" />
        </Field>
      ) : null}
      <div className="warp-dlg-2col">
        <Field label="Host / Address">
          <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="51.20.12.13" />
        </Field>
        <Field label="Port">
          <Input value={port} onChange={(e) => setPort(e.target.value)} inputMode="numeric" placeholder="443" />
        </Field>
        <Field label="Usage Coefficient" hint="1.0 = neutral">
          <Input value={usageCoefficient} onChange={(e) => setUsageCoefficient(e.target.value)} inputMode="decimal" placeholder="1.0" />
        </Field>
        {node ? (
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field label="Region" hint="used by the scheduler">
          <Input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="eu-central" />
        </Field>
        <Field label="Traffic Load" hint="scoring weight hint">
          <Input value={trafficLoad} onChange={(e) => setTrafficLoad(e.target.value)} inputMode="decimal" placeholder="0.0 – 1.0" />
        </Field>
      </div>
      <Field label="Advanced Metadata (JSON)">
        <textarea
          value={meta}
          onChange={(e) => setMeta(e.target.value)}
          placeholder='{ "api_port": 62051 }'
          className="h-24 w-full resize-y rounded border border-hairline bg-transparent p-2.5 font-mono text-[11px] text-fg outline-none focus:border-primary"
        />
      </Field>
    </Shell>
  );
}
