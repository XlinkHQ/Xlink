"use client";

import { Check, X } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, login } from "@/lib/api";
import { getBranding, onBrandingChange } from "@/lib/branding";

export function LoginScreen({ onSuccess }: { onSuccess: (name: string) => void }) {
  const [brand, setBrand] = useState(getBranding);
  useEffect(() => onBrandingChange(() => setBrand(getBranding())), []);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [alert, setAlert] = useState<"success" | "error" | null>(null);
  const timer = useRef<number | null>(null);

  const showAlert = (kind: "success" | "error") => {
    setAlert(kind);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setAlert(null), 4000);
  };
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    setAlert(null);
    if (username.trim().length === 0) {
      showAlert("error");
      return;
    }
    setSubmitting(true);
    const started = Date.now();
    const hold = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
    const settle = () => hold(Math.max(0, 3000 - (Date.now() - started)));
    try {
      const res = await login(username.trim(), password, needTotp ? totpCode.trim() : undefined);
      await settle();
      showAlert("success");
      window.setTimeout(() => onSuccess(res.user?.username ?? username.trim()), 1000);
    } catch (caught) {
      await settle();
      if (caught instanceof ApiError && caught.code === "totp_required") {
        setNeedTotp(true);
        setSubmitting(false);
        return;
      }
      showAlert("error");
      setSubmitting(false);
    }
  };

  return (
    <div className="warp-page">
      <main className="warp-signin">
        {alert ? (
          <div className="warp-alert-warpper">
            {alert === "success" ? (
              <div className="warp-alert warp-alert-style" role="status">
                <div>
                  <span className="warp-ico warp-ico-check">
                    <Check size={18} />
                  </span>
                  <div>
                    <h4>Successful</h4>
                    <p>Sign in was successful.</p>
                  </div>
                </div>
                <button type="button" aria-label="Close" onClick={() => setAlert(null)}>
                  <span><X size={16} /></span>
                </button>
              </div>
            ) : (
              <div className="warp-alert warp-alert-style" role="alert">
                <div>
                  <span className="warp-ico warp-ico-close">
                    <X size={18} />
                  </span>
                  <div>
                    <h4>Unsuccessful</h4>
                    <p>Please check your username and password and try again.</p>
                  </div>
                </div>
                <button type="button" aria-label="Close" onClick={() => setAlert(null)}>
                  <span><X size={16} /></span>
                </button>
              </div>
            )}
          </div>
        ) : null}

        {/* FORM */}
        <form className="warp-form-signin" onSubmit={submit} autoCapitalize="off" autoCorrect="off">
          <img
            src={brand.logo}
            alt={brand.name}
            className="warp-logo warp-signin-animation-logo"
            draggable={false}
          />
          <input
            type="text"
            placeholder="Username"
            aria-placeholder="Username"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            type="password"
            placeholder="Password"
            aria-placeholder="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {needTotp ? (
            <input
              type="text"
              inputMode="numeric"
              placeholder="Two-factor code"
              aria-placeholder="Two-factor code"
              autoComplete="one-time-code"
              autoFocus
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
            />
          ) : null}
          <input
            type="submit"
            className={submitting ? "warp-loader-processor-button" : ""}
            value={submitting ? "Processing..." : "Sign in"}
            disabled={submitting}
          />
        </form>
      </main>

      {/* INDICATOR */}
      <div className="warp-indicator-warpper warp-indicator-animation">
        <div className="warp-indicator" />
      </div>
    </div>
  );
}
