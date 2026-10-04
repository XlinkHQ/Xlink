"use client";

import { type FormEvent, useEffect, useState } from "react";
import { ApiError, login, runSetup, setupStatus } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { getBranding, onBrandingChange } from "@/lib/branding";
import { useT } from "@/lib/i18n";

export function LoginScreen({ onSuccess }: { onSuccess: (name: string) => void }) {
  const t = useT();
  const [brand, setBrand] = useState(getBranding);
  useEffect(() => onBrandingChange(() => setBrand(getBranding())), []);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // First run: no admin exists yet, so this screen creates the owner account
  // using the one-time token the panel printed to its log.
  const [setupMode, setSetupMode] = useState(false);
  const [setupToken, setSetupToken] = useState("");
  useEffect(() => {
    setupStatus()
      .then((s) => setSetupMode(s.needs_setup))
      .catch(() => {});
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    if (username.trim().length === 0) {
      toast("error", t("login.error.invalidCredentials"));
      return;
    }
    setSubmitting(true);
    const started = Date.now();
    const hold = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
    const settle = () => hold(Math.max(0, 3000 - (Date.now() - started)));
    try {
      if (setupMode) await runSetup(setupToken.trim(), username.trim(), password);
      const res = await login(username.trim(), password, needTotp ? totpCode.trim() : undefined);
      await settle();
      toast("success", t("login.success"));
      window.setTimeout(() => onSuccess(res.user?.username ?? username.trim()), 700);
    } catch (caught) {
      await settle();
      if (caught instanceof ApiError && caught.code === "totp_required") {
        setNeedTotp(true);
        setSubmitting(false);
        return;
      }
      toast("error", caught instanceof ApiError ? caught.message : t("login.error.invalidCredentials"));
      setSubmitting(false);
    }
  };

  return (
    <div className="warp-login-page">
      <aside className="warp-login-aside">
        <img src="/login.png" alt="" loading="eager" decoding="async" draggable={false} />
      </aside>

      <div className="warp-login-track">
        <main className="warp-login-main">
          <img
            src={brand.logo}
            alt={brand.name}
            className="warp-login-logo warp-signin-animation-logo"
            draggable={false}
          />

          <h1 className="warp-login-title">{t(setupMode ? "setup.title" : "login.title")}</h1>
          <h2 className="warp-login-subtitle">{t(setupMode ? "setup.subtitle" : "login.subtitle")}</h2>

          <form className="warp-login-form" onSubmit={submit} autoCapitalize="off" autoCorrect="off">
            {setupMode ? (
              <div className="warp-login-field">
                <label htmlFor="warp-login-setup-token">{t("setup.token")}</label>
                <input
                  id="warp-login-setup-token"
                  type="text"
                  placeholder={t("setup.token")}
                  aria-placeholder={t("setup.token")}
                  autoComplete="off"
                  value={setupToken}
                  onChange={(e) => setSetupToken(e.target.value)}
                />
              </div>
            ) : null}
            <div className="warp-login-field">
              <label htmlFor="warp-login-username">{t("login.username")}</label>
              <input
                id="warp-login-username"
                type="text"
                placeholder={t("login.username")}
                aria-placeholder={t("login.username")}
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="warp-login-field">
              <label htmlFor="warp-login-password">{t("login.password")}</label>
              <input
                id="warp-login-password"
                type="password"
                placeholder={t("login.password")}
                aria-placeholder={t("login.password")}
                autoComplete={setupMode ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {needTotp ? (
              <div className="warp-login-field">
                <label htmlFor="warp-login-totp">{t("login.totp")}</label>
                <input
                  id="warp-login-totp"
                  type="text"
                  inputMode="numeric"
                  placeholder={t("login.totp")}
                  aria-placeholder={t("login.totp")}
                  autoComplete="one-time-code"
                  autoFocus
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                />
              </div>
            ) : null}
            <button
              type="submit"
              className={`warp-login-submit${submitting ? " warp-login-submit-loading" : ""}`}
              disabled={submitting}
            >
              {submitting ? t("login.processing") : t(setupMode ? "setup.submit" : "login.signIn")}
            </button>
          </form>

          <footer className="warp-login-footer">
            <p>{t("login.copyright", { year: new Date().getFullYear(), name: brand.name })}</p>
          </footer>
        </main>
      </div>

      <div className="warp-indicator-warpper warp-indicator-animation">
        <div className="warp-indicator" />
      </div>
    </div>
  );
}
