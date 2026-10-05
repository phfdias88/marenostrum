"use client";

/**
 * Foto oficial do candidato (vinda do TSE via /api/v1/tse/candidates/{id}/photo).
 *
 * Estrategia de fallback:
 * 1. Tenta carregar a foto via <img>
 * 2. Se 404 ou erro de rede, esconde a foto e mostra avatar com iniciais
 * 3. Cor do avatar e deterministica pelo numero do partido (consistente entre paginas)
 *
 * O endpoint backend e PUBLICO (sem JWT) — proxia do TSE com cache em disco.
 */
import { useEffect, useRef, useState } from "react";

import { partyTheme } from "@/lib/partyColors";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

function initials(name: string): string {
  const parts = name
    .replace(/[^a-zA-ZÀ-ÿ ]/g, "")
    .trim()
    .split(/\s+/)
    .filter((p) => p.length > 1);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

type Size = "sm" | "md" | "lg" | "xl";

const SIZE_PX: Record<Size, string> = {
  sm: "w-10 h-10 text-xs",
  md: "w-14 h-14 text-sm",
  lg: "w-20 h-20 text-base",
  xl: "w-32 h-32 text-2xl",
};

type Props = {
  candidateId: string;
  name: string;
  partyNumber: number;
  size?: Size;
  className?: string;
};

export function CandidatePhoto({
  candidateId,
  name,
  partyNumber,
  size = "md",
  className = "",
}: Props) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [visible, setVisible] = useState(false);
  const dim = SIZE_PX[size];
  const url = `${API_BASE}/v1/tse/candidates/${candidateId}/photo`;
  const theme = partyTheme(partyNumber);
  const ref = useRef<HTMLDivElement>(null);

  // IntersectionObserver "estrito" — so dispara fetch da foto quando o
  // avatar entra a menos de 200px do viewport visivel. Mais conservador
  // que o `loading="lazy"` nativo, que dispara MUITO antes (>1000px),
  // causando estouro no backend (cada foto = RemoteZip lock por UF).
  useEffect(() => {
    if (!ref.current || visible) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true);
            io.disconnect();
            break;
          }
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [visible]);

  // Renderiza fallback (iniciais + cor do partido) + img sobreposta.
  // A img so e adicionada ao DOM quando visivel, evitando barragens
  // de fetch quando a lista tem 20+ candidatos.
  return (
    <div
      ref={ref}
      className={`relative shrink-0 ${dim} rounded-full ${className}`}
      title={name}
    >
      <div
        className="absolute inset-0 rounded-full grid place-items-center font-bold"
        style={{ backgroundColor: theme.color, color: theme.text }}
      >
        {initials(name)}
      </div>
      {visible && !failed && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={name}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          loading="lazy"
          decoding="async"
          className={`absolute inset-0 w-full h-full rounded-full object-cover border border-border transition-opacity duration-200 ${loaded ? "opacity-100" : "opacity-0"}`}
        />
      )}
    </div>
  );
}
