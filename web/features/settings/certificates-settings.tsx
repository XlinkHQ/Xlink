"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { confirmDialog } from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import {
  deleteCertificate,
  importCertificate,
  listCertificates,
  requestAcmeCertificate,
  ApiError,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { SettingsSection } from "@/shared/settings-kit";
import { WarpError } from "@/shared/warp-table";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

function daysLeft(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86400000);
}

export function CertificatesSettingsScreen() {
  const t = useT();
  const qc = useQueryClient();
  const certsQ = useQuery({ queryKey: ["managed-certs"], queryFn: () => listCertificates() });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [acmeOpen, setAcmeOpen] = useState(false);

  const certs = certsQ.data ?? [];

  const remove = async (id: string, domain: string) => {
    if (
      !(await confirmDialog({
        title: t("certificates.deleteConfirmTitle", { domain }),
        message: t("certificates.deleteConfirmMessage"),
        confirmLabel: t("action.delete"),
        danger: true,
      }))
    )
      return;
    try {
      await deleteCertificate(id);
      toast("success", t("certificates.deleted"));
      qc.invalidateQueries({ queryKey: ["managed-certs"] });
      qc.invalidateQueries({ queryKey: ["cert-inventory"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("certificates.deleteFailed"));
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={ShieldCheck}
        title={t("certificates.title")}
        description={t("certificates.description")}
      >
        <div className="warp-cert-actions">
          <button type="button" className="warp-tb-button" onClick={() => setUploadOpen(true)}>
            <Upload size={14} aria-hidden /> {t("certificates.uploadCertificate")}
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            onClick={() => setAcmeOpen(true)}
          >
            <Plus size={14} aria-hidden /> {t("certificates.getLetsEncrypt")}
          </button>
        </div>

        {certsQ.isLoading ? <p className="warp-cert-empty">{t("common.loading")}</p> : null}
        {certsQ.isError && !certsQ.isLoading ? <WarpError onRetry={() => certsQ.refetch()} /> : null}
        {certs.length === 0 && !certsQ.isLoading && !certsQ.isError ? (
          <p className="warp-cert-empty">
            {t("certificates.empty")}
          </p>
        ) : null}

        <div className="warp-cert-list">
          {certs.map((c) => {
            const dl = daysLeft(c.not_after);
            const tone =
              c.status === "error"
                ? "critical"
                : c.status === "pending"
                  ? "warning"
                  : dl != null && dl < 0
                    ? "critical"
                    : dl != null && dl < 15
                      ? "warning"
                      : "success";
            const label =
              c.status === "error"
                ? t("certificates.status.error")
                : c.status === "pending"
                  ? t("certificates.status.pending")
                  : dl != null && dl < 0
                    ? t("certificates.status.expired")
                    : dl != null
                      ? t("certificates.status.daysLeft", { n: dl })
                      : t("certificates.status.active");
            return (
              <div key={c.id} className="warp-cert-row">
                <div className="warp-cert-row-head">
                  <span className="warp-cert-name">{c.domain}</span>
                  <span className={`warp-badge ${tone}`}>{label}</span>
                  <button
                    type="button"
                    className="warp-cert-del"
                    onClick={() => remove(c.id, c.domain)}
                    aria-label={t("action.delete")}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="warp-cert-meta">
                  <span>
                    {t("certificates.source")} <b>{c.source === "acme" ? t("certificates.sourceLetsEncrypt") : t("certificates.sourceManual")}</b>
                  </span>
                  <span>
                    {t("certificates.issuer")} <b>{c.issuer || "—"}</b>
                  </span>
                  <span>
                    {t("certificates.expires")} <b>{fmtDate(c.not_after)}</b>
                  </span>
                </div>
                {c.last_error ? <p className="warp-cert-error">{c.last_error}</p> : null}
              </div>
            );
          })}
        </div>
      </SettingsSection>

      {uploadOpen ? (
        <UploadCertModal
          onClose={() => setUploadOpen(false)}
          onSaved={() => {
            setUploadOpen(false);
            qc.invalidateQueries({ queryKey: ["managed-certs"] });
            qc.invalidateQueries({ queryKey: ["cert-inventory"] });
          }}
        />
      ) : null}
      {acmeOpen ? (
        <AcmeModal
          onClose={() => setAcmeOpen(false)}
          onSaved={() => {
            setAcmeOpen(false);
            qc.invalidateQueries({ queryKey: ["managed-certs"] });
            qc.invalidateQueries({ queryKey: ["cert-inventory"] });
          }}
        />
      ) : null}
    </div>
  );
}

function UploadCertModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [domain, setDomain] = useState("");
  const [certPem, setCertPem] = useState("");
  const [keyPem, setKeyPem] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await importCertificate({ domain: domain.trim(), cert_pem: certPem, key_pem: keyPem });
      toast("success", t("certificates.saved"));
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("certificates.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("certificates.uploadCertificate")}
      width="w-[min(640px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button type="button" variant="primary" disabled={busy || !domain || !certPem || !keyPem} onClick={submit}>
            {busy ? t("common.saving") : t("certificates.saveCertificate")}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">{t("certificates.domain")}</p>
      <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="vpn.example.com" autoComplete="off" />
      <p className="warp-dlg-section-title" style={{ marginTop: 16 }}>{t("certificates.certPemLabel")}</p>
      <textarea
        className="warp-cert-textarea"
        value={certPem}
        onChange={(e) => setCertPem(e.target.value)}
        placeholder="-----BEGIN CERTIFICATE-----"
        rows={6}
      />
      <p className="warp-dlg-section-title" style={{ marginTop: 16 }}>{t("certificates.keyPemLabel")}</p>
      <textarea
        className="warp-cert-textarea"
        value={keyPem}
        onChange={(e) => setKeyPem(e.target.value)}
        placeholder="-----BEGIN PRIVATE KEY-----"
        rows={6}
      />
    </Modal>
  );
}

function AcmeModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [domain, setDomain] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await requestAcmeCertificate(domain.trim());
      toast("success", t("certificates.issued"));
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("certificates.issuanceFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("certificates.getLetsEncryptTitle")}
      width="w-[min(560px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("action.cancel")}
          </Button>
          <Button type="button" variant="primary" disabled={busy || !domain} onClick={submit}>
            {busy ? t("certificates.issuing") : t("certificates.issueCertificate")}
          </Button>
        </>
      }
    >
      <p className="warp-cert-hint">
        {t("certificates.acmeHint")}
      </p>
      <p className="warp-dlg-section-title" style={{ marginTop: 12 }}>{t("certificates.domain")}</p>
      <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="vpn.example.com" autoComplete="off" autoFocus />
    </Modal>
  );
}
