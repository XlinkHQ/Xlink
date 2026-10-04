"use client";

import { useEffect, useState } from "react";

export const LOCALES = ["en", "fa", "ru", "zh"] as const;
export type Locale = (typeof LOCALES)[number];

/** Locales written right-to-left. */
export const RTL_LOCALES: ReadonlySet<Locale> = new Set<Locale>(["fa"]);

export function isRtl(locale: Locale): boolean {
  return RTL_LOCALES.has(locale);
}

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  fa: "فارسی",
  ru: "Русский",
  zh: "中文",
};

const KEY = "xlink-locale";
const DEFAULT: Locale = "en";

function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value);
}

export function getLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT;
  const stored = window.localStorage.getItem(KEY);
  return isLocale(stored) ? stored : DEFAULT;
}

export function setLocale(locale: Locale) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, locale);
  window.dispatchEvent(new CustomEvent(KEY, { detail: locale }));
}

/** Reflect the locale onto <html lang/dir> so RTL languages lay out correctly.
 *
 * The root layout is a server component and renders a static lang="en" with no
 * dir, so Persian shipped fully translated but still laid out left-to-right.
 * Doing it here means every consumer of the locale gets it for free. */
function applyDocumentLocale(locale: Locale): void {
  if (typeof document === "undefined") return;
  const el = document.documentElement;
  el.lang = locale;
  el.dir = isRtl(locale) ? "rtl" : "ltr";
}

export function useLocale(): Locale {
  const [locale, set] = useState<Locale>(DEFAULT);
  useEffect(() => {
    const initial = getLocale();
    set(initial);
    applyDocumentLocale(initial);
    const handler = (e: Event) => {
      const next = (e as CustomEvent<Locale>).detail;
      set(next);
      applyDocumentLocale(next);
    };
    window.addEventListener(KEY, handler);
    return () => window.removeEventListener(KEY, handler);
  }, []);
  return locale;
}
