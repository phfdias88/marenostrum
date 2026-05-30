"use client";

/**
 * Numero que "voa" de 0 ate o valor final via requestAnimationFrame.
 * Curva ease-out cubic (rapido no comeco, suave no fim) — feeling premium.
 *
 * Re-anima quando value muda (ideal pra ver stats reagindo a filtros).
 */
import { useEffect, useRef, useState } from "react";

const fmt = new Intl.NumberFormat("pt-BR");
const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

type Props = {
  value: number;
  /** Duracao em ms (default 800). */
  duration?: number;
  /** Sufixo opcional (ex: "%"). */
  suffix?: string;
  /** Prefixo opcional (ex: "R$ "). */
  prefix?: string;
  /** Se true, mostra como porcentagem (1 casa). Caso contrario, inteiro pt-BR. */
  percent?: boolean;
  className?: string;
};

export function AnimatedNumber({
  value,
  duration = 800,
  suffix,
  prefix,
  percent,
  className,
}: Props) {
  const [display, setDisplay] = useState(value);
  // Guarda valor "alvo" pra detectar mudancas — evita usar dependencia
  // closure-stale dentro do step do rAF.
  const targetRef = useRef(value);
  // Guarda o display em ref pra evitar fechar sobre estado stale.
  const displayRef = useRef(value);
  displayRef.current = display;

  useEffect(() => {
    targetRef.current = value;
    const from = displayRef.current;
    const target = value;
    if (from === target) return;

    let raf = 0;
    let start: number | null = null;
    let finished = false;

    const step = (t: number) => {
      if (start === null) start = t;
      // Se um novo valor chegou no meio da animacao, abandona — proximo
      // useEffect-run vai criar uma nova animacao com fromRef atual.
      if (targetRef.current !== target) return;
      const elapsed = t - start;
      const k = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      const next = from + (target - from) * eased;
      setDisplay(next);
      if (k < 1) {
        raf = requestAnimationFrame(step);
      } else {
        // Snap defensivo no valor final — garante que sempre converge
        // mesmo se rAF for cortado pelo browser (tab em background, etc).
        setDisplay(target);
        finished = true;
      }
    };
    raf = requestAnimationFrame(step);

    // Safety net: depois de duration*1.5, forca o valor final caso o
    // rAF tenha sido suspenso (tab em background, throttling do navegador,
    // re-render rapido do pai). Sem isso, numero podia ficar travado
    // no meio da animacao.
    const timeoutId = window.setTimeout(() => {
      if (!finished && targetRef.current === target) {
        setDisplay(target);
        finished = true;
      }
    }, duration * 1.5 + 100);

    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(timeoutId);
    };
  }, [value, duration]);

  const formatted = percent
    ? `${fmtPct.format(display)}`
    : fmt.format(Math.round(display));

  return (
    <span className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
