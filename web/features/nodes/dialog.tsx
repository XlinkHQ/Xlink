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
import { useT } from "@/lib/i18n";

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
  const t = useT();
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
          throw new ApiError(t("nodes.metadataInvalidJson"), 400);
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
      toast("success", node ? t("nodes.nodeUpdated") : t("nodes.nodeCreated"));
      onSaved();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title={node ? t("nodes.editNode") : t("nodes.addNode")}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button type="submit" variant="primary" disabled={busy || !name.trim() || !host.trim()}>
            {busy ? t("common.saving") : node ? t("action.save") : t("action.create")}
          </Button>
        </>
      }
    >
      <Field label={t("common.name")}>
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="edge-fra-1" />
      </Field>
      {!node ? (
        <Field label={t("nodes.slug")}>
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder={t("nodes.slugPlaceholder")} />
        </Field>
      ) : null}
      <div className="warp-dlg-2col">
        <Field label={t("nodes.hostAddress")}>
          <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="51.20.12.13" />
        </Field>
        <Field label={t("nodes.port")}>
          <Input value={port} onChange={(e) => setPort(e.target.value)} inputMode="numeric" placeholder="443" />
        </Field>
        <Field label={t("nodes.usageCoefficient")} hint={t("nodes.usageCoefficientHint")}>
          <Input value={usageCoefficient} onChange={(e) => setUsageCoefficient(e.target.value)} inputMode="decimal" placeholder="1.0" />
        </Field>
        {node ? (
          <Field label={t("common.status")}>
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field label={t("nodes.region")} hint={t("nodes.regionHint")}>
          <Input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="eu-central" />
        </Field>
        <Field label={t("nodes.trafficLoad")} hint={t("nodes.trafficLoadHint")}>
          <Input value={trafficLoad} onChange={(e) => setTrafficLoad(e.target.value)} inputMode="decimal" placeholder="0.0 – 1.0" />
        </Field>
      </div>
      <Field label={t("nodes.advancedMetadata")}>
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
