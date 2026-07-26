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
import { useT } from "@/lib/i18n";
import { SettingsRow } from "./save-context";
import { SettingsSection } from "@/shared/settings-kit";

function TotpQr({ value }: { value: string }) {
  const t = useT();
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
        {t("security.qrFailed")}
      </span>
    );
  }
  if (!src) {
    return <span className="warp-2fa-qrbox warp-2fa-qrbox-loading" aria-label={t("security.generatingQr")} />;
  }
  return (
    <span className="warp-2fa-qrbox">
      <img src={src} alt="" width={160} height={160} />
    </span>
  );
}

export function SecuritySettingsScreen() {
  const t = useT();
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
      toast("error", e instanceof ApiError ? e.message : t("security.enrollFailed"));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    try {
      await totpConfirm(code.trim());
      toast("success", t("security.enabled"));
      setEnroll(null);
      setCode("");
      qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("security.invalidCode"));
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
      title: t("security.disableTitle"),
      message: t("security.disableMessage"),
      placeholder: "123456",
      confirmLabel: t("action.disable"),
      danger: true,
    });
    if (!c) return;
    setBusy(true);
    try {
      await totpDisable(c.trim());
      toast("success", t("security.disabled"));
      qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : t("security.invalidCode"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full">
      <SettingsSection
        icon={ShieldCheck}
        title={t("security.twoFactorTitle")}
        description={t("security.twoFactorDesc")}
      >
        <SettingsRow
          label={t("security.authenticatorApp")}
          hint={t("security.authenticatorAppHint")}
        >
          {enabled ? (
            <button type="button" className="warp-tb-button warp-tb-button-danger" onClick={disable} disabled={busy}>
              {t("security.disable2fa")}
            </button>
          ) : (
            <button type="button" className="warp-tb-button warp-tb-button-primary" onClick={start} disabled={busy}>
              {t("security.enable2fa")}
            </button>
          )}
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        divider
        icon={LogOut}
        title={t("security.sessionsTitle")}
        description={t("security.sessionsDesc")}
      >
        <SettingsRow
          label={t("security.activeSessions")}
          hint={t("security.activeSessionsHint")}
        >
          <button
            type="button"
            className="warp-tb-button warp-tb-button-danger"
            disabled={signingOut}
            onClick={async () => {
              if (!(await confirmDialog({ title: t("security.signOutEverywhereConfirmTitle"), message: t("security.signOutEverywhereConfirmMsg"), confirmLabel: t("security.signOut"), danger: true }))) return;
              setSigningOut(true);
              try {
                await logoutAll();
                clearTokens();
                toast("success", t("security.signedOutAll"));
                window.location.href = "/";
              } catch (e) {
                toast("error", e instanceof ApiError ? e.message : t("common.requestFailed"));
              } finally {
                setSigningOut(false);
              }
            }}
          >
            {signingOut ? t("security.signingOut") : t("security.signOutEverywhere")}
          </button>
        </SettingsRow>
      </SettingsSection>

      {enroll && !enabled ? (
        <Modal
          title={t("security.enrollTitle")}
          width="sm:w-[460px]"
          onClose={cancelEnroll}
          footer={
            <>
              <button type="button" className="warp-tb-button" onClick={cancelEnroll} disabled={busy}>
                {t("action.cancel")}
              </button>
              <button
                type="button"
                className="warp-tb-button warp-tb-button-primary"
                onClick={confirm}
                disabled={busy || code.trim().length < 6}
              >
                {busy ? t("security.verifying") : t("security.verifyCode")}
              </button>
            </>
          }
        >
          <div className="warp-totp">
            <section className="warp-totp-section">
              <header className="warp-totp-head">
                <span className="warp-badge success">{t("security.step1")}</span>
                <p className="warp-totp-title">{t("security.scanQr")}</p>
              </header>
              <p className="warp-totp-desc">
                {t("security.scanQrDesc")}
              </p>
              <div className="warp-totp-qr">
                <TotpQr value={enroll.otpauth_uri} />
                <p className="warp-totp-qr-hint">{t("security.cantScan")}</p>
                <button
                  type="button"
                  className="warp-totp-copy"
                  title={t("security.copySetupKey")}
                  onClick={async () => {
                    await copyText(enroll.secret);
                    toast("success", t("security.setupKeyCopied"));
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
                <span className="warp-badge success">{t("security.step2")}</span>
                <p className="warp-totp-title">{t("security.enterCodeTitle")}</p>
              </header>
              <label className="warp-totp-field">
                <span className="warp-totp-label">{t("security.authCode")}</span>
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
                <span className="warp-totp-helper">{t("security.enterCodeHelper")}</span>
              </label>
            </section>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
