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
import { SettingsSection } from "./settings-kit";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

function daysLeft(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86400000);
}

export function CertificatesSettingsScreen() {
  const qc = useQueryClient();
  const certsQ = useQuery({ queryKey: ["managed-certs"], queryFn: () => listCertificates() });
  const [uploadOpen, setUploadOpen] = useState(false);
  const [acmeOpen, setAcmeOpen] = useState(false);

  const certs = certsQ.data ?? [];

  const remove = async (id: string, domain: string) => {
    if (
      !(await confirmDialog({
        title: `Delete certificate for ${domain}?`,
        message: "Inbounds using this domain will fall back to no certificate until you add another.",
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
    try {
      await deleteCertificate(id);
      toast("success", "Certificate deleted.");
      qc.invalidateQueries({ queryKey: ["managed-certs"] });
      qc.invalidateQueries({ queryKey: ["cert-inventory"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={ShieldCheck}
        title="Certificates"
        description="Manage the TLS certificates used to secure your inbounds. Upload your own, or issue one automatically with Let's Encrypt."
      >
        <div className="warp-cert-actions">
          <button type="button" className="warp-tb-button" onClick={() => setUploadOpen(true)}>
            <Upload size={14} aria-hidden /> Upload certificate
          </button>
          <button
            type="button"
            className="warp-tb-button warp-tb-button-primary"
            onClick={() => setAcmeOpen(true)}
          >
            <Plus size={14} aria-hidden /> Get Let's Encrypt
          </button>
        </div>

        {certsQ.isLoading ? <p className="warp-cert-empty">Loading…</p> : null}
        {certs.length === 0 && !certsQ.isLoading ? (
          <p className="warp-cert-empty">
            No certificates yet. Upload one or request a free Let's Encrypt certificate for your domain.
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
                ? "Error"
                : c.status === "pending"
                  ? "Pending"
                  : dl != null && dl < 0
                    ? "Expired"
                    : dl != null
                      ? `${dl}d left`
                      : "Active";
            return (
              <div key={c.id} className="warp-cert-row">
                <div className="warp-cert-row-head">
                  <span className="warp-cert-name">{c.domain}</span>
                  <span className={`warp-badge ${tone}`}>{label}</span>
                  <button
                    type="button"
                    className="warp-cert-del"
                    onClick={() => remove(c.id, c.domain)}
                    aria-label="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="warp-cert-meta">
                  <span>
                    Source: <b>{c.source === "acme" ? "Let's Encrypt" : "Manual"}</b>
                  </span>
                  <span>
                    Issuer: <b>{c.issuer || "—"}</b>
                  </span>
                  <span>
                    Expires: <b>{fmtDate(c.not_after)}</b>
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
  const [domain, setDomain] = useState("");
  const [certPem, setCertPem] = useState("");
  const [keyPem, setKeyPem] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await importCertificate({ domain: domain.trim(), cert_pem: certPem, key_pem: keyPem });
      toast("success", "Certificate saved.");
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Upload certificate"
      width="w-[min(640px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" variant="primary" disabled={busy || !domain || !certPem || !keyPem} onClick={submit}>
            {busy ? "Saving…" : "Save certificate"}
          </Button>
        </>
      }
    >
      <p className="warp-dlg-section-title">Domain</p>
      <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="vpn.example.com" autoComplete="off" />
      <p className="warp-dlg-section-title" style={{ marginTop: 16 }}>Certificate (PEM, full chain)</p>
      <textarea
        className="warp-cert-textarea"
        value={certPem}
        onChange={(e) => setCertPem(e.target.value)}
        placeholder="-----BEGIN CERTIFICATE-----"
        rows={6}
      />
      <p className="warp-dlg-section-title" style={{ marginTop: 16 }}>Private key (PEM)</p>
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
  const [domain, setDomain] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await requestAcmeCertificate(domain.trim());
      toast("success", "Certificate issued.");
      onSaved();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Issuance failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Get a Let's Encrypt certificate"
      width="w-[min(560px,95vw)]"
      onClose={onClose}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" variant="primary" disabled={busy || !domain} onClick={submit}>
            {busy ? "Issuing…" : "Issue certificate"}
          </Button>
        </>
      }
    >
      <p className="warp-cert-hint">
        The panel will validate ownership over HTTP and obtain a free certificate. The domain must
        point to this panel and port 80 must be reachable.
      </p>
      <p className="warp-dlg-section-title" style={{ marginTop: 12 }}>Domain</p>
      <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="vpn.example.com" autoComplete="off" autoFocus />
    </Modal>
  );
}
