"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import { ApiError, currentUser, totpConfirm, totpDisable, totpEnroll } from "@/lib/api";
import { promptDialog } from "@/components/ui/dialog";
import { copyText } from "@/lib/clipboard";
import { Drawer } from "./parts";
import { SettingsRow } from "./settings";

function TotpQr({ value }: { value: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setSrc(null);
    setFailed(false);
    QRCode.toDataURL(value, { width: 160, margin: 1, color: { light: "#ffffff", dark: "#161616" } })
      .then((url) => active && setSrc(url))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [value]);

  if (failed) {
    return (
      <span className="warp-2fa-qrbox warp-2fa-qrbox-fallback">
        Couldn’t render the QR — use the setup key below.
      </span>
    );
  }
  if (!src) {
    return <span className="warp-2fa-qrbox warp-2fa-qrbox-loading" aria-label="Generating QR" />;
  }
  return (
    <span className="warp-2fa-qrbox">
      <img src={src} alt="" width={160} height={160} />
    </span>
  );
}

export function SecuritySettingsScreen() {
  const qc = useQueryClient();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => currentUser() });
  const enabled = meQuery.data?.totp_enabled ?? false;
  const [enroll, setEnroll] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    try {
      setEnroll(await totpEnroll());
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Could not start enrollment.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await totpConfirm(code.trim());
      toast("success", "Two-factor authentication enabled.");
      setEnroll(null);
      setCode("");
      qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Invalid code.");
    } finally {
      setBusy(false);
    }
  };

  const cancelEnroll = () => {
    setEnroll(null);
    setCode("");
  };

  const disable = async () => {
    const c = await promptDialog({
      title: "Disable two-factor auth",
      message: "Enter a current code from your authenticator to confirm.",
      placeholder: "123456",
      confirmLabel: "Disable",
      danger: true,
    });
    if (!c) return;
    setBusy(true);
    try {
      await totpDisable(c.trim());
      toast("success", "Two-factor authentication disabled.");
      qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Invalid code.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full">
      <div className="warp-set-list">
        <SettingsRow
          label="Two-factor authentication"
          hint="Require a TOTP code (Google Authenticator, Authy, 1Password) at sign-in."
        >
          {enabled ? (
            <button type="button" className="warp-tb-button warp-tb-button-danger" onClick={disable} disabled={busy}>
              Disable 2FA
            </button>
          ) : (
            <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={start} disabled={busy}>
              Enable 2FA
            </button>
          )}
        </SettingsRow>
      </div>

      {enroll && !enabled ? (
        <Drawer
          title={<span className="text-lg font-medium">Enable two-factor auth</span>}
          width="w-[460px]"
          panelClassName="bg-canvas"
          onClose={cancelEnroll}
        >
          <div className="warp-2fa">
            <ol className="warp-2fa-steps">
              <li>
                <span className="warp-2fa-step">1</span>
                <div>
                  <p className="warp-2fa-h">Scan the QR code</p>
                  <p className="warp-2fa-sub">Google Authenticator · Authy · 1Password</p>
                  <div className="warp-2fa-qr">
                    <TotpQr value={enroll.otpauth_uri} />
                  </div>
                </div>
              </li>
              <li>
                <span className="warp-2fa-step">2</span>
                <div className="min-w-0">
                  <p className="warp-2fa-h">Or add the key manually</p>
                  <button
                    type="button"
                    className="warp-2fa-key"
                    title="Copy"
                    onClick={async () => {
                      await copyText(enroll.secret);
                      toast("success", "Setup key copied.");
                    }}
                  >
                    <code>{enroll.secret.replace(/(.{4})/g, "$1 ").trim()}</code>
                    <Copy size={14} />
                  </button>
                </div>
              </li>
              <li>
                <span className="warp-2fa-step">3</span>
                <div className="min-w-0 flex-1">
                  <p className="warp-2fa-h">Enter the 6-digit code</p>
                  <input
                    className="warp-set-input mt-2"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="123456"
                    value={code}
                    autoFocus
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && code.trim().length === 6 && !busy) confirm();
                    }}
                  />
                </div>
              </li>
            </ol>

            <div className="warp-2fa-actions">
              <button type="button" className="warp-tb-button" onClick={cancelEnroll} disabled={busy}>
                Cancel
              </button>
              <button
                type="button"
                className="warp-tb-button warp-tb-button-primary"
                onClick={confirm}
                disabled={busy || code.trim().length < 6}
              >
                {busy ? "Verifying…" : "Enable"}
              </button>
            </div>
          </div>
        </Drawer>
      ) : null}
    </div>
  );
}
