"use client";

/**
 * Linha que revela botoes de acao ao arrastar pra esquerda (estilo iOS).
 *
 * Uso:
 *   <SwipeableRow
 *     actions={[
 *       { label: "Editar", color: "blue", onClick: () => ... },
 *       { label: "Apagar", color: "red", onClick: () => ... },
 *     ]}
 *   >
 *     <ContactRowContent ... />
 *   </SwipeableRow>
 *
 * Funciona so no mobile (touch). Em desktop a linha fica estatica.
 */
import { useRef, useState } from "react";

type Action = {
  label: string;
  icon?: React.ReactNode;
  color?: "red" | "blue" | "amber" | "emerald";
  onClick: () => void;
};

const COLOR: Record<NonNullable<Action["color"]>, string> = {
  red: "bg-rose-600 text-white",
  blue: "bg-blue-600 text-white",
  amber: "bg-amber-500 text-white",
  emerald: "bg-emerald-600 text-white",
};

export function SwipeableRow({
  actions,
  children,
  actionWidth = 80,
  className,
}: {
  actions: Action[];
  children: React.ReactNode;
  actionWidth?: number;
  className?: string;
}) {
  const [offset, setOffset] = useState(0);
  const startX = useRef<number | null>(null);
  const startOffset = useRef(0);

  const maxSwipe = actionWidth * actions.length;

  function onTouchStart(e: React.TouchEvent) {
    startX.current = e.targetTouches[0].clientX;
    startOffset.current = offset;
  }
  function onTouchMove(e: React.TouchEvent) {
    if (startX.current == null) return;
    const dx = e.targetTouches[0].clientX - startX.current;
    const next = Math.max(-maxSwipe, Math.min(0, startOffset.current + dx));
    setOffset(next);
  }
  function onTouchEnd() {
    if (startX.current == null) return;
    // Snap: se passou metade do max, snap pra aberto; senao fecha
    setOffset(offset < -maxSwipe / 2 ? -maxSwipe : 0);
    startX.current = null;
  }
  function actionClick(a: Action) {
    a.onClick();
    setOffset(0); // fecha depois de clicar
  }

  return (
    <div className={"relative overflow-hidden " + (className ?? "")}>
      {/* Botoes atras */}
      <div
        className="absolute right-0 top-0 bottom-0 flex"
        aria-hidden={offset === 0}
      >
        {actions.map((a, i) => (
          <button
            key={i}
            onClick={() => actionClick(a)}
            style={{ width: actionWidth }}
            className={
              "flex flex-col items-center justify-center gap-1 text-xs font-medium " +
              COLOR[a.color ?? "blue"]
            }
          >
            {a.icon}
            {a.label}
          </button>
        ))}
      </div>
      {/* Conteudo deslizavel */}
      <div
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        style={{
          transform: `translateX(${offset}px)`,
          transition: startX.current == null ? "transform 0.2s ease" : "none",
        }}
        className="bg-card touch-pan-y"
      >
        {children}
      </div>
    </div>
  );
}
