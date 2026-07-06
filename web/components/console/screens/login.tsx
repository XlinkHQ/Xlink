"use client";

import { type FormEvent, useEffect, useState } from "react";
import { ApiError, login } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { getBranding, onBrandingChange } from "@/lib/branding";

export function LoginScreen({ onSuccess }: { onSuccess: (name: string) => void }) {
  const [brand, setBrand] = useState(getBranding);
  useEffect(() => onBrandingChange(() => setBrand(getBranding())), []);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    if (username.trim().length === 0) {
      toast("error", "Please check your username and password and try again.");
      return;
    }
    setSubmitting(true);
    const started = Date.now();
    const hold = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
    const settle = () => hold(Math.max(0, 3000 - (Date.now() - started)));
    try {
      const res = await login(username.trim(), password, needTotp ? totpCode.trim() : undefined);
      await settle();
      toast("success", "Signed in successfully.");
      window.setTimeout(() => onSuccess(res.user?.username ?? username.trim()), 700);
    } catch (caught) {
      await settle();
      if (caught instanceof ApiError && caught.code === "totp_required") {
        setNeedTotp(true);
        setSubmitting(false);
        return;
      }
      toast("error", caught instanceof ApiError ? caught.message : "Please check your username and password and try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="warp-login-page">
      {/* SIDE ILLUSTRATION PANEL (DefGuard split layout) */}
      <aside className="warp-login-aside">
        <img src="/login.png" alt="" loading="eager" decoding="async" draggable={false} />
      </aside>

      {/* FORM PANEL */}
      <div className="warp-login-track">
        <main className="warp-login-main">
          <img
            src={brand.logo}
            alt={brand.name}
            className="warp-login-logo warp-signin-animation-logo"
            draggable={false}
          />

          <h1 className="warp-login-title">Sign in to your account</h1>
          <h2 className="warp-login-subtitle">Enter your credentials to continue.</h2>

          {/* FORM */}
          <form className="warp-login-form" onSubmit={submit} autoCapitalize="off" autoCorrect="off">
            <div className="warp-login-field">
              <label htmlFor="warp-login-username">Username</label>
              <input
                id="warp-login-username"
                type="text"
                placeholder="Username"
                aria-placeholder="Username"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="warp-login-field">
              <label htmlFor="warp-login-password">Password</label>
              <input
                id="warp-login-password"
                type="password"
                placeholder="Password"
                aria-placeholder="Password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {needTotp ? (
              <div className="warp-login-field">
                <label htmlFor="warp-login-totp">Two-factor code</label>
                <input
                  id="warp-login-totp"
                  type="text"
                  inputMode="numeric"
                  placeholder="Two-factor code"
                  aria-placeholder="Two-factor code"
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
              {submitting ? "Processing..." : "Sign in"}
            </button>
          </form>

          <footer className="warp-login-footer">
            <p>Copyright © {new Date().getFullYear()} {brand.name}</p>
          </footer>
        </main>
      </div>

      {/* INDICATOR (rainbow bottom bar) */}
      <div className="warp-indicator-warpper warp-indicator-animation">
        <div className="warp-indicator" />
      </div>
    </div>
  );
}
