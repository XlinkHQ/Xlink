"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "xlink-theme";

function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  let saved: string | null = null;
  try {
    saved = window.localStorage.getItem(KEY);
  } catch {}
  if (saved === "light" || saved === "dark") return saved;
  // No explicit choice yet: follow the OS instead of forcing dark.
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
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
