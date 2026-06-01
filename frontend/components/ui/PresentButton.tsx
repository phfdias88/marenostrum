"use client";

/**
 * Modo apresentacao — TV/projetor.
 *
 * Click "Apresentar" => entra em fullscreen + esconde header/nav via classe
 * "presenting" no <html>. ESC ou fullscreenchange (browser exit) limpa.
 *
 * Brand chip discreto no canto inferior direito enquanto apresenta.
 */
import { Maximize2, Minimize2 } from "lucide-react";
import { useEffect, useState } from "react";

function enter() {
  document.documentElement.classList.add("presenting");
  const el = document.documentElement;
  // Best-effort fullscreen — browsers exigem gesture do usuario, e nos temos
  // um (o click no botao). Mas se falhar (ex: iframe sem permissao), apenas
  // mantem o layout expandido.
  if (el.requestFullscreen && !document.fullscreenElement) {
    el.requestFullscreen().catch(() => {});
  }
}

function exit() {
  document.documentElement.classList.remove("presenting");
  if (document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
}

export function PresentButton({ className }: { className?: string }) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    function onFsChange() {
      // Quando o usuario aperta ESC pra sair do fullscreen, sincroniza estado.
      if (!document.fullscreenElement) {
        document.documentElement.classList.remove("presenting");
        setActive(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        exit();
        setActive(false);
      }
    }
    document.addEventListener("fullscreenchange", onFsChange);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("fullscreenchange", onFsChange);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  function toggle() {
    if (active) {
      exit();
      setActive(false);
    } else {
      enter();
      setActive(true);
    }
  }

  return (
    <>
      <button
        onClick={toggle}
        title={active ? "Sair da apresentacao (ESC)" : "Apresentar (TV/projetor)"}
        aria-label={active ? "Sair da apresentacao" : "Apresentar"}
        className={
          "inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md border border-border bg-card text-sm hover:border-primary/60 hover:bg-accent/40 transition-colors " +
          (className ?? "")
        }
      >
        {active ? (
          <>
            <Minimize2 className="w-4 h-4" /> <span className="hidden sm:inline">Sair</span>
          </>
        ) : (
          <>
            <Maximize2 className="w-4 h-4" /> <span className="hidden sm:inline">Apresentar</span>
          </>
        )}
      </button>

      {/* Brand chip flutuante quando apresentando */}
      {active && (
        <div className="present-chip pointer-events-none">
          <span className="text-primary font-bold tracking-[0.3em] text-xs">
            MARENOSTRUM
          </span>
          <span className="text-muted-foreground text-[10px] ml-2">
            · Inteligência de Dados &amp; Consultoria
          </span>
        </div>
      )}
    </>
  );
}
