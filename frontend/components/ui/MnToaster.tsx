"use client";

/**
 * Toaster (sonner) integrado ao tema da casa.
 *
 * O <Toaster> puro assume o tema do SISTEMA, mas o app controla o tema via
 * classe no <html> + localStorage("mn_theme") (ver ThemeToggle). Aqui lemos
 * o tema pelo useTheme (MutationObserver no <html>, reage ao toggle na hora)
 * e passamos pro sonner, forçando também os tokens da casa no card do toast
 * (card/border/foreground) pra não destoar do resto da UI.
 */
import { Toaster } from "sonner";

import { useTheme } from "@/lib/useTheme";

export function MnToaster() {
  const theme = useTheme();

  return (
    <Toaster
      theme={theme}
      richColors
      position="top-right"
      toastOptions={{
        classNames: {
          toast: "bg-card border-border text-foreground",
        },
      }}
    />
  );
}
