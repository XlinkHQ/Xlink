import { apiFetch } from "./core";

export type CertificateEntryRead = {
  profile_id: string;
  profile_name: string;
  core: string;
  protocol: string;
  security: string;
  server_name: string | null;
  node_id: string;
  node_name: string;
  node_host: string;
  status: string;
};

export type CertificateNodeGroupRead = {
  node_id: string;
  node_name: string;
  node_host: string;
  secure_count: number;
  insecure_count: number;
  entries: CertificateEntryRead[];
};

export type CertificatesRead = {
  total: number;
  secure: number;
  reality: number;
  insecure: number;
  nodes: CertificateNodeGroupRead[];
};

export type ManagedCertificate = {
  id: string;
  domain: string;
  source: string;
  status: string;
  issuer: string;
  not_before: string | null;
  not_after: string | null;
  last_error: string;
  renewed_at: string | null;
  created_at: string;
};

export function listCertificates() {
  return apiFetch<ManagedCertificate[]>("/certificates");
}

export function importCertificate(body: { domain: string; cert_pem: string; key_pem: string }) {
  return apiFetch<ManagedCertificate>("/certificates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function requestAcmeCertificate(domain: string) {
  return apiFetch<ManagedCertificate>("/certificates/acme", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export function deleteCertificate(id: string) {
  return apiFetch<void>(`/certificates/${id}`, { method: "DELETE" });
}
