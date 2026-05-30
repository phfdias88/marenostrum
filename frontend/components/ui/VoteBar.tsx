"use client";

/**
 * Barra de forca proporcional — usada em rankings (votos por municipio,
 * top candidatos, eleicao panel).
 *
 * Usa transition de width pra "encher" suavemente ao entrar na tela. Tons
 * variam por intensidade pra dar leitura imediata (top = dourado quente,
 * meio = dourado medio, calda = muted).
 */
import { useEffect, useState } from "react";

type Props = {
  /** Valor da linha (0..max). */
  value: number;
  /** Maximo do ranking (1a linha). */
  max: number;
  /** Tom forte pra topo (1o-3o), medio pra meio, esmaecido pro resto. */
  rank?: number;
  className?: string;
};

export function VoteBar({ value, max, rank, className }: Props) {
  const pct = Math.max(0, Math.min(100, (value / Math.max(1, max)) * 100));
  // Anima do 0 -> pct ao montar (smooth fill)
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setW(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  // Cor por rank: top3 = primary (gold), 4-10 = primary/70, resto = muted-foreground/60
  const tone =
    rank === undefined
      ? "bg-primary"
      : rank <= 3
        ? "bg-primary"
        : rank <= 10
          ? "bg-primary/70"
          : "bg-primary/40";

  return (
    <div
      className={"h-1.5 rounded-full bg-muted overflow-hidden " + (className ?? "")}
      aria-hidden
    >
      <div
        className={"h-full rounded-full transition-[width] duration-700 ease-out " + tone}
        style={{ width: `${w}%` }}
      />
    </div>
  );
}
