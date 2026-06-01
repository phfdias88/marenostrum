"use client";

/**
 * Barra de progresso de navegação (estilo NProgress/Vercel).
 *
 * Dá feedback IMEDIATO ao clicar num link interno — a barra dispara na hora
 * e "enche" até a rota trocar. Sem isso, em conexões lentas, o clique parece
 * "não fazer nada" por uns instantes.
 *
 * Como funciona:
 *  - Captura cliques em <a> internos (mesma origem, sem target/modificadores)
 *    → começa a barra + trickle (avança devagar até ~85%).
 *  - Quando o pathname muda → completa (100%) e some.
 *  - Fallback de 8s: se o clique não resultar em navegação (link âncora,
 *    cancelado), a barra some sozinha — nunca fica presa.
 */
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export function RouteProgress() {
  const pathname = usePathname();
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);
  const trickleRef = useRef<number | null>(null);
  const fallbackRef = useRef<number | null>(null);
  const firstRender = useRef(true);

  function stopTimers() {
    if (trickleRef.current) window.clearInterval(trickleRef.current);
    if (fallbackRef.current) window.clearTimeout(fallbackRef.current);
    trickleRef.current = null;
    fallbackRef.current = null;
  }

  function start() {
    stopTimers();
    setVisible(true);
    setWidth(12);
    // Trickle: avança em passos decrescentes, satura perto de 85%.
    trickleRef.current = window.setInterval(() => {
      setWidth((w) => (w >= 85 ? w : w + Math.max(0.5, (90 - w) * 0.08)));
    }, 200);
    // Nunca deixa preso: 8s sem troca de rota → finaliza.
    fallbackRef.current = window.setTimeout(() => finish(), 8000);
  }

  function finish() {
    stopTimers();
    setWidth(100);
    window.setTimeout(() => {
      setVisible(false);
      setWidth(0);
    }, 220);
  }

  // Clique em link interno → start
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement | null)?.closest("a");
      if (!a) return;
      const href = a.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      if (a.target && a.target !== "_self") return;
      try {
        const url = new URL(a.href, window.location.href);
        if (url.origin !== window.location.origin) return; // externo
        if (url.pathname === window.location.pathname && url.search === window.location.search)
          return; // mesma página
      } catch {
        return;
      }
      start();
    }
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Troca de rota → finish
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    finish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // Limpeza
  useEffect(() => () => stopTimers(), []);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-x-0 top-0 z-[100] h-0.5 pointer-events-none"
      aria-hidden
    >
      <div
        className="h-full bg-primary shadow-[0_0_8px_var(--tw-shadow-color)] shadow-primary/60 transition-[width] duration-200 ease-out"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
