"use client";

/**
 * Hook compartilhado pra ler o tema atual ("dark"|"light").
 *
 * Sources of truth (em ordem):
 *  1. classList do <html> (sempre tem dark OU light apos o anti-FOUC script)
 *  2. localStorage("mn_theme") como fallback
 *
 * Observa mudancas via MutationObserver no classList do <html>, entao quando
 * o usuario clica no ThemeToggle, todos os mapas re-renderizam.
 */
import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

function readTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  if (document.documentElement.classList.contains("light")) return "light";
  if (document.documentElement.classList.contains("dark")) return "dark";
  try {
    const t = window.localStorage.getItem("mn_theme");
    if (t === "light") return "light";
  } catch {
    /* ignore */
  }
  return "dark";
}

export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(readTheme());
    if (typeof document === "undefined") return;
    const html = document.documentElement;
    const obs = new MutationObserver(() => setTheme(readTheme()));
    obs.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return theme;
}
