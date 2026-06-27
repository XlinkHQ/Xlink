"use client";

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "xlink-theme";
const DARK_CLASS = "xlink-dark";

function applyThemeToDocument(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle(DARK_CLASS, theme === "dark");
  document.body.classList.toggle(DARK_CLASS, theme === "dark");
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return window.localStorage.getItem(KEY) === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, theme);
  applyThemeToDocument(theme);
  window.dispatchEvent(new CustomEvent(KEY, { detail: theme }));
}

export function useTheme(): Theme {
  const [theme, set] = useState<Theme>("dark");
  useEffect(() => {
    const initial = getTheme();
    set(initial);
    applyThemeToDocument(initial);
    const handler = (e: Event) => {
      const next = (e as CustomEvent<Theme>).detail;
      applyThemeToDocument(next);
      set(next);
    };
    const storageHandler = (e: StorageEvent) => {
      if (e.key !== KEY) return;
      const next = e.newValue === "light" ? "light" : "dark";
      applyThemeToDocument(next);
      set(next);
    };
    window.addEventListener(KEY, handler);
    window.addEventListener("storage", storageHandler);
    return () => {
      window.removeEventListener(KEY, handler);
      window.removeEventListener("storage", storageHandler);
    };
  }, []);
  return theme;
}
