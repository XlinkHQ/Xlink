"use client";

export type Branding = { name: string; logo: string };

const KEY = "xlink.branding";
const DEFAULTS: Branding = { name: "XLink", logo: "/xlink-logo.png" };
const EVENT = "xlink-branding";

export function getBranding(): Branding {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const v = JSON.parse(raw) as Partial<Branding>;
    return { name: v.name || DEFAULTS.name, logo: v.logo || DEFAULTS.logo };
  } catch {
    return DEFAULTS;
  }
}

export function setBranding(b: Branding): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(b));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch {
    /* ignore */
  }
}

export function onBrandingChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}
