"use client";

import { en } from "./messages/en";
import { fa } from "./messages/fa";
import { ru } from "./messages/ru";
import { zh } from "./messages/zh";
import type { Locale } from "./locale";
import { useLocale } from "./locale";

export type MessageKey = keyof typeof en;

const CATALOGS: Record<Locale, Partial<Record<MessageKey, string>>> = {
  en,
  fa,
  ru,
  zh,
};

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function translate(
  locale: Locale,
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  const value = CATALOGS[locale]?.[key] ?? en[key] ?? key;
  return interpolate(value, vars);
}

export type TranslateFn = (key: MessageKey, vars?: Record<string, string | number>) => string;

export function useT(): TranslateFn {
  const locale = useLocale();
  return (key, vars) => translate(locale, key, vars);
}

export { useLocale, setLocale, getLocale, isRtl, LOCALES, LOCALE_LABELS } from "./locale";
export type { Locale } from "./locale";
