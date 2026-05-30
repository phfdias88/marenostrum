"use client";

/**
 * Alternador de tema (claro/escuro).
 *
 * Estratégia anti-FOUC:
 *  - Script inline em <head> (em layout.tsx) aplica a classe ANTES de pintar.
 *  - Este componente só lê/grava localStorage e troca a classe no <html>.
 *
 * Chave: "mn_theme" → "dark" | "light"
 * Padrão: "dark" (paleta original da marca).
 */
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

type Theme = "dark" | "light";

function readTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const t = window.localStorage.getItem("mn_theme");
  return t === "light" ? "light" : "dark";
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  if (t === "light") {
    root.classList.add("light");
    root.classList.remove("dark");
  } else {
    root.classList.remove("light");
    root.classList.add("dark");
  }
}

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(readTheme());
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    window.localStorage.setItem("mn_theme", next);
    applyTheme(next);
  }

  // SSR: render botão "neutro" pra evitar mismatch
  if (!mounted) {
    return (
      <button
        aria-label="Alternar tema"
        className={
          "inline-flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors " +
          (className ?? "")
        }
      >
        <Moon className="w-4 h-4" />
      </button>
    );
  }

  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Mudar pra tema claro" : "Mudar pra tema escuro"}
      title={theme === "dark" ? "Tema claro" : "Tema escuro"}
      className={
        "inline-flex items-center justify-center h-8 w-8 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors " +
        (className ?? "")
      }
    >
      {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
}
