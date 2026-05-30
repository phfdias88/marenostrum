"use client";

/**
 * Pull-to-refresh nativo via touch events.
 *
 * Uso:
 *   <PullToRefresh onRefresh={async () => { await reload(); }}>
 *     <YourList />
 *   </PullToRefresh>
 *
 * Comportamento:
 *  - Detecta arrasto pra baixo apenas quando window.scrollY === 0
 *  - Mostra indicador animado conforme distancia (0..1)
 *  - Dispara onRefresh ao soltar acima do threshold (80px)
 *  - Em desktop e silencioso (touchstart nao dispara com mouse)
 */
import { Loader2, RefreshCcw } from "lucide-react";
import { useRef, useState } from "react";

const THRESHOLD = 80;
const MAX_PULL = 130;

type Props = {
  onRefresh: () => Promise<void> | void;
  children: React.ReactNode;
};

export function PullToRefresh({ onRefresh, children }: Props) {
  const startY = useRef<number | null>(null);
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);

  function onTouchStart(e: React.TouchEvent) {
    // So inicia pull se o scroll esta no topo
    if (window.scrollY > 4) return;
    startY.current = e.touches[0].clientY;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (startY.current == null || busy) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy <= 0) {
      // arrastando pra cima -> nao e PTR
      setPull(0);
      return;
    }
    // Resistencia: divide pra dar feeling "elastico"
    const dampened = Math.min(MAX_PULL, dy * 0.55);
    setPull(dampened);
  }
  async function onTouchEnd() {
    if (startY.current == null) return;
    const reached = pull >= THRESHOLD;
    startY.current = null;
    if (!reached) {
      setPull(0);
      return;
    }
    setBusy(true);
    try {
      await onRefresh();
    } finally {
      setBusy(false);
      setPull(0);
    }
  }

  const progress = Math.min(1, pull / THRESHOLD);
  const showIndicator = pull > 4 || busy;

  return (
    <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
      {/* Indicador no topo, posicao absoluta */}
      {showIndicator && (
        <div
          className="pointer-events-none flex justify-center"
          style={{
            height: busy ? 48 : pull,
            transition: busy || startY.current === null ? "height 0.2s ease" : "none",
          }}
        >
          <div
            className="grid place-items-center mt-2 w-10 h-10 rounded-full bg-card border border-border shadow"
            style={{
              opacity: busy ? 1 : progress,
              transform: `rotate(${progress * 360}deg)`,
              transition: busy ? "opacity 0.2s ease" : "none",
            }}
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin text-primary" />
            ) : (
              <RefreshCcw className="w-4 h-4 text-primary" />
            )}
          </div>
        </div>
      )}
      {/* Conteudo (sem transform pra nao quebrar position:sticky internos) */}
      {children}
    </div>
  );
}
