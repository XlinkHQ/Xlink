"use client";

import { useEffect, useState } from "react";

export const LOCALES = ["en", "fa", "ru", "zh"] as const;
export type Locale = (typeof LOCALES)[number];

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

export function useLocale(): Locale {
  const [locale, set] = useState<Locale>(DEFAULT);
  useEffect(() => {
    set(getLocale());
    const handler = (e: Event) => set((e as CustomEvent<Locale>).detail);
    window.addEventListener(KEY, handler);
    return () => window.removeEventListener(KEY, handler);
  }, []);
  return locale;
}
