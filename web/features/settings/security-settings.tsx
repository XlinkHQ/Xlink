"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, LogOut, ShieldCheck } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast";
import { ApiError, clearTokens, currentUser, logoutAll, totpConfirm, totpDisable, totpEnroll } from "@/lib/api";
import { confirmDialog, promptDialog } from "@/components/ui/dialog";
import { copyText } from "@/lib/clipboard";
import { Modal } from "@/components/ui/modal";
import { SettingsRow } from "./settings";
import { SettingsSection } from "@/components/console/screens/settings-kit";

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
  const [signingOut, setSigningOut] = useState(false);

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
      <SettingsSection
        icon={ShieldCheck}
        title="Two-factor authentication"
        description="Require a one-time code at sign-in, in addition to your password."
      >
        <SettingsRow
          label="Authenticator app"
          hint="Use Google Authenticator, Authy or 1Password."
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
      </SettingsSection>

      <SettingsSection
        divider
        icon={LogOut}
        title="Sessions"
        description="Sign out of every device where this admin account is logged in."
      >
        <SettingsRow
          label="Active sessions"
          hint="Revoke all sessions — you and any other device will need to sign in again."
        >
          <button
            type="button"
            className="warp-tb-button warp-tb-button-danger"
            disabled={signingOut}
            onClick={async () => {
              if (!(await confirmDialog({ title: "Sign out everywhere?", message: "All sessions for this account are revoked immediately.", confirmLabel: "Sign out", danger: true }))) return;
              setSigningOut(true);
              try {
                await logoutAll();
                // logoutAll revokes THIS session's refresh token too, so clear
                // local tokens and bounce to login — otherwise this tab keeps
                // working until the access token silently expires.
                clearTokens();
                toast("success", "Signed out of all sessions.");
                window.location.href = "/";
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : "Request failed.");
              } finally {
                setSigningOut(false);
              }
            }}
          >
            {signingOut ? "Signing out…" : "Sign out everywhere"}
          </button>
        </SettingsRow>
      </SettingsSection>

      {enroll && !enabled ? (
        <Modal
          title="Enable two-factor authentication"
          width="sm:w-[460px]"
          onClose={cancelEnroll}
          footer={
            <>
              <button type="button" className="warp-tb-button" onClick={cancelEnroll} disabled={busy}>
                Cancel
              </button>
              <button
                type="button"
                className="warp-tb-button warp-tb-button-primary"
                onClick={confirm}
                disabled={busy || code.trim().length < 6}
              >
                {busy ? "Verifying…" : "Verify code"}
              </button>
            </>
          }
        >
          <div className="warp-totp">
            <section className="warp-totp-section">
              <header className="warp-totp-head">
                <span className="warp-badge success">Step 1</span>
                <p className="warp-totp-title">Scan the QR code</p>
              </header>
              <p className="warp-totp-desc">
                Open your authenticator app (Google Authenticator, Authy, 1Password)
                and scan the code below to add this account.
              </p>
              <div className="warp-totp-qr">
                <TotpQr value={enroll.otpauth_uri} />
                <p className="warp-totp-qr-hint">Can’t scan the code?</p>
                <button
                  type="button"
                  className="warp-totp-copy"
                  title="Copy setup key"
                  onClick={async () => {
                    await copyText(enroll.secret);
                    toast("success", "Setup key copied.");
                  }}
                >
                  <code>{enroll.secret.replace(/(.{4})/g, "$1 ").trim()}</code>
                  <Copy size={14} aria-hidden />
                </button>
              </div>
            </section>

            <div className="warp-totp-divider" />

            <section className="warp-totp-section">
              <header className="warp-totp-head">
                <span className="warp-badge success">Step 2</span>
                <p className="warp-totp-title">Enter the authentication code</p>
              </header>
              <label className="warp-totp-field">
                <span className="warp-totp-label">Authentication code</span>
                <input
                  className="warp-set-input"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="000000"
                  value={code}
                  autoFocus
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && code.trim().length === 6 && !busy) confirm();
                  }}
                />
                <span className="warp-totp-helper">Enter the 6-digit code from your authenticator app.</span>
              </label>
            </section>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
