"use client";

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "xlink-theme";

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return window.localStorage.getItem(KEY) === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, theme);
  window.dispatchEvent(new CustomEvent(KEY, { detail: theme }));
}

export function useTheme(): Theme {
  const [theme, set] = useState<Theme>("dark");
  useEffect(() => {
    set(getTheme());
    const handler = (e: Event) => set((e as CustomEvent<Theme>).detail);
    window.addEventListener(KEY, handler);
    return () => window.removeEventListener(KEY, handler);
  }, []);
  return theme;
}
